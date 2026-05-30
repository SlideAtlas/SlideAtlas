"""JWT 인증 데코레이터 + 토큰 유틸.

매 요청마다 JWT를 복호화하고 payload.session_token 을 DB users.session_token 과
대조한다. 새 기기 로그인으로 session_token 이 갱신되면 구 토큰은 즉시 무효(401).
"""
import os
import hmac
import time
import hashlib
import secrets
import functools
from datetime import datetime, timedelta, timezone

import jwt
from flask import request, g, jsonify, redirect

# psycopg2 미설치 환경(로컬 정적 분석 등)에서도 import 자체는 통과시킨다.
try:
    import psycopg2  # noqa: F401
    _PSYCOPG2_AVAILABLE = True
except ImportError:
    _PSYCOPG2_AVAILABLE = False

JWT_ALGO = "HS256"
JWT_EXP_HOURS = 24
COOKIE_NAME = "access_token"

TILE_TOKEN_TTL = 300  # 타일 접근 토큰 유효시간 5분 (CLAUDE.md §8 Presigned URL TTL 5분)


def _jwt_secret():
    # 시크릿은 .env/환경변수에서만 읽는다. 미설정 시 기동 단계에서 실패시켜
    # 약한 기본키로 토큰이 발급되는 사고를 막는다.
    secret = os.environ.get("JWT_SECRET_KEY")
    if not secret:
        raise RuntimeError("JWT_SECRET_KEY 미설정 — 환경변수/.env 확인")
    return secret


def encode_token(payload: dict) -> str:
    now = datetime.now(timezone.utc)
    body = dict(payload)
    body["iat"] = now
    body["exp"] = now + timedelta(hours=JWT_EXP_HOURS)
    return jwt.encode(body, _jwt_secret(), algorithm=JWT_ALGO)


def decode_token(token: str) -> dict:
    # 만료/변조 시 jwt 예외가 발생하며 호출부에서 401 처리한다.
    return jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALGO])


def _no_store(resp):
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _unauthorized(error: str, message: str):
    resp = jsonify({"success": False, "error": error, "message": message})
    resp.status_code = 401
    return _no_store(resp)


def _forbidden(error: str, message: str):
    resp = jsonify({"success": False, "error": error, "message": message})
    resp.status_code = 403
    return _no_store(resp)


def _csrf_failed():
    resp = jsonify({
        "success": False, "error": "CSRF_INVALID",
        "message": "CSRF 토큰이 유효하지 않습니다",
    })
    resp.status_code = 403
    return _no_store(resp)


# ─────────────────────────────────────────────
# 타일 접근 토큰 (HMAC-SHA256, 5분 TTL)
# 뷰어 페이지 로드 시 Flask가 발급, 타일 요청 시 ?t= 쿼리로 검증.
# ─────────────────────────────────────────────
def generate_tile_token(user_id: str, institution_id: str, slide_id: str) -> str:
    exp = int(time.time()) + TILE_TOKEN_TTL
    msg = f"{user_id}:{institution_id}:{slide_id}:{exp}"
    sig = hmac.new(_jwt_secret().encode(), msg.encode(), hashlib.sha256).hexdigest()
    return f"{exp}:{sig}"


def verify_tile_token(token: str, user_id: str, institution_id: str, slide_id: str) -> bool:
    try:
        exp_str, sig = token.split(":", 1)
        exp = int(exp_str)
        if exp < int(time.time()):
            return False
        msg = f"{user_id}:{institution_id}:{slide_id}:{exp}"
        expected = hmac.new(_jwt_secret().encode(), msg.encode(), hashlib.sha256).hexdigest()
        return secrets.compare_digest(sig, expected)
    except Exception:
        return False


def _get_db():
    # server_render.py 의 풀을 재사용한다 (순환 import 방지 위해 함수 내부 import).
    from server_render import get_db_conn, release_db_conn
    return get_db_conn, release_db_conn


def _authenticate():
    """JWT 복호화 + session_token DB 대조 + status 확인 후 g 에 사용자 컨텍스트 적재.

    성공 시 None 을 반환하고 g.* 를 채운다.
    실패 시 (error_code, message) 튜플을 반환한다.
    """
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return ("SESSION_EXPIRED", "다시 로그인하세요")
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        return ("SESSION_EXPIRED", "다시 로그인하세요")
    except jwt.InvalidTokenError:
        return ("INVALID_TOKEN", "다시 로그인하세요")

    user_id = payload.get("sub")   # str per PyJWT 2.8+ sub requirement
    token_session = payload.get("session_token")
    if user_id is None or not token_session:
        return ("INVALID_TOKEN", "다시 로그인하세요")

    if not _PSYCOPG2_AVAILABLE:
        return ("DB_UNAVAILABLE", "다시 로그인하세요")

    get_db_conn, release_db_conn = _get_db()
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            # subscription_end 매 요청 검사 (§12-4 ③) — 만료 후 활성 세션 차단
            cur.execute(
                """SELECT u.session_token, u.status, i.subscription_end
                   FROM users u
                   LEFT JOIN institutions i ON i.id = u.institution_id
                   WHERE u.id = %s""",
                (user_id,),
            )
            row = cur.fetchone()
    finally:
        release_db_conn(conn)

    if row is None:
        return ("SESSION_EXPIRED", "다시 로그인하세요")
    db_session, status, subscription_end = row
    # 동시접속 제어: DB의 최신 session_token 과 다르면 구 세션 → 즉시 만료.
    if db_session != token_session:
        return ("SESSION_EXPIRED", "다시 로그인하세요")
    if status != "active":
        return ("SESSION_EXPIRED", "다시 로그인하세요")
    # 구독 만료 검사: is_special 계정 제외, 매 요청마다 확인 (만료 후 24h 세션 악용 방지)
    if not payload.get("is_special") and subscription_end is not None:
        from datetime import date
        if subscription_end < date.today():
            return ("SUBSCRIPTION_EXPIRED", "구독이 만료되었습니다. 갱신 후 다시 로그인하세요")

    g.user_id = user_id
    g.institution_id = payload.get("institution_id")
    g.role = payload.get("role")
    g.is_special = payload.get("is_special", False)
    return None


def _csrf_ok():
    """상태 변경 메서드(POST/PUT/DELETE/PATCH)에 한해 더블서밋 CSRF 검증."""
    if request.method not in ("POST", "PUT", "DELETE", "PATCH"):
        return True
    client_csrf = request.headers.get("X-CSRF-Token")
    cookie_csrf = request.cookies.get("csrf_token")
    if not client_csrf or not cookie_csrf:
        return False
    return secrets.compare_digest(client_csrf, cookie_csrf)


def login_required(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        err = _authenticate()
        if err is not None:
            return _unauthorized(*err)

        # CSRF: 인증 통과 후 상태 변경 요청에 한해 더블서밋 검증.
        if not _csrf_ok():
            return _csrf_failed()

        resp = f(*args, **kwargs)
        try:
            return _no_store(resp)
        except AttributeError:
            # (body, status) 튜플 등 비-Response 반환은 그대로 통과.
            return resp

    return wrapper


def page_login_required(f):
    """HTML 페이지 보호용. 인증 실패 시 JSON 대신 랜딩(/)으로 redirect."""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        err = _authenticate()
        if err is not None:
            return redirect("/")
        return f(*args, **kwargs)

    return wrapper


def role_required(*roles):
    def decorator(f):
        @functools.wraps(f)
        @login_required
        def wrapper(*args, **kwargs):
            if g.get("role") not in roles:
                resp = jsonify({
                    "success": False,
                    "error": "FORBIDDEN",
                    "message": "권한이 없습니다",
                })
                resp.status_code = 403
                return _no_store(resp)
            return f(*args, **kwargs)
        return wrapper
    return decorator
