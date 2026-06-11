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


# ─────────────────────────────────────────────
# 구독·좌석 판정 공통 헬퍼 (§0 단일 진실)
#   register()·verify_email() 와 포털 명단 sync(server_render._sync_member)가
#   모두 이 동일한 식을 재사용한다. 두 경로가 다른 식을 가지면 §0 위반(좌석·접근창 판정이 갈림).
# ─────────────────────────────────────────────
def active_window_subscription(cur, institution_id, subject_code, today, for_update=False):
    """(기관×과목)의 접근창 내 active 구독을 조회.

    접근창 = status='active' AND access_open_date <= today AND subscription_end >= today
            (today 는 KST 기준 — §16·§18 D10).
    반환 (found: bool, max_seats: int|None).
      found=False    → 접근창 내 active 구독 없음(미래학기/만료/미구독) → fail-closed 대상.
      max_seats=None → 구독은 있으나 정원 무제한(또는 미설정).
    for_update=True 면 구독 행을 FOR UPDATE 로 잠가 동시 좌석검사를 과목 단위로 직렬화한다.
    """
    lock = " FOR UPDATE" if for_update else ""
    cur.execute(
        f"""SELECT max_seats FROM subscriptions
            WHERE institution_id = %s AND subject_code = %s AND status = 'active'
              AND access_open_date <= %s AND subscription_end >= %s
            ORDER BY subscription_end DESC
            LIMIT 1{lock}""",
        (institution_id, subject_code, today, today),
    )
    row = cur.fetchone()
    if row is None:
        return (False, None)
    return (True, row[0])


def active_seat_count(cur, institution_id, subject_code):
    """해당 (기관×과목)에서 좌석을 점유한 active 사용자 수(정원 검사 분모)."""
    cur.execute(
        """SELECT COUNT(*) FROM users
           WHERE institution_id = %s AND subject_code = %s AND status = 'active'""",
        (institution_id, subject_code),
    )
    return cur.fetchone()[0]


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


def _fetch_position(user_id):
    """users.position(지위) 조회 — 인증 응답의 '랜딩 힌트·표시용'(DB 권위). 실패/미존재면 None
    (랜딩 JS 는 None → 기본 /home 폴백). ★ 인증·검증·세션 판정에는 쓰지 않는다 — 본 transaction
    과 분리된 부가 조회이며, /teacher 접근 게이트는 서버 _course_position(매 요청 DB 재조회)이 별도로
    판정한다(프론트 position 신뢰로 권한 우회 불가). 누수 방지: inner try/finally 로 release 보장."""
    get_db_conn, release_db_conn = _db()
    try:
        conn = get_db_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT position FROM users WHERE id = %s", (user_id,))
                row = cur.fetchone()
                return row[0] if row else None
        finally:
            release_db_conn(conn)
    except Exception:
        return None


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
    # [Codex sweep 후속] release_db_conn 은 finally 단일 지점에서만 — 검증실패 early return 포함 모든
    #   경로에서 정확히 1회(autocommit 복구 후). 판정 로직·반환 shape·에러코드는 불변, release 구조만 정리.
    try:
        conn.autocommit = False
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
            #    ★ §0 동기화 주의(Codex 2차 #3): 아래 접근창 술어
            #      (status='active' AND access_open_date<=today AND subscription_end>=today)는
            #      active_window_subscription() 헬퍼와 '문자 그대로 동일'해야 한다. 여기는 'roster 행 중
            #      active 과목 나열'이라 쿼리 형태(EXISTS 상관 서브쿼리)가 달라 헬퍼를 직접 못 쓰지만,
            #      술어를 바꿀 땐 반드시 헬퍼와 함께 바꾼다(둘이 갈리면 §0 위반).
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
                # 공통 헬퍼 재사용(§0): 포털 sync 와 동일한 접근창·좌석 식.
                _found, max_seats = active_window_subscription(
                    cur, institution_id, subject_code, today)
                active_count = active_seat_count(cur, institution_id, subject_code)
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
        return _err("SERVER_ERROR", "처리 중 오류가 발생했습니다", 500)
    finally:
        try:
            conn.autocommit = True
        except Exception:
            pass
        release_db_conn(conn)

    # 메일 발송 실패가 가입 트랜잭션을 되돌리지는 않는다(코드 재발송 경로 존재).
    # conn 은 위 finally 에서 이미 release 됨(메일 발송은 DB 무관).
    try:
        send_verification_email(email, code)
    except Exception:
        return _err("EMAIL_SEND_FAILED", "인증코드 발송에 실패했습니다. 잠시 후 다시 시도하세요", 502)

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
    token = csrf_token = None
    # [Codex sweep 후속] release_db_conn 은 finally 단일 지점에서만 — 검증실패/attempt-commit early return
    #   포함 모든 경로에서 정확히 1회(autocommit 복구 후). 판정 로직·반환 shape·에러코드 불변, release 구조만.
    try:
        conn.autocommit = False
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
                # 공통 헬퍼 재사용(§0): 구독 행 FOR UPDATE 로 좌석검사 직렬화(동시성 방어).
                found, max_seats = active_window_subscription(
                    cur, institution_id, subject_code, today, for_update=True)
                if not found:
                    conn.rollback()
                    return _err("SUBSCRIPTION_INACTIVE",
                                "해당 과목 구독이 활성화되지 않았습니다. 과 사무실에 문의하세요", 403)
                active_count = active_seat_count(cur, institution_id, subject_code)
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
            #   [v3.9 Codex/Gemini Low#5] 겸직(__ADMIN__ + 과목 행)은 두 행을 모두 verified로 갱신한다 —
            #   과거엔 캡처된 subject 행만 갱신돼 포털에서 '인증된 관리자'가 '대기'로 잘못 표시됐다(표시만, 권한 무관).
            #   대상 = '캡처된 subject 행(있으면) + role=='admin'이면 __ADMIN__ 행'으로 한정한다.
            #   ★ WARN2 취지 유지: '모든 과목 행 일괄 verified'가 아니라 두 특정 행만 — 타 과목 행은 미인증 유지.
            verify_subjects = []
            if subject_code:
                verify_subjects.append(subject_code)
            if role == "admin":
                verify_subjects.append(ADMIN_ROSTER_SUBJECT)
            if not verify_subjects:
                # 방어(이론상 미도달): subject_code도 없고 admin도 아니면 위 D4b 게이트에서 이미 거부됨.
                verify_subjects.append(ADMIN_ROSTER_SUBJECT)
            cur.execute(
                "UPDATE institution_rosters SET is_verified = TRUE "
                "WHERE institution_id = %s AND lower(email) = %s AND subject_code = ANY(%s)",
                (institution_id, email, verify_subjects),
            )
        conn.commit()
        token = encode_token(payload)
        csrf_token = secrets.token_hex(32)
    except Exception:
        conn.rollback()
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
        # 인증 직후 라우팅 분기용(login 응답과 동일 계약). 순수 admin-only는 /portal로.
        "subject_code": subject_code,
        "csrf_token": csrf_token,
        # [6번 A안] 랜딩 힌트(additive): position∈{교수,조교}면 프론트가 /teacher/courses 로 랜딩.
        #   ★ [Codex Low] login 과 동일하게 '맨 뒤' append — 기존 필드 순서 불변(§13-2 엄격). DB 권위, 실패 시 None.
        "position": _fetch_position(user_id),
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
    code = None
    # [Codex sweep] release_db_conn 은 finally 단일 지점에서만 — 검증실패 early return 포함 모든
    #   경로에서 정확히 1회(autocommit 복구 후). 판정 로직·반환 shape·에러코드는 불변, release 구조만 정리.
    try:
        conn.autocommit = False
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
        return _err("SERVER_ERROR", "처리 중 오류가 발생했습니다", 500)
    finally:
        try:
            conn.autocommit = True
        except Exception:
            pass
        release_db_conn(conn)

    # conn 은 위 finally 에서 이미 release 됨(메일 발송은 DB 무관).
    try:
        send_verification_email(email, code)
    except Exception:
        return _err("EMAIL_SEND_FAILED", "인증코드 발송에 실패했습니다", 502)

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
    token = csrf_token = None
    user_ctx = None
    # [Codex sweep 후속] release_db_conn 은 finally 단일 지점에서만 — 검증실패/잠금-commit early return
    #   포함 모든 경로에서 정확히 1회(autocommit 복구 후). 판정 로직·반환 shape·에러코드 불변, release 구조만.
    try:
        conn.autocommit = False
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
                """SELECT u.id, u.institution_id, u.role, u.subject_code, u.is_special,
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
            (user_id, institution_id, role, subject_code, is_special,
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
            elif role == "admin" and subject_code is None and _has_admin_roster(user_id):
                # [Codex 라운드2] 구독 만료 면제는 '순수 admin-only(subject_code IS NULL, 좌석 0)'에만.
                #   subject_code가 있으면(겸직, 좌석 점유) admin이어도 아래 else로 떨어져 구독 만료
                #   검사를 받는다 — register·verify·_authenticate와 4경로 일관.
                # 기관 관리자(포털 전용): 구독 만료 게이트 면제(§9). 단 _authenticate와 동일하게
                #   '현재 __ADMIN__ roster 행 존재'와 결합한다(발견 4, 동일 함수 재사용).
                #   roster 회수 시 면제가 사라져 아래 else로 떨어지고, 매칭 구독이 없거나 만료면
                #   SUBSCRIPTION_EXPIRED로 로그인 단계에서 차단된다. 슬라이드 접근은 별도 단일 게이트(§8).
                pass
            else:
                # 매칭 구독이 없으면(subscription_end=NULL) 라이선스 격리상 차단(fail-closed).
                #   (role=admin이어도 subject_code 보유 또는 __ADMIN__ roster 부재면 여기로 떨어진다.)
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
            # 로그인 후 라우팅 분기용(프론트). 순수 admin-only(role='admin' AND subject_code IS NULL)는
            #   슬라이드 0개 화면 대신 /portal로 보낸다. 게이트·권한 판정에는 쓰지 않는다(§8 단일 게이트 무관).
            "subject_code": subject_code,
            "csrf_token": csrf_token,
        }
    except Exception:
        conn.rollback()
        return _err("SERVER_ERROR", "처리 중 오류가 발생했습니다", 500)
    finally:
        try:
            conn.autocommit = True
        except Exception:
            pass
        release_db_conn(conn)

    # [6번 A안] 랜딩 힌트(additive): position∈{교수,조교}면 프론트가 /teacher/courses 로 랜딩.
    #   main transaction 과 분리된 부가 조회 — 인증·세션 판정·반환 기존 필드 불변(position 만 추가).
    user_ctx["position"] = _fetch_position(user_id)
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
# POST /api/auth/change-password  (D31 — 로그인 사용자 본인 비밀번호 변경)
# ─────────────────────────────────────────────
@auth_bp.route("/change-password", methods=["POST"])
@login_required
def change_password():
    """로그인 사용자가 '본인' 비밀번호를 변경한다.

    ★ 본인만: scope = g.user_id 단일 — body/경로의 user_id 는 받지도 보지도 않는다(IDOR 불가).
    ★ 현재 비번 검증: 기존 login 과 동일한 check_password_hash 로 current_password 를 대조해야만 진행.
    ★ 신규 해시/세션 로직 없음 — register 의 generate_password_hash, login/verify 의
      _issue_token_payload(세션 회전) 를 그대로 재사용한다.
    세션 처리: 비번 변경 시 session_token 을 회전하고(다른 기기의 구 세션은 다음 요청에서 SESSION_REVOKED),
      현재 기기에는 새 토큰 쿠키를 재발급해 로그인 상태를 유지한다(기존 동시접속 모델과 동일 메커니즘, §8).
    """
    body = request.get_json(silent=True) or {}
    current_password = body.get("current_password") or ""
    new_password = body.get("new_password") or ""
    if not current_password or not new_password:
        return _err("MISSING_FIELDS", "현재 비밀번호와 새 비밀번호를 입력하세요")
    # 새 비번 정책 — register 와 동일(8자 이상).
    if len(new_password) < 8:
        return _err("WEAK_PASSWORD", "비밀번호는 8자 이상이어야 합니다")

    get_db_conn, release_db_conn = _db()
    conn = get_db_conn()
    token = csrf_token = None
    # [Codex] release_db_conn 은 finally 단일 지점에서만 — 정상·검증실패(early return)·예외 모든
    #   경로에서 정확히 1회 release(autocommit 복구 후). early return 이 try 안에서 일어나도 finally 가
    #   release 를 보장 → 커넥션 누수 차단(직전 포털 수정 160a082 와 동일 패턴). 판정 로직·에러코드 불변.
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            # scope=g.user_id 고정(IDOR 불가). FOR UPDATE 로 동시 변경 직렬화.
            cur.execute(
                "SELECT password_hash, institution_id, role, is_special "
                "FROM users WHERE id = %s FOR UPDATE",
                (g.user_id,),
            )
            row = cur.fetchone()
            if row is None:
                conn.rollback()
                return _err("USER_NOT_FOUND", "사용자를 찾을 수 없습니다", 404)
            pw_hash, institution_id, role, is_special = row
            # ★ 현재 비밀번호 검증 — login 과 동일한 check_password_hash 재사용. 불일치면 변경 거부.
            if not pw_hash or not check_password_hash(pw_hash, current_password):
                conn.rollback()
                return _err("CURRENT_PASSWORD_INVALID", "현재 비밀번호가 올바르지 않습니다", 403)
            # 새 비번이 현재 비번과 동일하면 거부.
            if check_password_hash(pw_hash, new_password):
                conn.rollback()
                return _err("SAME_PASSWORD", "새 비밀번호가 현재 비밀번호와 같습니다")
            # 해싱·세션 회전은 기존 함수 재사용(신규 로직 없음).
            new_hash = generate_password_hash(new_password)
            session_token, payload = _issue_token_payload(
                g.user_id, institution_id, role, is_special)
            cur.execute(
                "UPDATE users SET password_hash = %s, session_token = %s WHERE id = %s",
                (new_hash, session_token, g.user_id),
            )
        conn.commit()
        token = encode_token(payload)
        csrf_token = secrets.token_hex(32)
    except Exception:
        conn.rollback()
        return _err("SERVER_ERROR", "처리 중 오류가 발생했습니다", 500)
    finally:
        try:
            conn.autocommit = True
        except Exception:
            pass
        release_db_conn(conn)

    # 세션 회전: 현재 기기에는 새 토큰/CSRF 쿠키 재발급(로그인 유지), 구 세션은 무효화(login·verify 와 동일).
    resp = _ok({"message": "비밀번호가 변경되었습니다"})
    return _set_auth_cookies(resp, token, csrf_token)


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
