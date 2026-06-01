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

# 기관 관리자(포털) 전용 roster 센티넬 과목코드 (§9).
#   roster는 (institution_id, subject_code, email) 단위 독립 행이므로, 같은 이메일이
#   관리자 행(subject_code='__ADMIN__')과 과목 행('HST' 등)으로 충돌 없이 공존한다.
#   role='admin'은 시스템 권한(포털 접근), position(교수/조교 등)은 표시용으로 권한과 무관.
#   admin은 과목·좌석·구독에 묶이지 않으므로 인증 경로의 과목 구독 게이트에서 면제된다
#   (슬라이드 접근은 별도 단일 게이트 _slide_access_allowed가 과목 좌석으로 판정, §8).
ADMIN_ROSTER_SUBJECT = "__ADMIN__"

TILE_TOKEN_TTL = 300  # 타일 접근 토큰 유효시간 5분 (CLAUDE.md §8 Presigned URL TTL 5분)


def _today_kst():
    """KST(UTC+9) 기준 오늘 날짜. 날짜 경계(접근창·만료) 타임존 일관 처리(§16·§18 D10).
    Render 서버는 UTC이므로 date.today()/now(utc).date()는 자정 부근에 KST와 하루 어긋날 수 있다.
    """
    return (datetime.now(timezone.utc) + timedelta(hours=9)).date()


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
    resp.headers["Cache-Control"] = "no-store, no-cache"
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

    에러 코드 정의:
      TOKEN_INVALID        : 쿠키 없음·JWT 만료·수동 삭제·유저 미조회·세션 비활성
      SESSION_REVOKED      : 타 기기 로그인으로 DB의 session_token이 교체된 상태
      SUBSCRIPTION_EXPIRED : 기관 구독 만료 (is_special 계정 제외)
    """
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return ("TOKEN_INVALID", "다시 로그인하세요")  # 쿠키 없음·만료·수동 삭제
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        return ("TOKEN_INVALID", "다시 로그인하세요")  # JWT 만료
    except jwt.InvalidTokenError:
        return ("INVALID_TOKEN", "다시 로그인하세요")  # JWT 변조

    user_id = payload.get("sub")   # str per PyJWT 2.8+ sub requirement
    token_session = payload.get("session_token")
    if user_id is None or not token_session:
        return ("TOKEN_INVALID", "다시 로그인하세요")  # JWT payload 불완전

    if not _PSYCOPG2_AVAILABLE:
        return ("DB_UNAVAILABLE", "다시 로그인하세요")

    get_db_conn, release_db_conn = _get_db()
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            # [M2] 구독 만료 매 요청 검사 (§12-4 ③) — subscriptions(기관×과목) 모델 사용.
            # 해당 user의 (institution_id, subject_code)에 매칭되는 활성 구독의 최신 종료일을 본다.
            # [D4] NULL 폴백(기관 단위) 제거: subject_code는 가입 시 필수 채번되므로(§6-2) 정상 경로에
            #   NULL은 없다(§0-3·§0-4). 과목 축을 일급으로 양축(institution_id, subject_code) 매칭.
            # 반환 shape(session_token, status, subscription_end)는 변경하지 않는다(다운스트림·테스트 호환).
            # [C] 접근창 집행: 유효 구독 창(access_open_date <= today <= subscription_end)인
            #   active 구독만 본다. 미래 학기 구독이 미리 active여도 access_open_date 전에는
            #   subquery가 NULL → 만료 처리(통과 금지). today는 KST(§16·§18 D10).
            today = _today_kst()
            # [Codex#2/Gemini#4] JWT payload 신뢰 금지 — role·is_special·institution_id를 매 요청
            #   DB에서 다시 읽어 g에 주입한다(권위는 DB). 어드민이 DB에서 강등/특별계정 해제하면
            #   기존 JWT가 만료(24h) 전이라도 다음 요청에서 즉시 반영된다. 권한 변경 즉시 무효화가
            #   필요하면 session_token 회전(login·logout 경로)으로 구 토큰을 끊는다.
            cur.execute(
                """SELECT u.session_token, u.status, u.subject_code, u.special_expires_at,
                          u.role, u.is_special, u.institution_id,
                          (SELECT MAX(s.subscription_end)
                             FROM subscriptions s
                            WHERE s.institution_id = u.institution_id
                              AND s.subject_code = u.subject_code
                              AND s.status = 'active'
                              AND s.access_open_date <= %s
                              AND s.subscription_end >= %s)
                   FROM users u
                   WHERE u.id = %s""",
                (today, today, user_id),
            )
            row = cur.fetchone()
    finally:
        release_db_conn(conn)

    # ① 유저 미조회
    if row is None:
        return ("TOKEN_INVALID", "다시 로그인하세요")

    (db_session, status, subject_code, special_expires_at,
     db_role, db_is_special, db_institution_id, subscription_end) = row
    db_is_special = bool(db_is_special)

    # ② 세션 토큰 검증 — 반드시 아래 순서를 지킬 것 (순서 변경 금지)
    # token_session 존재 여부를 먼저 확인해야 None vs None 비교로
    # SESSION_REVOKED가 오발동하는 것을 막는다.
    if not token_session:
        return ("TOKEN_INVALID", "다시 로그인하세요")
    if db_session != token_session:
        # session에 토큰이 명확히 존재하는데 DB값과 다름 = 타 기기 로그인으로
        # DB의 session_token이 교체된 상태.
        return ("SESSION_REVOKED", "다른 기기에서 로그인되어 현재 세션이 무효화되었습니다")

    if status != "active":
        return ("TOKEN_INVALID", "다시 로그인하세요")  # 비활성·잠금 계정

    # ③ 만료 검사 (매 요청). today는 위에서 KST로 계산됨([C]).
    #    [Codex#2/Gemini#4] is_special·role은 payload가 아닌 DB 값(db_is_special·db_role)으로 판정.
    if db_is_special:
        # [B] 특별계정: 구독 만료는 면제하되 special_expires_at은 집행(§15-8).
        #     special_expires_at NULL(무기한)은 통과 — 비권장이나 허용. 경과 시 차단.
        if special_expires_at is not None and special_expires_at < today:
            return ("SUBSCRIPTION_EXPIRED", "특별계정 사용 기간이 만료되었습니다. 과 사무실에 문의하세요")
    elif db_role == "admin":
        # 기관 관리자(포털 전용): 과목 구독에 묶이지 않으므로 매 요청 구독 만료 게이트 면제.
        #   콘텐츠 노출은 넓히지 않는다 — 슬라이드/타일은 _slide_access_allowed가 과목 좌석으로
        #   별도 판정하며(§8), admin의 subject_code='__ADMIN__'는 어떤 슬라이드 과목과도 불일치한다.
        pass
    else:
        # §8 명문: "매칭 구독이 없거나 만료면 SUBSCRIPTION_EXPIRED."
        #   매칭 구독이 없으면(subscription_end IS NULL) 라이선스 격리상 차단(fail-closed, Codex FAIL1).
        if subscription_end is None or subscription_end < today:
            return ("SUBSCRIPTION_EXPIRED", "구독이 만료되었습니다. 과 사무실에 문의하세요")

    g.user_id = user_id
    # 권위는 DB — payload(JWT)가 아니라 방금 조회한 DB 값을 g에 적재한다.
    g.institution_id = db_institution_id
    g.subject_code = subject_code   # [A] 과목 격리 게이트의 기준 (사용자가 등록된 과목)
    g.role = db_role
    g.is_special = db_is_special
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
