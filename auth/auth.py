"""SlideAtlas JWT 인증 Blueprint.

라우트:
  POST /api/auth/register       회원가입 (명단 대조 + TO 검사 + 인증코드 발송)
  POST /api/auth/verify-email   인증코드 확인 (TO 재검사 + JWT 발급)
  POST /api/auth/login          로그인 (세션 무효화 + JWT 발급)
  POST /api/auth/logout         로그아웃 (session_token 제거)
  GET  /api/auth/me             현재 사용자 정보

모든 DB 작업은 conn.autocommit=False 트랜잭션으로 묶고 에러 시 전면 rollback.
민감정보(JWT 시크릿/Gmail/DB 비번)는 환경변수/.env 에서만 읽는다.
"""
import os
import uuid
import secrets
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from flask import Blueprint, request, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash

from .decorators import (
    encode_token, login_required, COOKIE_NAME, _today_kst, ADMIN_ROSTER_SUBJECT,
    _has_admin_roster,
)

load_dotenv()  # .env 있으면 읽기, 없으면(Render) 환경변수 그대로 사용

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

VERIFICATION_TTL_MIN = 10
MAX_CODE_ATTEMPTS = 5
COOKIE_MAX_AGE = 86400

# 계정 잠금 정책
LOCK_THRESHOLD = 10    # 윈도우 내 실패 누적 임계값
LOCK_WINDOW_HRS = 24   # 카운팅 윈도우 / 자동 해제 시간(시간)

# 인증코드 재발송 정책
RESEND_COOLDOWN_SEC = 60   # 1분 쿨다운
RESEND_DAILY_LIMIT = 5     # 24시간 최대 5회


# ─────────────────────────────────────────────
# 응답 헬퍼
# ─────────────────────────────────────────────
def _ok(data=None, status=200):
    resp = jsonify({"success": True, "data": data or {}})
    resp.status_code = status
    resp.headers["Cache-Control"] = "no-store, no-cache"
    return resp


def _err(error, message, status=400):
    resp = jsonify({"success": False, "error": error, "message": message})
    resp.status_code = status
    resp.headers["Cache-Control"] = "no-store, no-cache"
    return resp


def _set_auth_cookies(resp, token, csrf_token):
    # JWT: HttpOnly + Secure + SameSite=Strict (JS 접근 불가)
    resp.set_cookie(
        COOKIE_NAME, token,
        httponly=True, secure=True, samesite="Strict", max_age=COOKIE_MAX_AGE,
    )
    # CSRF: JS가 읽어 헤더에 실어보낼 수 있도록 httponly=False
    resp.set_cookie(
        "csrf_token", csrf_token,
        httponly=False, secure=True, samesite="Strict", max_age=COOKIE_MAX_AGE,
    )
    return resp


def _db():
    from server_render import get_db_conn, release_db_conn
    return get_db_conn, release_db_conn


# ─────────────────────────────────────────────
# 이메일 발송 (send_report.py 방식 재사용)
# ─────────────────────────────────────────────
def send_verification_email(to_email: str, code: str):
    msg = MIMEText(f"SlideAtlas 인증코드: {code}\n\n10분 내에 입력하세요.")
    msg["Subject"] = "[SlideAtlas] 이메일 인증코드"
    msg["From"] = os.environ["GMAIL_USER"]
    msg["To"] = to_email
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PW"])
        s.send_message(msg)


def _gen_code() -> str:
    # CSPRNG(secrets) 사용 — 이메일 인증코드는 보안 토큰이므로 random(예측 가능) 금지(Codex#4).
    return str(secrets.randbelow(900000) + 100000)


def _now():
    return datetime.now(timezone.utc)


def _aware(ts):
    """naive timestamp 를 UTC aware 로 정규화."""
    if ts is None:
        return None
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


def _check_and_increment_failed(cur, user_id: int) -> bool:
    """실패 카운터 증가 + 임계값 도달 시 계정 잠금. 잠겼으면 True."""
    cur.execute(
        "SELECT failed_attempts, failed_window_start FROM users WHERE id = %s FOR UPDATE",
        (user_id,),
    )
    row = cur.fetchone()
    if row is None:
        return False

    failed, window_start = row
    now = _now()
    window_start = _aware(window_start)

    # 윈도우 만료 또는 미시작 → 새 윈도우로 카운트 1부터 시작.
    if window_start is None or (now - window_start).total_seconds() > LOCK_WINDOW_HRS * 3600:
        new_count = 1
        cur.execute(
            "UPDATE users SET failed_attempts = 1, failed_window_start = %s WHERE id = %s",
            (now, user_id),
        )
    else:
        new_count = (failed or 0) + 1
        cur.execute(
            "UPDATE users SET failed_attempts = %s WHERE id = %s",
            (new_count, user_id),
        )

    if new_count >= LOCK_THRESHOLD:
        cur.execute(
            "UPDATE users SET status = 'locked', locked_at = %s WHERE id = %s",
            (now, user_id),
        )
        return True
    return False


def _reset_failed_attempts(cur, user_id: int):
    cur.execute(
        "UPDATE users SET failed_attempts = 0, failed_window_start = NULL WHERE id = %s",
        (user_id,),
    )


def _check_auto_unlock(cur, user_id: int, status: str, locked_at) -> str:
    """locked_at 으로부터 LOCK_WINDOW_HRS 경과 시 자동 해제. 현재 유효 status 반환."""
    if status != "locked" or locked_at is None:
        return status
    now = _now()
    locked_at = _aware(locked_at)
    if (now - locked_at).total_seconds() > LOCK_WINDOW_HRS * 3600:
        cur.execute(
            """UPDATE users
               SET status = 'active', locked_at = NULL,
                   failed_attempts = 0, failed_window_start = NULL
               WHERE id = %s""",
            (user_id,),
        )
        return "active"
    return "locked"


def _issue_token_payload(user_id, institution_id, role, is_special):
    session_token = str(uuid.uuid4())
    payload = {
        "sub": str(user_id),   # PyJWT 2.8+ requires sub to be string
        "institution_id": institution_id,
        "role": role,
        "session_token": session_token,
        "is_special": bool(is_special),
    }
    return session_token, payload


# ─────────────────────────────────────────────
# POST /api/auth/register
# ─────────────────────────────────────────────
@auth_bp.route("/register", methods=["POST"])
def register():
    # 두 트랙 가입 모델(§6-4, v3.4 CEO 확정): 가입자는 지위·역할·과목을 입력하지 않는다.
    #   폼 = 기관 + 이름 + 이메일 + 비번(+확인). role·position·subject_code는 전부
    #   institution_rosters 두 트랙(__ADMIN__ 행 / subject 행) 조회로 서버가 결정한다.
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    institution_id = (body.get("institution_id") or "").strip()
    # 이름은 가입 폼에서 받지 않는다(옵션 A) — 표시용 이름은 roster.name이 단일 출처(§6-4).
    #   users에 name 컬럼이 없고 INSERT에도 포함하지 않으므로 서버는 name을 무시한다.

    if not email or not password or not institution_id:
        return _err("MISSING_FIELDS", "필수 입력값이 누락되었습니다")
    if len(password) < 8:
        return _err("WEAK_PASSWORD", "비밀번호는 8자 이상이어야 합니다")

    get_db_conn, release_db_conn = _db()
    conn = get_db_conn()
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            # 1) 이미 가입된 이메일 — 이메일당 users 1계정 정책(§6-2, Codex#3·Gemini#5 확정).
            #    과목 소속은 institution_rosters 행으로 표현하며, users.email은 전역 식별자다.
            #    동일 이메일 재가입 시 새 계정/중복 pending을 만들지 않는다(앱 레이어 강제).
            cur.execute(
                "SELECT 1 FROM users WHERE lower(email) = %s",
                (email,),
            )
            if cur.fetchone() is not None:
                conn.rollback()
                return _err("EMAIL_EXISTS", "이미 가입된 이메일입니다", 409)

            # 2) roster 두 트랙 조회 (role 필터 없음 — 역할도 서버가 결정).
            cur.execute(
                """SELECT subject_code, position FROM institution_rosters
                   WHERE institution_id = %s AND lower(email) = %s""",
                (institution_id, email),
            )
            roster_rows = cur.fetchall()
            if not roster_rows:
                conn.rollback()
                return _err("NOT_ON_ROSTER", "명단에 없습니다. 과 사무실에 문의하세요", 403)

            # 3) 트랙 분할 + role 결정 (§6-4).
            #    트랙2(__ADMIN__ 행) 존재 → role='admin'(포털 접근), 아니면 'viewer'.
            admin_rows = [r for r in roster_rows if r[0] == ADMIN_ROSTER_SUBJECT]
            role = "admin" if admin_rows else "viewer"

            # 4) subject_code·position 해석 — position의 단일 출처는 subject 행이다(§6-4).
            #    active = (institution, subject)가 접근창 내 active 구독을 가진 subject 행.
            #    ※ register는 좌석·온보딩(§6-3) 정합상 subscription active-in-window만 사용
            #      (단일 게이트의 granted-OR 분기와 의도적으로 다름 — granted 단독은 불충분).
            #    today는 KST(§16·§18 D10).
            today = _today_kst()
            cur.execute(
                """SELECT r.subject_code, r.position
                   FROM institution_rosters r
                   WHERE r.institution_id = %s AND lower(r.email) = %s
                     AND r.subject_code <> %s
                     AND EXISTS(SELECT 1 FROM subscriptions s
                                 WHERE s.institution_id = r.institution_id
                                   AND s.subject_code = r.subject_code
                                   AND s.status = 'active'
                                   AND s.access_open_date <= %s AND s.subscription_end >= %s)""",
                (institution_id, email, ADMIN_ROSTER_SUBJECT, today, today),
            )
            active = cur.fetchall()

            if len(active) == 1:
                # subject·position 모두 그 매칭된 subject 행에서만 가져온다(__ADMIN__ position(NULL) 미사용).
                subject_code, position = active[0]
            elif len(active) == 0:
                if role == "admin":
                    # admin-only(또는 active subject 없는 겸직): 과목 축 없음(좌석 0·콘텐츠 비소비, §21).
                    #   users.subject_code=NULL, position=NULL. 구독·정원 게이트 면제(§9). 슬라이드 접근은
                    #   별도 단일 게이트가 과목 좌석으로 판정하므로 면제가 콘텐츠 노출을 넓히지 않는다(§8).
                    subject_code, position = None, None
                else:
                    # viewer인데 접근창 내 active 구독 없음 — 온보딩 선행(§6-3) 위반. active 계정 미생성.
                    conn.rollback()
                    return _err("SUBSCRIPTION_INACTIVE",
                                "해당 과목 구독이 활성화되지 않았습니다. 과 사무실에 문의하세요", 403)
            else:
                # active subject 2개 이상 — 단일 users.subject_code로 모호. v1.5(다과목)까지 fail-closed 거부(D12).
                conn.rollback()
                return _err("MULTI_SUBJECT_AMBIGUOUS",
                            "여러 과목 명단에 등록되어 있습니다. 과 사무실에 문의하세요", 403)

            # 5) 좌석(정원) 검사 — 면제 기준은 subject_code 유무다(Codex 발견 1·2 수정).
            #    콘텐츠를 소비(=좌석 점유, subject_code 있음)하는 사용자는 admin 겸직이어도 정원
            #    검사를 받는다. subject_code가 NULL인 순수 admin-only(좌석 0)만 검사를 건너뛴다.
            #    (이전 role=='viewer' 기준은 겸직 admin이 좌석 점유하면서 정원 검사를 우회했음.)
            #    여기는 소프트 사전검사이며, 권위 있는 동시성 재검사는 verify_email에서 행 잠금
            #    (FOR UPDATE)으로 수행한다.
            if subject_code is not None:
                cur.execute(
                    """SELECT max_seats FROM subscriptions
                       WHERE institution_id = %s AND subject_code = %s AND status = 'active'
                         AND access_open_date <= %s AND subscription_end >= %s
                       ORDER BY subscription_end DESC
                       LIMIT 1""",
                    (institution_id, subject_code, today, today),
                )
                sub = cur.fetchone()
                max_seats = sub[0] if sub else None
                cur.execute(
                    """SELECT COUNT(*) FROM users
                       WHERE institution_id = %s AND subject_code = %s AND status = 'active'""",
                    (institution_id, subject_code),
                )
                active_count = cur.fetchone()[0]
                if max_seats is not None and active_count >= max_seats:
                    conn.rollback()
                    return _err("SEAT_FULL", "정원이 초과되었습니다", 403)

            # 6) users INSERT (pending_verification, subject_code·position 채번) + 인증코드 INSERT
            pw_hash = generate_password_hash(password)
            cur.execute(
                """INSERT INTO users (institution_id, subject_code, email, password_hash, role, position, status)
                   VALUES (%s, %s, %s, %s, %s, %s, 'pending_verification')
                   RETURNING id""",
                (institution_id, subject_code, email, pw_hash, role, position),
            )
            user_id = cur.fetchone()[0]

            code = _gen_code()
            expires_at = _now() + timedelta(minutes=VERIFICATION_TTL_MIN)
            cur.execute(
                """INSERT INTO email_verifications (user_id, code, expires_at)
                   VALUES (%s, %s, %s)""",
                (user_id, code, expires_at),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        release_db_conn(conn)
        return _err("SERVER_ERROR", "처리 중 오류가 발생했습니다", 500)
    finally:
        try:
            conn.autocommit = True
        except Exception:
            pass

    # 메일 발송 실패가 가입 트랜잭션을 되돌리지는 않는다(코드 재발송 경로 존재).
    try:
        send_verification_email(email, code)
    except Exception:
        release_db_conn(conn)
        return _err("EMAIL_SEND_FAILED", "인증코드 발송에 실패했습니다. 잠시 후 다시 시도하세요", 502)

    release_db_conn(conn)
    return _ok({"message": "인증코드가 이메일로 발송되었습니다"})


# ─────────────────────────────────────────────
# POST /api/auth/verify-email
# ─────────────────────────────────────────────
@auth_bp.route("/verify-email", methods=["POST"])
def verify_email():
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    code = (body.get("code") or "").strip()
    if not email or not code:
        return _err("MISSING_FIELDS", "이메일과 인증코드를 입력하세요")

    get_db_conn, release_db_conn = _db()
    conn = get_db_conn()
    conn.autocommit = False
    token = csrf_token = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, institution_id, role, is_special, subject_code
                   FROM users
                   WHERE lower(email) = %s AND status = 'pending_verification'""",
                (email,),
            )
            user = cur.fetchone()
            if user is None:
                conn.rollback()
                return _err("USER_NOT_FOUND", "인증 대기 중인 사용자가 없습니다", 404)
            user_id, institution_id, role, is_special, subject_code = user

            # D4(b): 가입 경로가 subject_code를 채웠어야 한다(§6-2). viewer가 비어 있으면 가입 경로
            #   결함이므로 임의 기본값을 채우지 않고 거부한다(§0-3). 과목 축 없이 active 전환 금지.
            #   단 기관 관리자(role='admin')의 admin-only 계정은 과목 축이 없어 subject_code=NULL이
            #   정상이다(§6-4 v3.4). NULL을 센티넬로 재할당하지 않고 그대로 둔다(roster UPDATE 분기에서
            #   NULL→__ADMIN__ 행, 비NULL(겸직)→subject 행으로 처리, §9).
            is_admin_user = (role == "admin")
            if not subject_code and not is_admin_user:
                conn.rollback()
                print(f"[verify_email] subject_code 누락(user_id={user_id}, email={email}) — 가입 경로 결함")
                return _err("SUBJECT_CODE_MISSING", "계정 설정 오류입니다. 과 사무실에 문의하세요", 409)

            cur.execute(
                """SELECT id, code, expires_at, consumed, attempt_count
                   FROM email_verifications
                   WHERE user_id = %s AND consumed = FALSE
                   ORDER BY created_at DESC
                   LIMIT 1
                   FOR UPDATE""",
                (user_id,),
            )
            ev = cur.fetchone()
            if ev is None:
                conn.rollback()
                return _err("CODE_NOT_FOUND", "유효한 인증코드가 없습니다", 404)
            ev_id, ev_code, expires_at, consumed, attempt_count = ev

            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < _now():
                cur.execute(
                    "UPDATE email_verifications SET consumed = TRUE WHERE id = %s",
                    (ev_id,),
                )
                conn.commit()
                return _err("CODE_EXPIRED", "인증코드가 만료되었습니다", 410)

            if attempt_count >= MAX_CODE_ATTEMPTS:
                cur.execute(
                    "UPDATE email_verifications SET consumed = TRUE WHERE id = %s",
                    (ev_id,),
                )
                conn.commit()
                return _err("TOO_MANY_ATTEMPTS", "시도 횟수를 초과했습니다", 429)

            if ev_code != code:
                cur.execute(
                    "UPDATE email_verifications SET attempt_count = attempt_count + 1 WHERE id = %s",
                    (ev_id,),
                )
                remaining = MAX_CODE_ATTEMPTS - (attempt_count + 1)
                # 코드 무차별 대입 방어: 누적 실패 시 계정 잠금
                now_locked = _check_and_increment_failed(cur, user_id)
                conn.commit()
                if now_locked:
                    return _err("ACCOUNT_LOCKED", "보안상 계정이 잠겼습니다. 과 사무실에 문의하세요", 403)
                return _err_with_remaining("CODE_MISMATCH", "인증코드가 일치하지 않습니다", remaining)

            # 코드 일치 → 정원(좌석) 재검사 (동시성 방어): 해당 (기관×과목) 구독 행 잠금.
            #   subscriptions.max_seats(과목별)를 기준으로 한다(§13-2·§16). institutions.max_users
            #   (deprecated)는 참조하지 않는다(§0-2). 구독 행을 FOR UPDATE로 잠가 동시 verify가
            #   마지막 좌석을 중복 통과하지 못하게 한다(과목 단위 직렬화).
            # [#4] 접근창 내 active 구독 필수(없으면 거부 — active 전환 금지). today는 KST(§18 D10).
            #   면제 기준은 subject_code 유무다(Codex 발견 1·2 수정). 캡처된 subject가 있으면
            #   admin 겸직이어도 (1) 그 과목 active-in-window 구독 재확인(fail-closed) (2) 좌석
            #   FOR UPDATE 재검사를 수행한다. subject_code가 NULL인 순수 admin-only만 면제한다.
            if subject_code is not None:
                today = _today_kst()
                cur.execute(
                    """SELECT max_seats FROM subscriptions
                       WHERE institution_id = %s AND subject_code = %s AND status = 'active'
                         AND access_open_date <= %s AND subscription_end >= %s
                       ORDER BY subscription_end DESC
                       LIMIT 1
                       FOR UPDATE""",
                    (institution_id, subject_code, today, today),
                )
                sub = cur.fetchone()
                if sub is None:
                    conn.rollback()
                    return _err("SUBSCRIPTION_INACTIVE",
                                "해당 과목 구독이 활성화되지 않았습니다. 과 사무실에 문의하세요", 403)
                max_seats = sub[0]
                cur.execute(
                    """SELECT COUNT(*) FROM users
                       WHERE institution_id = %s AND subject_code = %s AND status = 'active'""",
                    (institution_id, subject_code),
                )
                active_count = cur.fetchone()[0]
                if max_seats is not None and active_count >= max_seats:
                    conn.rollback()
                    return _err("SEAT_FULL", "정원이 초과되었습니다", 403)

            session_token, payload = _issue_token_payload(
                user_id, institution_id, role, is_special
            )
            cur.execute(
                """UPDATE users
                   SET status = 'active', session_token = %s, last_login = NOW(),
                       failed_attempts = 0, failed_window_start = NULL
                   WHERE id = %s""",
                (session_token, user_id),
            )
            cur.execute(
                "UPDATE email_verifications SET consumed = TRUE WHERE id = %s",
                (ev_id,),
            )
            # roster는 (기관×과목×이메일) 독립 행(§6-2) — 인증된 해당 행만 표시.
            # (institution_id, email)만으로 갱신하면 다과목 명단을 일괄 over-mark(Codex WARN2).
            #   [v3.4 결정#1] users.subject_code 기준 분기:
            #     · NULL(순수 admin-only) → __ADMIN__ 행을 verified.
            #     · 비NULL(viewer 또는 active subject 1건 캡처한 겸직 admin) → 그 subject 행을 verified.
            #   (겸직에서 __ADMIN__ 행만 바뀌고 subject 행이 누락되는 일이 없도록.)
            roster_subject = subject_code if subject_code else ADMIN_ROSTER_SUBJECT
            cur.execute(
                "UPDATE institution_rosters SET is_verified = TRUE "
                "WHERE institution_id = %s AND subject_code = %s AND lower(email) = %s",
                (institution_id, roster_subject, email),
            )
        conn.commit()
        token = encode_token(payload)
        csrf_token = secrets.token_hex(32)
    except Exception:
        conn.rollback()
        release_db_conn(conn)
        return _err("SERVER_ERROR", "처리 중 오류가 발생했습니다", 500)
    finally:
        try:
            conn.autocommit = True
        except Exception:
            pass
    release_db_conn(conn)

    resp = _ok({
        "user_id": user_id,
        "institution_id": institution_id,
        "role": role,
        "csrf_token": csrf_token,
    })
    return _set_auth_cookies(resp, token, csrf_token)


def _err_with_remaining(error, message, remaining):
    resp = jsonify({
        "success": False, "error": error, "message": message,
        "remaining": max(remaining, 0),
    })
    resp.status_code = 400
    resp.headers["Cache-Control"] = "no-store, no-cache"
    return resp


# ─────────────────────────────────────────────
# POST /api/auth/resend-code
# ─────────────────────────────────────────────
@auth_bp.route("/resend-code", methods=["POST"])
def resend_code():
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    if not email:
        return _err("MISSING_FIELDS", "이메일을 입력하세요")

    get_db_conn, release_db_conn = _db()
    conn = get_db_conn()
    conn.autocommit = False
    code = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, status FROM users WHERE lower(email) = %s",
                (email,),
            )
            user = cur.fetchone()
            if user is None:
                conn.rollback()
                return _err("USER_NOT_FOUND", "해당 이메일로 가입된 계정이 없습니다", 404)
            user_id, status = user

            if status in ("locked", "suspended"):
                conn.rollback()
                return _err("ACCOUNT_LOCKED", "보안상 계정이 잠겼습니다. 과 사무실에 문의하세요", 403)
            if status != "pending_verification":
                conn.rollback()
                return _err("ALREADY_VERIFIED", "이미 인증된 계정입니다", 409)

            # 동시 재발송 경쟁조건 방어: user row 잠금 후 쿨다운/한도 검사
            cur.execute("SELECT id FROM users WHERE id = %s FOR UPDATE", (user_id,))

            now = _now()

            # 1분 쿨다운
            cur.execute(
                "SELECT MAX(created_at) FROM email_verifications WHERE user_id = %s",
                (user_id,),
            )
            last_sent = _aware(cur.fetchone()[0])
            if last_sent is not None:
                elapsed = (now - last_sent).total_seconds()
                if elapsed < RESEND_COOLDOWN_SEC:
                    remaining_sec = int(RESEND_COOLDOWN_SEC - elapsed)
                    conn.rollback()
                    return _err("RESEND_TOO_SOON", f"{remaining_sec}초 후에 다시 시도하세요", 429)

            # 24시간 발송 횟수 제한
            cur.execute(
                "SELECT COUNT(*) FROM email_verifications WHERE user_id = %s AND created_at > %s",
                (user_id, now - timedelta(hours=24)),
            )
            daily_count = cur.fetchone()[0]
            if daily_count >= RESEND_DAILY_LIMIT:
                conn.rollback()
                return _err("RESEND_LIMIT_EXCEEDED", "오늘 재발송 한도를 초과했습니다. 내일 다시 시도하세요", 429)

            # 기존 미소진 코드 폐기 후 새 코드 발급
            cur.execute(
                "UPDATE email_verifications SET consumed = TRUE WHERE user_id = %s AND consumed = FALSE",
                (user_id,),
            )
            code = _gen_code()
            expires_at = now + timedelta(minutes=VERIFICATION_TTL_MIN)
            cur.execute(
                "INSERT INTO email_verifications (user_id, code, expires_at) VALUES (%s, %s, %s)",
                (user_id, code, expires_at),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        release_db_conn(conn)
        return _err("SERVER_ERROR", "처리 중 오류가 발생했습니다", 500)
    finally:
        try:
            conn.autocommit = True
        except Exception:
            pass

    try:
        send_verification_email(email, code)
    except Exception:
        release_db_conn(conn)
        return _err("EMAIL_SEND_FAILED", "인증코드 발송에 실패했습니다", 502)

    release_db_conn(conn)
    return _ok({"message": "새 인증코드가 발송되었습니다"})


# ─────────────────────────────────────────────
# POST /api/auth/login
# ─────────────────────────────────────────────
@auth_bp.route("/login", methods=["POST"])
def login():
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    if not email or not password:
        return _err("MISSING_FIELDS", "이메일과 비밀번호를 입력하세요")

    get_db_conn, release_db_conn = _db()
    conn = get_db_conn()
    conn.autocommit = False
    token = csrf_token = None
    user_ctx = None
    try:
        with conn.cursor() as cur:
            # [M2] 구독 만료 검사도 subscriptions(기관×과목) 모델 사용 (decorators._authenticate와 동일 규칙).
            # 반환 shape(8컬럼, 마지막=subscription_end)는 유지 — 테스트 mock·언패킹 호환.
            # [D4] 과목 격리 정식화: (institution_id, subject_code) 양축으로 매칭한다.
            #   NULL 폴백(기관 단위)은 제거됨 — subject_code는 가입 시 필수 채번되므로(§6-2) 정상 경로에
            #   NULL은 존재하지 않는다(§0-3·§0-4). subject_code 미일치 시 매칭 구독 없음 → 만료 검사 적용.
            # [C] 접근창 집행: 유효 구독 창(access_open_date <= today <= subscription_end)인
            #   active 구독만 본다(미래 학기 active도 창 전엔 NULL→만료). today는 KST(§16·§18 D10).
            today = _today_kst()
            cur.execute(
                """SELECT u.id, u.institution_id, u.role, u.is_special,
                          u.password_hash, u.status, u.locked_at, u.special_expires_at,
                          (SELECT MAX(s.subscription_end)
                             FROM subscriptions s
                            WHERE s.institution_id = u.institution_id
                              AND s.subject_code = u.subject_code
                              AND s.status = 'active'
                              AND s.access_open_date <= %s
                              AND s.subscription_end >= %s)
                   FROM users u
                   WHERE lower(u.email) = %s
                   FOR UPDATE OF u""",
                (today, today, email),
            )
            row = cur.fetchone()
            if row is None:
                conn.rollback()
                return _err("INVALID_CREDENTIALS", "이메일 또는 비밀번호가 올바르지 않습니다", 401)
            (user_id, institution_id, role, is_special,
             pw_hash, status, locked_at, special_expires_at, subscription_end) = row

            if status == "pending_verification":
                conn.rollback()
                return _err("EMAIL_NOT_VERIFIED", "이메일 인증을 완료하세요", 403)
            if status == "locked":
                # 24시간 경과 시 자동 해제 후 정상 로그인 흐름 진행.
                status = _check_auto_unlock(cur, user_id, status, locked_at)
                if status == "locked":
                    conn.commit()  # 자동해제 미발생 — 트랜잭션 마무리만
                    return _err("ACCOUNT_LOCKED", "보안상 계정이 잠겼습니다. 과 사무실에 문의하세요", 403)
            if status != "active":
                conn.rollback()
                return _err("ACCOUNT_INACTIVE", "비활성화된 계정입니다", 403)

            # 비밀번호 검증 (실패 시 카운터 증가 → 임계값 도달 시 잠금)
            if not pw_hash or not check_password_hash(pw_hash, password):
                now_locked = _check_and_increment_failed(cur, user_id)
                conn.commit()
                if now_locked:
                    return _err("ACCOUNT_LOCKED", "보안상 계정이 잠겼습니다. 과 사무실에 문의하세요", 403)
                return _err("INVALID_CREDENTIALS", "이메일 또는 비밀번호가 올바르지 않습니다", 401)

            # 만료 검사 (§8). is_special은 구독 만료 면제, 단 special_expires_at은 집행([B]).
            # today는 위에서 KST로 계산됨([C], 접근창과 동일 기준).
            if is_special:
                # [B] 특별계정 사용 기간 만료 집행. NULL(무기한)은 통과(§15-8 비권장).
                if special_expires_at is not None and special_expires_at < today:
                    conn.rollback()
                    return _err("SUBSCRIPTION_EXPIRED", "특별계정 사용 기간이 만료되었습니다", 403)
            elif role == "admin" and _has_admin_roster(user_id):
                # 기관 관리자(포털 전용): 구독 만료 게이트 면제(§9). 단 _authenticate와 동일하게
                #   '현재 __ADMIN__ roster 행 존재'와 결합한다(Codex 발견 4, 동일 함수 재사용).
                #   roster 회수 시 면제가 사라져 아래 else로 떨어지고, 매칭 구독이 없거나 만료면
                #   SUBSCRIPTION_EXPIRED로 로그인 단계에서 차단된다(로그인만 성공하고 보호 라우트에서
                #   막히던 불일치 제거). 슬라이드 접근은 별도 단일 게이트가 과목 좌석으로 판정(§8).
                pass
            else:
                # 매칭 구독이 없으면(subscription_end=NULL) 라이선스 격리상 차단(fail-closed).
                #   (role=admin이어도 __ADMIN__ roster가 없으면 여기로 떨어진다.)
                if subscription_end is None or subscription_end < today:
                    conn.rollback()
                    return _err("SUBSCRIPTION_EXPIRED", "구독이 만료되었습니다", 403)

            session_token, payload = _issue_token_payload(
                user_id, institution_id, role, is_special
            )
            # 기존 세션 무효화 — 이 시점부터 구 토큰 요청은 _authenticate()에서
            # SESSION_REVOKED를 반환함. 단일 동시접속 제어의 핵심 지점.
            # + 로그인 성공 시 실패 카운터 리셋
            cur.execute(
                """UPDATE users
                   SET session_token = %s, last_login = NOW(),
                       failed_attempts = 0, failed_window_start = NULL
                   WHERE id = %s""",
                (session_token, user_id),
            )
        conn.commit()
        token = encode_token(payload)
        csrf_token = secrets.token_hex(32)
        user_ctx = {
            "user_id": user_id,
            "institution_id": institution_id,
            "role": role,
            "csrf_token": csrf_token,
        }
    except Exception:
        conn.rollback()
        release_db_conn(conn)
        return _err("SERVER_ERROR", "처리 중 오류가 발생했습니다", 500)
    finally:
        try:
            conn.autocommit = True
        except Exception:
            pass
    release_db_conn(conn)

    resp = _ok(user_ctx)
    return _set_auth_cookies(resp, token, csrf_token)


# ─────────────────────────────────────────────
# POST /api/auth/logout
# ─────────────────────────────────────────────
@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    get_db_conn, release_db_conn = _db()
    conn = get_db_conn()
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET session_token = NULL WHERE id = %s",
                (g.user_id,),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        release_db_conn(conn)
        return _err("SERVER_ERROR", "처리 중 오류가 발생했습니다", 500)
    finally:
        try:
            conn.autocommit = True
        except Exception:
            pass
    release_db_conn(conn)

    resp = _ok({"message": "로그아웃되었습니다"})
    resp.delete_cookie(COOKIE_NAME, samesite="Strict")
    resp.delete_cookie("csrf_token", samesite="Strict")
    return resp


# ─────────────────────────────────────────────
# GET /api/auth/me
# ─────────────────────────────────────────────
@auth_bp.route("/me", methods=["GET"])
@login_required
def me():
    get_db_conn, release_db_conn = _db()
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, email, role, institution_id, is_special, status, last_login
                   FROM users WHERE id = %s""",
                (g.user_id,),
            )
            row = cur.fetchone()
    finally:
        release_db_conn(conn)

    if row is None:
        return _err("USER_NOT_FOUND", "사용자를 찾을 수 없습니다", 404)

    return _ok({
        "user_id": row[0],
        "email": row[1],
        "role": row[2],
        "institution_id": row[3],
        "is_special": bool(row[4]),
        "status": row[5],
        "last_login": row[6].isoformat() if row[6] else None,
    })
