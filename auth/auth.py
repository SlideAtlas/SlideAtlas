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
import random
import secrets
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from flask import Blueprint, request, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash

from .decorators import encode_token, login_required, COOKIE_NAME

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
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _err(error, message, status=400):
    resp = jsonify({"success": False, "error": error, "message": message})
    resp.status_code = status
    resp.headers["Cache-Control"] = "no-store"
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
    return str(random.randint(100000, 999999))


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
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    name = (body.get("name") or "").strip()
    role = (body.get("role") or "").strip()
    institution_id = (body.get("institution_id") or "").strip()

    if not email or not password or not role or not institution_id:
        return _err("MISSING_FIELDS", "필수 입력값이 누락되었습니다")

    get_db_conn, release_db_conn = _db()
    conn = get_db_conn()
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            # 1) 명단 화이트리스트 (email + role 동시 일치)
            cur.execute(
                """SELECT 1 FROM institution_rosters
                   WHERE institution_id = %s AND lower(email) = %s AND role = %s""",
                (institution_id, email, role),
            )
            if cur.fetchone() is None:
                conn.rollback()
                return _err("ROSTER_MISMATCH", "과 사무실에 문의하세요", 403)

            # 2) 이미 가입된 이메일
            cur.execute("SELECT 1 FROM users WHERE lower(email) = %s", (email,))
            if cur.fetchone() is not None:
                conn.rollback()
                return _err("EMAIL_EXISTS", "이미 가입된 이메일입니다", 409)

            # 3) TO(정원) 검사: max_users vs active 유저 수
            cur.execute(
                "SELECT max_users FROM institutions WHERE id = %s", (institution_id,)
            )
            inst = cur.fetchone()
            if inst is None:
                conn.rollback()
                return _err("INSTITUTION_NOT_FOUND", "기관을 찾을 수 없습니다", 404)
            max_users = inst[0]
            cur.execute(
                """SELECT COUNT(*) FROM users
                   WHERE institution_id = %s AND status = 'active'""",
                (institution_id,),
            )
            active_count = cur.fetchone()[0]
            if max_users is not None and active_count >= max_users:
                conn.rollback()
                return _err("CAPACITY_EXCEEDED", "정원이 초과되었습니다", 409)

            # 4) users INSERT (pending_verification) + 인증코드 INSERT
            pw_hash = generate_password_hash(password)
            cur.execute(
                """INSERT INTO users (institution_id, email, password_hash, role, status)
                   VALUES (%s, %s, %s, %s, 'pending_verification')
                   RETURNING id""",
                (institution_id, email, pw_hash, role),
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
                """SELECT id, institution_id, role, is_special
                   FROM users
                   WHERE lower(email) = %s AND status = 'pending_verification'""",
                (email,),
            )
            user = cur.fetchone()
            if user is None:
                conn.rollback()
                return _err("USER_NOT_FOUND", "인증 대기 중인 사용자가 없습니다", 404)
            user_id, institution_id, role, is_special = user

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

            # 코드 일치 → TO 재검사 (동시성 방어): institutions row 잠금
            cur.execute(
                "SELECT max_users FROM institutions WHERE id = %s FOR UPDATE",
                (institution_id,),
            )
            inst = cur.fetchone()
            max_users = inst[0] if inst else None
            cur.execute(
                """SELECT COUNT(*) FROM users
                   WHERE institution_id = %s AND status = 'active'""",
                (institution_id,),
            )
            active_count = cur.fetchone()[0]
            if max_users is not None and active_count >= max_users:
                conn.rollback()
                return _err("CAPACITY_EXCEEDED", "정원이 초과되었습니다", 409)

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
            cur.execute(
                "UPDATE institution_rosters SET is_verified = TRUE WHERE institution_id = %s AND lower(email) = %s",
                (institution_id, email),
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
    resp.headers["Cache-Control"] = "no-store"
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
            cur.execute(
                """SELECT u.id, u.institution_id, u.role, u.is_special,
                          u.password_hash, u.status, u.locked_at, i.subscription_end
                   FROM users u
                   LEFT JOIN institutions i ON i.id = u.institution_id
                   WHERE lower(u.email) = %s
                   FOR UPDATE OF u""",
                (email,),
            )
            row = cur.fetchone()
            if row is None:
                conn.rollback()
                return _err("INVALID_CREDENTIALS", "이메일 또는 비밀번호가 올바르지 않습니다", 401)
            (user_id, institution_id, role, is_special,
             pw_hash, status, locked_at, subscription_end) = row

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

            # 구독 만료 검사 (is_special 계정은 만료 무관 허용)
            if not is_special and subscription_end is not None:
                today = datetime.now(timezone.utc).date()
                if subscription_end < today:
                    conn.rollback()
                    return _err("SUBSCRIPTION_EXPIRED", "구독이 만료되었습니다", 403)

            session_token, payload = _issue_token_payload(
                user_id, institution_id, role, is_special
            )
            # 기존 세션 무효화: session_token 덮어쓰기 (1기기 동시접속 제어)
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
