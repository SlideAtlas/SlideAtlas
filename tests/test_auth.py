"""
SlideAtlas JWT 인증 pytest

NOTE: RDS PostgreSQL 접속 불가 예외 처리
======================================
RDS는 EC2 전용 VPC에 있어 로컬 머신에서 직접 접속 불가.
이 테스트는 unittest.mock.patch를 사용하여 DB 레이어를 mock하고
실제 Flask 애플리케이션과 라우트만 정상 작동하는지 검증한다.
- get_db_conn, release_db_conn을 mock으로 대체
- 이메일 발송도 mock
- JWT 토큰 생성/검증은 실제 코드 실행
- 데이터베이스 트랜잭션 동작은 시뮬레이션

이것은 CLAUDE.md의 멀티테넌시 및 보안 5대 체크리스트 중
"로그인 필수" 라우트의 데코레이터 검증 목적으로 설계됨.
"""

import pytest
import os
import secrets
import json
from datetime import datetime, timedelta, timezone
from unittest import mock
from unittest.mock import MagicMock, patch, call

# 환경변수 미리 설정 (JWT 토큰 생성용)
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-pytest"
os.environ["GMAIL_USER"] = "test@gmail.com"
os.environ["GMAIL_APP_PW"] = "test-app-pw"
os.environ["ADMIN_SECRET_KEY"] = "test-admin-secret-for-pytest"  # [#6] fail-closed: 미설정 시 기동 실패

# Flask 앱 로딩
from server_render import app
from auth.decorators import encode_token, decode_token, COOKIE_NAME, generate_tile_token


@pytest.fixture
def client():
    """Flask 테스트 클라이언트"""
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def mock_db():
    """DB 연결 mock"""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_conn.cursor.return_value.__exit__.return_value = None
    mock_conn.commit.return_value = None
    mock_conn.rollback.return_value = None
    mock_conn.autocommit = False
    
    return {
        "conn": mock_conn,
        "cursor": mock_cursor,
    }


def test_register_missing_fields(client, mock_db):
    """회원가입: 필수값 누락 → 400"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        
        resp = client.post("/api/auth/register", 
                          json={"email": "test@example.com"})
        
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "MISSING_FIELDS"
        assert data["success"] is False


def test_register_roster_mismatch(client, mock_db):
    """회원가입: 명단에 없는 이메일 → 403 ROSTER_MISMATCH"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        mock_db["cursor"].fetchone.return_value = None  # 명단 없음
        
        resp = client.post("/api/auth/register",
                          json={
                              "email": "unknown@test.com",
                              "password": "pass123",
                              "role": "student",
                              "institution_id": "YU"
                          })
        
        assert resp.status_code == 403
        data = resp.get_json()
        assert data["error"] == "ROSTER_MISMATCH"
        assert data["success"] is False


def test_register_email_exists(client, mock_db):
    """회원가입: 이미 가입된 이메일 → 409 EMAIL_EXISTS"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        mock_db["cursor"].fetchone.side_effect = [("HST",), (1,)]  # roster subject, 이메일 존재
        
        resp = client.post("/api/auth/register",
                          json={
                              "email": "existing@test.com",
                              "password": "pass123",
                              "role": "student",
                              "institution_id": "YU"
                          })
        
        assert resp.status_code == 409
        data = resp.get_json()
        assert data["error"] == "EMAIL_EXISTS"


def test_register_capacity_exceeded(client, mock_db):
    """회원가입: 정원 초과 → 409 CAPACITY_EXCEEDED"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"), \
         patch("auth.auth.send_verification_email"):
        mock_get_db.return_value = mock_db["conn"]
        mock_db["cursor"].fetchone.side_effect = [
            ("HST",),    # roster subject_code (명단 존재)
            None,        # 이메일 없음
            (10,),       # max_seats=10
            (10,),       # active_count=10
        ]
        
        resp = client.post("/api/auth/register",
                          json={
                              "email": "new@test.com",
                              "password": "pass123",
                              "role": "student",
                              "institution_id": "YU"
                          })
        
        assert resp.status_code == 409
        data = resp.get_json()
        assert data["error"] == "CAPACITY_EXCEEDED"


def test_register_success(client, mock_db):
    """회원가입: 성공 → 200"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"), \
         patch("auth.auth.send_verification_email") as mock_send:
        mock_get_db.return_value = mock_db["conn"]
        
        mock_db["cursor"].fetchone.side_effect = [
            ("HST",),    # roster subject_code (명단)
            None,        # 이메일 없음
            (100,),      # max_seats
            (5,),        # active_count
            (42,),       # INSERT users RETURNING id
        ]
        
        resp = client.post("/api/auth/register",
                          json={
                              "email": "new@test.com",
                              "password": "secure123",
                              "role": "student",
                              "institution_id": "YU"
                          })
        
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "인증코드" in data["data"]["message"]
        assert mock_send.called


def test_register_no_active_subscription_rejected(client, mock_db):
    """[#4] 구독 없는 roster 사용자 가입 거부 → 403 SUBSCRIPTION_INACTIVE (active 계정 미생성)."""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"), \
         patch("auth.auth.send_verification_email"):
        mock_get_db.return_value = mock_db["conn"]
        mock_db["cursor"].fetchone.side_effect = [
            ("HST",),    # roster subject_code (명단 존재)
            None,        # 이메일 없음
            None,        # 접근창 내 active 구독 없음 → 거부
        ]
        resp = client.post("/api/auth/register",
                          json={"email": "new@test.com", "password": "pass123",
                                "role": "student", "institution_id": "YU"})
        assert resp.status_code == 403
        assert resp.get_json()["error"] == "SUBSCRIPTION_INACTIVE"


def test_verify_email_no_active_subscription_rejected(client, mock_db):
    """[#4] 구독 없는 사용자 인증 거부 → 403 SUBSCRIPTION_INACTIVE (active 전환 금지)."""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        mock_db["cursor"].fetchone.side_effect = [
            (1, "YU", "student", False, "HST"),   # user
            (1, "123456", datetime.now(timezone.utc) + timedelta(minutes=5), False, 0),  # ev
            None,   # 접근창 내 active 구독 없음 → 거부
        ]
        resp = client.post("/api/auth/verify-email",
                          json={"email": "test@example.com", "code": "123456"})
        assert resp.status_code == 403
        assert resp.get_json()["error"] == "SUBSCRIPTION_INACTIVE"


def test_verify_email_code_expired(client, mock_db):
    """인증코드 확인: 만료된 코드 → 410 CODE_EXPIRED"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        
        mock_db["cursor"].fetchone.side_effect = [
            (1, "YU", "student", False, "HST"),
            (
                1, "123456",
                datetime.now(timezone.utc) - timedelta(minutes=20),
                False, 0
            )
        ]
        
        resp = client.post("/api/auth/verify-email",
                          json={
                              "email": "test@example.com",
                              "code": "123456"
                          })
        
        assert resp.status_code == 410
        data = resp.get_json()
        assert data["error"] == "CODE_EXPIRED"


def test_verify_email_too_many_attempts(client, mock_db):
    """인증코드 확인: 시도 초과 → 429 TOO_MANY_ATTEMPTS"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        
        mock_db["cursor"].fetchone.side_effect = [
            (1, "YU", "student", False, "HST"),
            (
                1, "123456",
                datetime.now(timezone.utc) + timedelta(minutes=5),
                False, 5
            )
        ]
        
        resp = client.post("/api/auth/verify-email",
                          json={
                              "email": "test@example.com",
                              "code": "999999"
                          })
        
        assert resp.status_code == 429
        data = resp.get_json()
        assert data["error"] == "TOO_MANY_ATTEMPTS"


def test_verify_email_code_mismatch(client, mock_db):
    """인증코드 확인: 잘못된 코드 → 400 CODE_MISMATCH (remaining 필드 포함)"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        
        mock_db["cursor"].fetchone.side_effect = [
            (1, "YU", "student", False, "HST"),
            (
                1, "123456",
                datetime.now(timezone.utc) + timedelta(minutes=5),
                False, 3
            ),
            (0, None),   # _check_and_increment_failed: failed_attempts, failed_window_start
        ]

        resp = client.post("/api/auth/verify-email",
                          json={
                              "email": "test@example.com",
                              "code": "999999"
                          })

        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "CODE_MISMATCH"
        assert "remaining" in data
        assert data["remaining"] == 1


def test_verify_email_code_mismatch_last_attempt(client, mock_db):
    """인증코드: attempt_count=4일 때 불일치 → remaining=0"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        
        mock_db["cursor"].fetchone.side_effect = [
            (1, "YU", "student", False, "HST"),
            (
                1, "123456",
                datetime.now(timezone.utc) + timedelta(minutes=5),
                False, 4
            ),
            (4, None),   # _check_and_increment_failed: 4 previous failures, new window
        ]

        resp = client.post("/api/auth/verify-email",
                          json={
                              "email": "test@example.com",
                              "code": "wrong"
                          })
        
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["remaining"] == 0


def test_verify_email_capacity_exceeded_at_verify(client, mock_db):
    """인증 단계에서 TO 재검사 → 409 CAPACITY_EXCEEDED"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        
        mock_db["cursor"].fetchone.side_effect = [
            (1, "YU", "student", False, "HST"),
            (
                1, "123456",
                datetime.now(timezone.utc) + timedelta(minutes=5),
                False, 0
            ),
            (100,),
            (100,),
        ]
        
        resp = client.post("/api/auth/verify-email",
                          json={
                              "email": "test@example.com",
                              "code": "123456"
                          })
        
        assert resp.status_code == 409
        data = resp.get_json()
        assert data["error"] == "CAPACITY_EXCEEDED"


def test_verify_email_success(client, mock_db):
    """인증코드 확인: 성공 → 200 (쿠키 + csrf_token)"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        
        mock_db["cursor"].fetchone.side_effect = [
            (1, "YU", "student", False, "HST"),
            (
                1, "123456",
                datetime.now(timezone.utc) + timedelta(minutes=5),
                False, 0
            ),
            (100,),
            (5,),
        ]
        
        resp = client.post("/api/auth/verify-email",
                          json={
                              "email": "test@example.com",
                              "code": "123456"
                          })
        
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "csrf_token" in data["data"]
        
        cookies = resp.headers.getlist("Set-Cookie")
        assert any(COOKIE_NAME in c for c in cookies)


def test_login_invalid_credentials_user_not_found(client, mock_db):
    """로그인: 존재하지 않는 이메일 → 401"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        mock_db["cursor"].fetchone.return_value = None
        
        resp = client.post("/api/auth/login",
                          json={
                              "email": "nonexistent@test.com",
                              "password": "pass123"
                          })
        
        assert resp.status_code == 401
        data = resp.get_json()
        assert data["error"] == "INVALID_CREDENTIALS"


def test_login_invalid_credentials_wrong_password(client, mock_db):
    """로그인: 비밀번호 불일치 → 401"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        
        from werkzeug.security import generate_password_hash
        correct_hash = generate_password_hash("correct_password")
        
        # Login query: id, institution_id, role, is_special, pw_hash, status, locked_at, subscription_end
        # Then _check_and_increment_failed queries: failed_attempts, failed_window_start
        mock_db["cursor"].fetchone.side_effect = [
            (1, "YU", "student", False, correct_hash, "active", None, None,
             datetime.now(timezone.utc) + timedelta(days=365)),
            (0, None),  # _check_and_increment_failed
        ]

        resp = client.post("/api/auth/login",
                          json={
                              "email": "test@example.com",
                              "password": "wrong_password"
                          })

        assert resp.status_code == 401
        data = resp.get_json()
        assert data["error"] == "INVALID_CREDENTIALS"


def test_login_email_not_verified(client, mock_db):
    """로그인: 미인증 계정 → 403 EMAIL_NOT_VERIFIED"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        
        from werkzeug.security import generate_password_hash
        
        mock_db["cursor"].fetchone.return_value = (
            1, "YU", "student", False,
            generate_password_hash("password"),
            "pending_verification",
            None,  # locked_at
            None,  # special_expires_at
            datetime.now(timezone.utc) + timedelta(days=365)
        )
        
        resp = client.post("/api/auth/login",
                          json={
                              "email": "test@example.com",
                              "password": "password"
                          })
        
        assert resp.status_code == 403
        data = resp.get_json()
        assert data["error"] == "EMAIL_NOT_VERIFIED"


def test_login_subscription_expired_regular_user(client, mock_db):
    """로그인: 구독 만료 (is_special=False) → 403"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        
        from werkzeug.security import generate_password_hash
        
        mock_db["cursor"].fetchone.return_value = (
            1, "YU", "student", False,
            generate_password_hash("password"),
            "active",
            None,  # locked_at
            None,  # special_expires_at
            datetime.now(timezone.utc).date() - timedelta(days=1)
        )

        resp = client.post("/api/auth/login",
                          json={
                              "email": "test@example.com",
                              "password": "password"
                          })

        assert resp.status_code == 403
        data = resp.get_json()
        assert data["error"] == "SUBSCRIPTION_EXPIRED"


def test_login_subscription_expired_but_is_special(client, mock_db):
    """로그인: 구독 만료이지만 is_special=True → 200"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        
        from werkzeug.security import generate_password_hash
        
        mock_db["cursor"].fetchone.return_value = (
            1, "YU", "student", True,
            generate_password_hash("password"),
            "active",
            None,  # locked_at
            None,  # special_expires_at
            datetime.now(timezone.utc).date() - timedelta(days=1)
        )
        
        resp = client.post("/api/auth/login",
                          json={
                              "email": "test@example.com",
                              "password": "password"
                          })
        
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True


def test_login_success(client, mock_db):
    """로그인: 성공 → 200"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        
        from werkzeug.security import generate_password_hash
        
        mock_db["cursor"].fetchone.return_value = (
            1, "YU", "student", False,
            generate_password_hash("password"),
            "active",
            None,  # locked_at
            None,  # special_expires_at
            datetime.now(timezone.utc).date() + timedelta(days=365)
        )

        resp = client.post("/api/auth/login",
                          json={
                              "email": "test@example.com",
                              "password": "password"
                          })

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "csrf_token" in data["data"]
        
        cookies = resp.headers.getlist("Set-Cookie")
        assert any(COOKIE_NAME in c for c in cookies)


def test_login_missing_fields(client, mock_db):
    """로그인: 필수값 누락 → 400"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        
        resp = client.post("/api/auth/login",
                          json={"email": "test@example.com"})
        
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "MISSING_FIELDS"


def test_login_required_no_cookie(client):
    """login_required: 쿠키 없음 → 401 TOKEN_INVALID (SESSION_REVOKED 오발동 없음)"""
    resp = client.get("/api/auth/me")

    assert resp.status_code == 401
    data = resp.get_json()
    assert data["error"] == "TOKEN_INVALID"
    # SESSION_REVOKED가 아님을 명시적으로 검증
    assert data["error"] != "SESSION_REVOKED"


def test_login_required_invalid_token(client):
    """login_required: 유효하지 않은 JWT → 401"""
    client.set_cookie(COOKIE_NAME, "invalid.jwt.token")
    
    resp = client.get("/api/auth/me")
    
    assert resp.status_code == 401


def test_login_required_expired_token(client):
    """login_required: 만료된 JWT → 401 TOKEN_INVALID"""
    with patch("auth.decorators.decode_token") as mock_decode:
        import jwt
        mock_decode.side_effect = jwt.ExpiredSignatureError()

        client.set_cookie(COOKIE_NAME, "dummy-token")
        resp = client.get("/api/auth/me")

        assert resp.status_code == 401
        data = resp.get_json()
        assert data["error"] == "TOKEN_INVALID"


def test_login_required_session_token_mismatch(client, mock_db):
    """login_required: DB session_token 불일치 (다른 기기 로그인) → 401 SESSION_REVOKED"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]

        payload = {
            "sub": "1",
            "institution_id": "YU",
            "role": "student",
            "session_token": "old-session-token",
            "is_special": False,
        }
        token = encode_token(payload)
        client.set_cookie(COOKIE_NAME, token)

        mock_db["cursor"].fetchone.return_value = (
            # session_token, status, subject_code, special_expires_at, role, is_special, institution_id, subscription_end
            "new-session-token", "active", "HST", None, "student", False, "YU", None
        )

        resp = client.get("http://localhost/api/auth/me")

        assert resp.status_code == 401
        data = resp.get_json()
        assert data["error"] == "SESSION_REVOKED"


def test_login_required_pending_verification(client, mock_db):
    """login_required: 유저 status='pending_verification' → 401"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        
        payload = {
            "sub": "1",
            "institution_id": "YU",
            "role": "student",
            "session_token": "valid-session-123",
            "is_special": False,
        }
        token = encode_token(payload)
        client.set_cookie(COOKIE_NAME, token)
        
        mock_db["cursor"].fetchone.return_value = (
            "valid-session-123", "pending_verification", "HST", None, "student", False, "YU", None
        )

        resp = client.get("/api/auth/me")
        
        assert resp.status_code == 401


def test_login_required_success(client, mock_db):
    """login_required: 유효한 JWT + DB 일치 → 200"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        
        payload = {
            "sub": "1",
            "institution_id": "YU",
            "role": "student",
            "session_token": "valid-session-123",
            "is_special": False,
        }
        token = encode_token(payload)
        client.set_cookie(COOKIE_NAME, token)

        mock_db["cursor"].fetchone.side_effect = [
            # fail-closed(§8): 매칭 구독 없으면(None) SUBSCRIPTION_EXPIRED → 유효 구독일 제공
            ("valid-session-123", "active", "HST", None, "student", False, "YU",
             datetime.now(timezone.utc).date() + timedelta(days=365)),   # _authenticate: +role,is_special,institution_id
            (1, "test@example.com", "student", "YU", False, "active", None)  # me()
        ]

        # Werkzeug 3.x: set_cookie requires full URL for domain matching
        resp = client.get("http://localhost/api/auth/me")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["user_id"] == 1


def test_response_headers_cache_control(client, mock_db):
    """응답 헤더: 모든 인증 응답에 Cache-Control: no-store"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        
        mock_db["cursor"].fetchone.return_value = None
        resp = client.post("/api/auth/register",
                          json={
                              "email": "test@example.com",
                              "password": "pass",
                              "role": "student",
                              "institution_id": "YU"
                          })
        assert "Cache-Control" in resp.headers
        assert "no-store" in resp.headers["Cache-Control"]
        
        mock_db["cursor"].fetchone.return_value = None
        resp = client.post("/api/auth/login",
                          json={
                              "email": "test@example.com",
                              "password": "pass"
                          })
        assert "Cache-Control" in resp.headers
        assert "no-store" in resp.headers["Cache-Control"]


def test_logout_success(client, mock_db):
    """로그아웃: 성공 → 200, 쿠키 삭제"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        
        payload = {
            "sub": "1",
            "institution_id": "YU",
            "role": "student",
            "session_token": "valid-session-123",
            "is_special": False,
        }
        token = encode_token(payload)
        csrf_value = "test-csrf-token-1234"
        client.set_cookie(COOKIE_NAME, token)
        client.set_cookie("csrf_token", csrf_value)

        mock_db["cursor"].fetchone.return_value = (
            # fail-closed(§8): 유효 구독일 제공해 _authenticate 통과 → logout 도달
            "valid-session-123", "active", "HST", None, "student", False, "YU",
            datetime.now(timezone.utc).date() + timedelta(days=365)   # +role,is_special,institution_id
        )

        # Werkzeug 3.x: full URL for domain matching; X-CSRF-Token required by login_required
        resp = client.post(
            "http://localhost/api/auth/logout",
            headers={"X-CSRF-Token": csrf_value},
        )

        assert resp.status_code == 200
        assert any("Delete" in c or "Max-Age=0" in c
                  for c in resp.headers.getlist("Set-Cookie"))


# ─────────────────────────────────────────────
# 계정 잠금 테스트
# ─────────────────────────────────────────────

def test_login_account_locked(client, mock_db):
    """로그인: 잠긴 계정 → 403 ACCOUNT_LOCKED"""
    from werkzeug.security import generate_password_hash
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]

        locked_at = datetime.now(timezone.utc) - timedelta(hours=1)  # 잠근지 1시간
        mock_db["cursor"].fetchone.return_value = (
            1, "YU", "student", False,
            generate_password_hash("password"),
            "locked",
            locked_at,  # locked_at 1시간 전 (24h 미경과)
            None,  # special_expires_at
            datetime.now(timezone.utc).date() + timedelta(days=365)
        )

        resp = client.post("/api/auth/login",
                          json={"email": "test@example.com", "password": "password"})

        assert resp.status_code == 403
        data = resp.get_json()
        assert data["error"] == "ACCOUNT_LOCKED"


def test_login_account_auto_unlock(client, mock_db):
    """로그인: 잠긴 계정이지만 24시간 경과 → 자동 해제 후 로그인 성공"""
    from werkzeug.security import generate_password_hash
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]

        locked_at = datetime.now(timezone.utc) - timedelta(hours=25)  # 25시간 전 잠금
        mock_db["cursor"].fetchone.return_value = (
            1, "YU", "student", False,
            generate_password_hash("password"),
            "locked",
            locked_at,
            None,  # special_expires_at
            datetime.now(timezone.utc).date() + timedelta(days=365)
        )

        resp = client.post("/api/auth/login",
                          json={"email": "test@example.com", "password": "password"})

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True


def test_login_wrong_password_locks_account(client, mock_db):
    """로그인: 10회 비밀번호 오류 누적 → ACCOUNT_LOCKED 반환"""
    from werkzeug.security import generate_password_hash
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]

        correct_hash = generate_password_hash("correct")
        window_start = datetime.now(timezone.utc) - timedelta(hours=1)

        # Login query + _check_and_increment_failed: already at 9, new attempt = 10 → lock
        mock_db["cursor"].fetchone.side_effect = [
            (1, "YU", "student", False, correct_hash, "active", None, None,
             datetime.now(timezone.utc).date() + timedelta(days=365)),
            (9, window_start),   # failed_attempts=9, window still active → new=10 → locked
        ]

        resp = client.post("/api/auth/login",
                          json={"email": "test@example.com", "password": "wrong"})

        assert resp.status_code == 403
        data = resp.get_json()
        assert data["error"] == "ACCOUNT_LOCKED"


def test_verify_email_code_mismatch_triggers_lock(client, mock_db):
    """인증코드 오입력: 카운터 누적으로 계정 잠금 → ACCOUNT_LOCKED"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]

        window_start = datetime.now(timezone.utc) - timedelta(hours=1)
        mock_db["cursor"].fetchone.side_effect = [
            (1, "YU", "student", False, "HST"),
            (1, "123456", datetime.now(timezone.utc) + timedelta(minutes=5), False, 2),
            (9, window_start),   # 9 previous fails → 10th → locked
        ]

        resp = client.post("/api/auth/verify-email",
                          json={"email": "test@example.com", "code": "wrong"})

        assert resp.status_code == 403
        data = resp.get_json()
        assert data["error"] == "ACCOUNT_LOCKED"


# ─────────────────────────────────────────────
# 인증코드 재발송 테스트
# ─────────────────────────────────────────────

def test_resend_code_success(client, mock_db):
    """인증코드 재발송: 성공 → 200"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"), \
         patch("auth.auth.send_verification_email") as mock_send:
        mock_get_db.return_value = mock_db["conn"]

        now = datetime.now(timezone.utc)
        mock_db["cursor"].fetchone.side_effect = [
            (1, "pending_verification"),                      # user lookup
            (now - timedelta(minutes=5),),                   # last_sent (5분 전, 쿨다운 통과)
            (1,),                                             # daily_count=1 (한도 미달)
        ]

        resp = client.post("/api/auth/resend-code",
                          json={"email": "test@example.com"})

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert mock_send.called


def test_resend_code_cooldown(client, mock_db):
    """인증코드 재발송: 1분 이내 재발송 → 429 RESEND_TOO_SOON"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]

        now = datetime.now(timezone.utc)
        mock_db["cursor"].fetchone.side_effect = [
            (1, "pending_verification"),
            (now - timedelta(seconds=30),),   # 30초 전 발송 → 쿨다운
        ]

        resp = client.post("/api/auth/resend-code",
                          json={"email": "test@example.com"})

        assert resp.status_code == 429
        data = resp.get_json()
        assert data["error"] == "RESEND_TOO_SOON"


def test_resend_code_daily_limit(client, mock_db):
    """인증코드 재발송: 24시간 5회 초과 → 429 RESEND_LIMIT_EXCEEDED"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]

        now = datetime.now(timezone.utc)
        mock_db["cursor"].fetchone.side_effect = [
            (1, "pending_verification"),
            (now - timedelta(minutes=5),),   # 쿨다운 통과
            (5,),                            # daily_count=5 → 한도 초과
        ]

        resp = client.post("/api/auth/resend-code",
                          json={"email": "test@example.com"})

        assert resp.status_code == 429
        data = resp.get_json()
        assert data["error"] == "RESEND_LIMIT_EXCEEDED"


def test_resend_code_locked_account_blocked(client, mock_db):
    """인증코드 재발송: 잠긴 계정 → 403 ACCOUNT_LOCKED"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]

        mock_db["cursor"].fetchone.return_value = (1, "locked")

        resp = client.post("/api/auth/resend-code",
                          json={"email": "test@example.com"})

        assert resp.status_code == 403
        data = resp.get_json()
        assert data["error"] == "ACCOUNT_LOCKED"


def test_resend_code_missing_email(client, mock_db):
    """인증코드 재발송: 이메일 누락 → 400 MISSING_FIELDS"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]

        resp = client.post("/api/auth/resend-code", json={})

        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "MISSING_FIELDS"


# ─────────────────────────────────────────────
# CSRF 검증 테스트
# ─────────────────────────────────────────────

def test_csrf_missing_header_returns_403(client, mock_db):
    """login_required POST: X-CSRF-Token 헤더 없음 → 403 CSRF_INVALID"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]

        payload = {"sub": "1", "institution_id": "YU", "role": "student",
                   "session_token": "sess123", "is_special": False}
        token = encode_token(payload)
        client.set_cookie(COOKIE_NAME, token)
        client.set_cookie("csrf_token", "some-csrf-token")

        # fail-closed(§8): 유효 구독일 제공해 _authenticate 통과 → CSRF 검사 도달
        mock_db["cursor"].fetchone.return_value = (
            "sess123", "active", "HST", None, "student", False, "YU",
            datetime.now(timezone.utc).date() + timedelta(days=365))

        # No X-CSRF-Token header → 403
        resp = client.post("http://localhost/api/auth/logout")

        assert resp.status_code == 403
        data = resp.get_json()
        assert data["error"] == "CSRF_INVALID"


def test_csrf_mismatched_token_returns_403(client, mock_db):
    """login_required POST: X-CSRF-Token 헤더와 쿠키 불일치 → 403 CSRF_INVALID"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]

        payload = {"sub": "1", "institution_id": "YU", "role": "student",
                   "session_token": "sess123", "is_special": False}
        token = encode_token(payload)
        client.set_cookie(COOKIE_NAME, token)
        client.set_cookie("csrf_token", "correct-csrf-token")

        # fail-closed(§8): 유효 구독일 제공해 _authenticate 통과 → CSRF 검사 도달
        mock_db["cursor"].fetchone.return_value = (
            "sess123", "active", "HST", None, "student", False, "YU",
            datetime.now(timezone.utc).date() + timedelta(days=365))

        resp = client.post(
            "http://localhost/api/auth/logout",
            headers={"X-CSRF-Token": "wrong-csrf-token"},
        )

        assert resp.status_code == 403
        data = resp.get_json()
        assert data["error"] == "CSRF_INVALID"


# ─────────────────────────────────────────────
# Admin CSRF 검증 테스트
# ─────────────────────────────────────────────

def test_admin_csrf_required_no_header(client, mock_db):
    """Admin API POST: X-CSRF-Token 없음 → 403 (현 계약: admin_users DB + session['admin_user_id'])"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        # _get_admin_user: SELECT id, role, name, status, session_token FROM admin_users
        mock_db["cursor"].fetchone.return_value = (1, "super_admin", "Admin", "active", "admin-sess-tok")

        with client.session_transaction() as sess:
            sess['admin_user_id'] = 1
            sess['admin_csrf_token'] = 'test-admin-csrf-123'
            sess['admin_session_token'] = 'admin-sess-tok'

        resp = client.post('/admin/api/slide',
                           json={"id": "TEST-001", "title_ko": "테스트"},
                           headers={'Content-Type': 'application/json'})
        assert resp.status_code == 403
        data = resp.get_json()
        assert data.get('ok') is False or 'CSRF' in str(data)


def test_admin_csrf_required_wrong_token(client, mock_db):
    """Admin API POST: X-CSRF-Token 불일치 → 403 (현 계약: admin_users DB)"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        mock_db["cursor"].fetchone.return_value = (1, "super_admin", "Admin", "active", "admin-sess-tok")

        with client.session_transaction() as sess:
            sess['admin_user_id'] = 1
            sess['admin_csrf_token'] = 'correct-token'
            sess['admin_session_token'] = 'admin-sess-tok'

        resp = client.post('/admin/api/slide',
                           json={"id": "TEST-001"},
                           headers={
                               'Content-Type': 'application/json',
                               'X-CSRF-Token': 'wrong-token',
                           })
        assert resp.status_code == 403


def test_admin_csrf_delete_no_header(client, mock_db):
    """Admin API DELETE: X-CSRF-Token 없음 → 403 (현 계약: admin_users DB)"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        mock_db["cursor"].fetchone.return_value = (1, "super_admin", "Admin", "active", "admin-sess-tok")

        with client.session_transaction() as sess:
            sess['admin_user_id'] = 1
            sess['admin_csrf_token'] = 'test-csrf'
            sess['admin_session_token'] = 'admin-sess-tok'

        resp = client.delete('/admin/api/slide/TEST-001')
        assert resp.status_code == 403


# ─────────────────────────────────────────────
# 401 에러 코드 세분화 신규 테스트
# ─────────────────────────────────────────────

def test_token_invalid_no_cookie(client):
    """쿠키 없는 요청 → TOKEN_INVALID (SESSION_REVOKED 오발동 없음)"""
    resp = client.get("/api/auth/me")

    assert resp.status_code == 401
    data = resp.get_json()
    assert data["error"] == "TOKEN_INVALID"
    # 핵심: SESSION_REVOKED가 반환되어서는 안 됨
    assert data["error"] != "SESSION_REVOKED"


def test_session_revoked_on_db_mismatch(client, mock_db):
    """유효한 쿠키이지만 DB session_token과 불일치 → SESSION_REVOKED"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]

        payload = {
            "sub": "1",
            "institution_id": "YU",
            "role": "student",
            "session_token": "old-token-from-jwt",
            "is_special": False,
        }
        token = encode_token(payload)
        # Werkzeug 3.x: set_cookie + full URL for cookie delivery
        client.set_cookie(COOKIE_NAME, token)

        # DB에는 다른 session_token (다른 기기에서 로그인)
        mock_db["cursor"].fetchone.return_value = (
            "different-token-in-db", "active", "HST", None, "student", False, "YU", None
        )

        resp = client.get("http://localhost/api/auth/me")

        assert resp.status_code == 401
        data = resp.get_json()
        assert data["error"] == "SESSION_REVOKED"
        assert data["error"] != "TOKEN_INVALID"


def test_subscription_expired_returns_401(client, mock_db):
    """active 계정, 구독 만료 → SUBSCRIPTION_EXPIRED (401)"""
    from datetime import date, timedelta
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]

        payload = {
            "sub": "1",
            "institution_id": "YU",
            "role": "student",
            "session_token": "valid-sess",
            "is_special": False,
        }
        token = encode_token(payload)
        client.set_cookie(COOKIE_NAME, token)

        expired_date = date.today() - timedelta(days=1)
        mock_db["cursor"].fetchone.return_value = (
            "valid-sess", "active", "HST", None, "student", False, "YU", expired_date
        )

        resp = client.get("http://localhost/api/auth/me")

        assert resp.status_code == 401
        data = resp.get_json()
        assert data["error"] == "SUBSCRIPTION_EXPIRED"


def test_before_access_open_date_blocks(client, mock_db):
    """★#3: 미래 학기 구독이 active여도 access_open_date 전이면 접근 차단.

    접근창 필터(access_open_date<=today<=subscription_end)에 걸려 subquery가 NULL을 반환 →
    매칭 유효 구독 없음 → SUBSCRIPTION_EXPIRED (일반 사용자).
    """
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]

        payload = {
            "sub": "1", "institution_id": "YU", "role": "student",
            "session_token": "valid-sess", "is_special": False,
        }
        client.set_cookie(COOKIE_NAME, encode_token(payload))
        # 접근창 밖 → subquery NULL: (session, status, subject, special_expires_at, role, is_special, institution_id, subscription_end=None)
        mock_db["cursor"].fetchone.return_value = (
            "valid-sess", "active", "HST", None, "student", False, "YU", None
        )

        resp = client.get("http://localhost/api/auth/me")

        assert resp.status_code == 401
        assert resp.get_json()["error"] == "SUBSCRIPTION_EXPIRED"


def test_login_before_access_open_date_blocks(client, mock_db):
    """★#3(login): access_open_date 이전(유효 구독창 없음) → 403 SUBSCRIPTION_EXPIRED."""
    from werkzeug.security import generate_password_hash
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        # 접근창 밖 → subquery NULL(subscription_end=None)
        mock_db["cursor"].fetchone.return_value = (
            1, "YU", "student", False,
            generate_password_hash("password"),
            "active", None,
            None,   # special_expires_at
            None    # subscription_end (접근창 밖 → NULL)
        )

        resp = client.post("/api/auth/login",
                          json={"email": "test@example.com", "password": "password"})

        assert resp.status_code == 403
        assert resp.get_json()["error"] == "SUBSCRIPTION_EXPIRED"


def test_special_expires_at_past_blocks(client, mock_db):
    """★#5: special_expires_at 경과한 특별계정 → 차단 (SUBSCRIPTION_EXPIRED)."""
    from datetime import date, timedelta
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]

        payload = {
            "sub": "1", "institution_id": "YU", "role": "student",
            "session_token": "valid-sess", "is_special": True,
        }
        client.set_cookie(COOKIE_NAME, encode_token(payload))
        # is_special이지만 special_expires_at이 과거 → 차단. subscription_end는 무관(None).
        # g.is_special은 DB값으로 판정(Codex#2) → 행의 is_special=True.
        mock_db["cursor"].fetchone.return_value = (
            "valid-sess", "active", None, date.today() - timedelta(days=1),
            "student", True, "YU", None
        )

        resp = client.get("http://localhost/api/auth/me")

        assert resp.status_code == 401
        assert resp.get_json()["error"] == "SUBSCRIPTION_EXPIRED"


def test_special_expires_at_null_passes(client, mock_db):
    """special_expires_at=NULL(무기한) 특별계정 → 통과 (§15-8 비권장이나 허용)."""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]

        payload = {
            "sub": "1", "institution_id": "YU", "role": "admin",
            "session_token": "valid-sess", "is_special": True,
        }
        client.set_cookie(COOKIE_NAME, encode_token(payload))
        mock_db["cursor"].fetchone.side_effect = [
            ("valid-sess", "active", None, None, "admin", True, "YU", None),   # _authenticate: is_special=True, special_expires_at=None → 통과
            (1, "admin@test.com", "admin", "YU", True, "active", None),  # me()
        ]

        resp = client.get("http://localhost/api/auth/me")

        assert resp.status_code == 200
        assert resp.get_json()["success"] is True


def test_login_special_expires_at_past_blocks(client, mock_db):
    """★#5(login): special_expires_at 경과 특별계정 로그인 → 403 SUBSCRIPTION_EXPIRED."""
    from werkzeug.security import generate_password_hash
    from datetime import date, timedelta
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        # is_special=True, special_expires_at 과거, subscription_end None
        mock_db["cursor"].fetchone.return_value = (
            1, "YU", "student", True,
            generate_password_hash("password"),
            "active", None,
            date.today() - timedelta(days=1),  # special_expires_at 과거
            None                                # subscription_end
        )

        resp = client.post("/api/auth/login",
                          json={"email": "special@test.com", "password": "password"})

        assert resp.status_code == 403
        assert resp.get_json()["error"] == "SUBSCRIPTION_EXPIRED"


def test_is_special_subscription_expired_passes(client, mock_db):
    """is_special=True 계정, 구독 만료여도 정상 통과"""
    from datetime import date, timedelta
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]

        payload = {
            "sub": "1",
            "institution_id": "YU",
            "role": "admin",
            "session_token": "valid-sess",
            "is_special": True,
        }
        token = encode_token(payload)
        client.set_cookie(COOKIE_NAME, token)

        expired_date = date.today() - timedelta(days=30)
        mock_db["cursor"].fetchone.side_effect = [
            ("valid-sess", "active", None, None, "admin", True, "YU", expired_date),   # _authenticate: is_special=True → 구독만료 면제
            (1, "admin@test.com", "admin", "YU", True, "active", None),  # me()
        ]

        resp = client.get("http://localhost/api/auth/me")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True


def test_tile_token_invalid_returns_correct_code(client, mock_db):
    """타일 토큰 검증 실패 → TILE_TOKEN_INVALID (SESSION_REVOKED·SUBSCRIPTION_EXPIRED 아님)"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"), \
         patch("server_render.get_slide_institution") as mock_inst, \
         patch("server_render._institution_subject_access", return_value=True):
        mock_get_db.return_value = mock_db["conn"]
        # 단일 게이트 계약: (institution_id, subject_code, deploy_status, conversion_status)
        mock_inst.return_value = ("SA", "HST", "deployed", "ready")

        payload = {
            "sub": "1",
            "institution_id": "YU",
            "role": "student",
            "session_token": "valid-sess",
            "is_special": False,
        }
        token = encode_token(payload)
        # Werkzeug 3.x: set_cookie + full URL for cookie delivery
        client.set_cookie(COOKIE_NAME, token)

        # fail-closed(§8): 유효 구독일 + 과목(HST)이 슬라이드 과목과 일치 → 게이트 통과 → 타일토큰 검사 도달
        mock_db["cursor"].fetchone.return_value = (
            "valid-sess", "active", "HST", None, "student", False, "YU",
            datetime.now(timezone.utc).date() + timedelta(days=365)
        )

        # 타일 토큰 없이 DZI 접근 (?t= 미포함)
        resp = client.get("http://localhost/dzi/SA-HST-001.dzi")

        assert resp.status_code == 401
        data = resp.get_json()
        assert data["error"] == "TILE_TOKEN_INVALID"
        # 프론트 인터셉터가 로그인 세션 에러로 오판하지 않도록 구분
        assert data["error"] not in ("SESSION_REVOKED", "SUBSCRIPTION_EXPIRED", "TOKEN_INVALID")


# ─────────────────────────────────────────────
# 슬라이드 접근 단일 게이트 (과목 구독 기준 — 기관일치 화석 제거)
# ─────────────────────────────────────────────

def _gate_setup(client, mock_db, *, subject_code, is_special=False,
                institution_id="YU", user_id="1"):
    """일반/특별 사용자 로그인 컨텍스트 구성. _authenticate가 g.subject_code를 세팅하도록 mock."""
    payload = {
        "sub": user_id, "institution_id": institution_id, "role": "student",
        "session_token": "valid-sess", "is_special": is_special,
    }
    client.set_cookie(COOKIE_NAME, encode_token(payload))
    # _authenticate row: (session_token, status, subject_code, special_expires_at,
    #                     role, is_special, institution_id, subscription_end)
    # g.is_special은 DB값으로 판정(Codex#2) → is_special 파라미터를 행에 반영.
    mock_db["cursor"].fetchone.return_value = (
        "valid-sess", "active", subject_code, None,
        "student", is_special, institution_id,
        datetime.now(timezone.utc).date() + timedelta(days=365),
    )


def test_gate_cross_institution_same_subject_allowed(client, mock_db):
    """★#1: 기관이 SA가 아니어도(YU 학생) SA-HST-* 슬라이드 접근 허용 (과목 구독 기준)."""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"), \
         patch("server_render.get_slide_institution", return_value=("SA", "HST", "deployed", "ready")), \
         patch("server_render._institution_subject_access", return_value=True):
        mock_get_db.return_value = mock_db["conn"]
        _gate_setup(client, mock_db, subject_code="HST", institution_id="YU")
        # 유효 타일 토큰 제공 → 게이트 통과 시 SLIDE_CACHE 미적재로 503(Loading) = 접근 허용 증명
        t = generate_tile_token("1", "YU", "SA-HST-001")
        resp = client.get(f"http://localhost/dzi/SA-HST-001.dzi?t={t}")
        assert resp.status_code == 503  # 게이트·타일토큰 통과(미적재 로딩) — 403/401 아님


def test_gate_institution_not_subscribed_subject_403(client, mock_db):
    """★#2: 기관이 PRT 미구독 → 그 기관 PRT 학생의 SA-PRT-* 접근 403 (게이트 (3) 기관 미구독)."""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"), \
         patch("server_render.get_slide_institution", return_value=("SA", "PRT", "deployed", "ready")), \
         patch("server_render._institution_subject_access", return_value=False):  # 기관이 PRT 미구독
        mock_get_db.return_value = mock_db["conn"]
        _gate_setup(client, mock_db, subject_code="PRT", institution_id="YU")
        resp = client.get("http://localhost/dzi/SA-PRT-001.dzi")
        assert resp.status_code == 403
        assert resp.get_json()["error"] == "FORBIDDEN"


def test_gate_subject_mismatch_403(client, mock_db):
    """g.subject_code != slide.subject_code (같은 기관·다른 과목 등록) → 403 (게이트 (2))."""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"), \
         patch("server_render.get_slide_institution", return_value=("SA", "PRT", "deployed", "ready")), \
         patch("server_render._institution_subject_access", return_value=True):
        mock_get_db.return_value = mock_db["conn"]
        _gate_setup(client, mock_db, subject_code="HST")  # HST 등록 학생이 PRT 슬라이드 접근
        resp = client.get("http://localhost/dzi/SA-PRT-001.dzi")
        assert resp.status_code == 403
        assert resp.get_json()["error"] == "FORBIDDEN"


def test_gate_not_deployed_403(client, mock_db):
    """deploy_status != 'deployed' 슬라이드 → 일반 사용자 403 (게이트 (1))."""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"), \
         patch("server_render.get_slide_institution", return_value=("SA", "HST", "qc_pending", "ready")), \
         patch("server_render._institution_subject_access", return_value=True):
        mock_get_db.return_value = mock_db["conn"]
        _gate_setup(client, mock_db, subject_code="HST")
        resp = client.get("http://localhost/dzi/SA-HST-001.dzi")
        assert resp.status_code == 403
        assert resp.get_json()["error"] == "FORBIDDEN"


# ─────────────────────────────────────────────
# [#6] ADMIN_SECRET_KEY fail-closed 기동
# ─────────────────────────────────────────────

def test_tile_token_reissue_denied_without_access(client, mock_db):
    """[2-2#2] 접근권 없는 슬라이드의 타일 토큰 재발급 거부 (403)."""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"), \
         patch("server_render.get_slide_institution", return_value=("SA", "PRT", "deployed", "ready")), \
         patch("server_render._institution_subject_access", return_value=False):
        mock_get_db.return_value = mock_db["conn"]
        _gate_setup(client, mock_db, subject_code="HST")  # HST 학생이 PRT 슬라이드 토큰 요청
        resp = client.get("http://localhost/api/tile-token?slide=SA-PRT-001")
        assert resp.status_code == 403
        assert resp.get_json()["error"] == "FORBIDDEN"


def test_tile_token_reissue_success_with_access(client, mock_db):
    """[2-2#2] 접근권 있는 슬라이드 → 새 타일 토큰 재발급 성공."""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"), \
         patch("server_render.get_slide_institution", return_value=("SA", "HST", "deployed", "ready")), \
         patch("server_render._institution_subject_access", return_value=True):
        mock_get_db.return_value = mock_db["conn"]
        _gate_setup(client, mock_db, subject_code="HST")
        resp = client.get("http://localhost/api/tile-token?slide=SA-HST-001")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["token"]
        # 재발급 토큰이 실제 검증을 통과하는지 확인
        from auth.decorators import verify_tile_token
        assert verify_tile_token(data["token"], "1", "YU", "SA-HST-001") is True


def test_tile_token_reissue_missing_slide(client, mock_db):
    """[2-2#2] slide 누락 → 400."""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        _gate_setup(client, mock_db, subject_code="HST")
        resp = client.get("http://localhost/api/tile-token")
        assert resp.status_code == 400


def test_xlsx_safe_neutralizes_formula_injection():
    """[2-2#4] =,+,-,@로 시작하는 셀 값은 ' 프리픽스로 무력화, 그 외는 원본 유지."""
    import server_render as _sr
    assert _sr._xlsx_safe("=1+1") == "'=1+1"
    assert _sr._xlsx_safe("+82-10") == "'+82-10"
    assert _sr._xlsx_safe("-cmd") == "'-cmd"
    assert _sr._xlsx_safe("@SUM(A1)") == "'@SUM(A1)"
    assert _sr._xlsx_safe("충남대 의대") == "충남대 의대"   # 정상 한글 — 변경 없음
    assert _sr._xlsx_safe("H&E") == "H&E"
    assert _sr._xlsx_safe(42) == 42                          # 숫자 — 변경 없음
    assert _sr._xlsx_safe(None) is None


def test_inquiry_reply_email_rejects_header_injection():
    """[2-2#3] 수신 주소에 개행(헤더 주입 시도) → 발송 거부(False)."""
    import server_render as _sr
    ok = _sr._send_inquiry_reply_email("victim@test.com\nBcc: evil@x.com", "제목", "본문")
    assert ok is False


def test_inquiry_reply_email_escapes_html():
    """[2-2#3] 본문·제목의 HTML이 escaping되어 발송 (스크립트 주입 방지)."""
    import server_render as _sr
    captured = {}

    class _FakeSMTP:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def login(self, *a): pass
        def send_message(self, msg): captured['msg'] = msg

    with patch("smtplib.SMTP_SSL", _FakeSMTP):
        ok = _sr._send_inquiry_reply_email(
            "user@test.com", "<b>title</b>", "<script>alert(1)</script>")
    assert ok is True
    payload = captured['msg'].get_payload()[0].get_payload(decode=True).decode('utf-8')
    assert '<script>' not in payload
    assert '&lt;script&gt;' in payload
    # Subject는 개행 없이 한 줄
    assert '\n' not in str(captured['msg']['Subject']).strip()


def _admin_session(client, csrf='admin-csrf', session_token='admin-sess-tok'):
    with client.session_transaction() as sess:
        sess['admin_user_id'] = 1
        sess['admin_csrf_token'] = csrf
        sess['admin_session_token'] = session_token   # [Codex#2] 매 요청 DB 대조 토큰


def test_inquiry_reply_mail_failure_keeps_open(client, mock_db):
    """[2-2#3] 메일 발송 실패 시 status='answered'로 바꾸지 않음(open 유지) + 경고 반환."""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"), \
         patch("server_render._send_inquiry_reply_email", return_value=False):
        mock_get_db.return_value = mock_db["conn"]
        mock_db["cursor"].fetchone.side_effect = [
            (1, "super_admin", "Admin", "active", "admin-sess-tok"),  # _get_admin_user (+session_token)
            ("문의제목", "user@test.com"),           # SELECT title, user_email
            (99,),                                   # INSERT reply RETURNING id
        ]
        _admin_session(client, 'admin-csrf')
        resp = client.post("/admin/api/inquiries/1/reply",
                           json={"body": "답변 내용"},
                           headers={"X-CSRF-Token": "admin-csrf"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["sent_via_ses"] is False
        assert "warning" in data
        # answered UPDATE가 실행되지 않았는지 확인
        executed = " ".join(str(c.args[0]) for c in mock_db["cursor"].execute.call_args_list)
        assert "answered" not in executed


def test_inquiry_reply_mail_success_marks_answered(client, mock_db):
    """[2-2#3] 메일 발송 성공 시에만 status='answered' 전환."""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"), \
         patch("server_render._send_inquiry_reply_email", return_value=True):
        mock_get_db.return_value = mock_db["conn"]
        mock_db["cursor"].fetchone.side_effect = [
            (1, "super_admin", "Admin", "active", "admin-sess-tok"),
            ("문의제목", "user@test.com"),
            (99,),
        ]
        _admin_session(client, 'admin-csrf')
        resp = client.post("/admin/api/inquiries/1/reply",
                           json={"body": "답변 내용"},
                           headers={"X-CSRF-Token": "admin-csrf"})
        assert resp.status_code == 200
        assert resp.get_json()["sent_via_ses"] is True
        executed = " ".join(str(c.args[0]) for c in mock_db["cursor"].execute.call_args_list)
        assert "answered" in executed


def test_admin_secret_key_required_at_startup():
    """[#6] ADMIN_SECRET_KEY 미설정 시 server_render import(기동) 실패 (고정 폴백 금지)."""
    import importlib
    import server_render as _sr
    saved = os.environ.pop("ADMIN_SECRET_KEY", None)
    try:
        with pytest.raises(RuntimeError):
            importlib.reload(_sr)
    finally:
        # 환경 복원 후 모듈을 정상 상태로 되돌린다(다른 테스트 격리).
        if saved is not None:
            os.environ["ADMIN_SECRET_KEY"] = saved
        else:
            os.environ["ADMIN_SECRET_KEY"] = "test-admin-secret-for-pytest"
        importlib.reload(_sr)


# ─────────────────────────────────────────────
# 기관 관리자 등록·인증·포털 (§9 — admin roster onboarding)
# ─────────────────────────────────────────────
def test_register_admin_only_allowed(client, mock_db):
    """②: 관리자 등록(role='admin')만 있어도 /register 통과 — 과목·구독·좌석 게이트 면제."""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"), \
         patch("auth.auth.send_verification_email") as mock_send:
        mock_get_db.return_value = mock_db["conn"]
        # admin roster에는 센티넬 과목코드. 구독/좌석 SELECT는 호출되지 않아야 한다.
        mock_db["cursor"].fetchone.side_effect = [
            ("__ADMIN__",),   # roster subject_code (관리자 행)
            None,             # 이메일 미존재
            (42,),            # INSERT users RETURNING id
        ]
        resp = client.post("/api/auth/register",
                          json={"email": "prof@univ.ac.kr", "password": "secure123",
                                "role": "admin", "institution_id": "YU"})
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        assert mock_send.called
        # 구독·정원 게이트 면제 확인: 실행된 SQL에 subscriptions 조회가 없어야 한다.
        executed = " ".join(str(c.args[0]) for c in mock_db["cursor"].execute.call_args_list)
        assert "FROM subscriptions" not in executed


def test_register_admin_skips_subscription_even_if_none(client, mock_db):
    """②(보강): 구독이 전혀 없어도 admin은 SUBSCRIPTION_INACTIVE로 거부되지 않는다."""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"), \
         patch("auth.auth.send_verification_email"):
        mock_get_db.return_value = mock_db["conn"]
        mock_db["cursor"].fetchone.side_effect = [
            ("__ADMIN__",),   # roster
            None,             # 이메일 미존재
            (7,),             # INSERT users RETURNING id
        ]
        resp = client.post("/api/auth/register",
                          json={"email": "admin@univ.ac.kr", "password": "pw123456",
                                "role": "admin", "institution_id": "YU"})
        assert resp.status_code == 200


def test_verify_email_admin_creates_admin_role(client, mock_db):
    """③: 관리자 인증 완료 → users.role='admin' 활성, 구독·좌석 재검사 면제."""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        mock_db["cursor"].fetchone.side_effect = [
            (1, "YU", "admin", False, "__ADMIN__"),   # user (role='admin')
            (1, "123456", datetime.now(timezone.utc) + timedelta(minutes=5), False, 0),  # ev
        ]
        resp = client.post("/api/auth/verify-email",
                          json={"email": "prof@univ.ac.kr", "code": "123456"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["role"] == "admin"
        # active 전환 시 구독/좌석 재검사가 없어야 한다(면제).
        executed = " ".join(str(c.args[0]) for c in mock_db["cursor"].execute.call_args_list)
        assert "FROM subscriptions" not in executed
        cookies = resp.headers.getlist("Set-Cookie")
        assert any(COOKIE_NAME in c for c in cookies)


def test_portal_admin_access(client, mock_db):
    """④: 관리자 roster 행이 존재하는 사용자는 /portal 진입 가능(200).

    [Codex#1/Gemini#3] role='admin'만으로는 통과하지 않는다 — _is_institution_admin(roster 행 존재)이
      권위. 본 테스트는 roster 행이 있는 정상 관리자 경로(200)를 검증한다.
    """
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        payload = {"sub": "1", "institution_id": "YU", "role": "admin",
                   "session_token": "sess-admin-1", "is_special": False}
        client.set_cookie(COOKIE_NAME, encode_token(payload))
        mock_db["cursor"].fetchone.side_effect = [
            # _authenticate: subscription_end=None이어도 db_role='admin'이라 통과.
            ("sess-admin-1", "active", "__ADMIN__", None, "admin", False, "YU", None),
            (1,),                  # _is_institution_admin: 관리자 roster 행 존재
            ("연세대 의과대학",),   # 포털: institutions.name_ko
        ]
        resp = client.get("http://localhost/portal")
        assert resp.status_code == 200
        assert "포털" in resp.get_data(as_text=True)


def test_portal_non_admin_redirected(client, mock_db):
    """일반 학생(role='student', 관리자 명단 없음)은 /portal에서 랜딩으로 리다이렉트."""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        payload = {"sub": "2", "institution_id": "YU", "role": "student",
                   "session_token": "sess-stu-1", "is_special": False}
        client.set_cookie(COOKIE_NAME, encode_token(payload))
        mock_db["cursor"].fetchone.side_effect = [
            # _authenticate: 유효 구독창(학생은 구독 필요)
            ("sess-stu-1", "active", "HST", None, "student", False, "YU",
             datetime.now(timezone.utc).date() + timedelta(days=365)),
            None,   # _is_institution_admin: 관리자 명단 행 없음
        ]
        resp = client.get("http://localhost/portal")
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/")


def test_institution_create_registers_admin_roster(client, mock_db):
    """①: 기관 추가 시 admin_contacts → institution_rosters(role='admin', '__ADMIN__', position) 등록."""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"), \
         patch("server_render._send_portal_invite_email", return_value=True) as mock_invite:
        mock_get_db.return_value = mock_db["conn"]
        mock_db["cursor"].fetchone.side_effect = [
            (1, "super_admin", "Admin", "active", "admin-sess-tok"),  # _get_admin_user (+session_token)
            None,                                   # SELECT id FROM institutions (미존재)
        ]
        _admin_session(client, 'admin-csrf')
        resp = client.post("/admin/api/institutions",
                           json={"id": "YU", "university": "연세대", "college": "의과대학",
                                 "admin_contacts": [
                                     {"name": "김교수", "position": "교수", "email": "prof@univ.ac.kr", "phone": "010"},
                                 ],
                                 "subscriptions": []},
                           headers={"X-CSRF-Token": "admin-csrf"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["admins_registered"] == 1
        # roster INSERT 호출에 센티넬 과목코드·role='admin'·position·이메일이 들어갔는지 확인.
        roster_inserts = [
            c for c in mock_db["cursor"].execute.call_args_list
            if "INSERT INTO institution_rosters" in str(c.args[0])
        ]
        assert roster_inserts, "institution_rosters INSERT가 호출되지 않음"
        params = roster_inserts[0].args[1]
        assert "__ADMIN__" in params
        assert "prof@univ.ac.kr" in params
        assert "교수" in params
        # 포털 안내 메일 발송 시도
        assert mock_invite.called


def test_institution_update_syncs_admin_roster(client, mock_db):
    """기관 수정(PUT): 관리자 제거 = __ADMIN__ roster 행만 DELETE. 계정/과목 권한은 불가침."""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"), \
         patch("server_render._send_portal_invite_email", return_value=True):
        mock_get_db.return_value = mock_db["conn"]
        mock_db["cursor"].fetchone.side_effect = [
            (1, "super_admin", "Admin", "active", "admin-sess-tok"),  # _get_admin_user (+session_token)
        ]
        # 기존 admin roster: 두 명(old@, keep@) → 폼에는 keep@만 남김 → old@ 제거
        mock_db["cursor"].fetchall.return_value = [("old@univ.ac.kr",), ("keep@univ.ac.kr",)]
        _admin_session(client, 'admin-csrf')
        resp = client.put("/admin/api/institutions/YU",
                          json={"university": "연세대", "college": "의과대학",
                                "admin_contacts": [
                                    {"name": "유지", "position": "교수", "email": "keep@univ.ac.kr", "phone": ""},
                                ]},
                          headers={"X-CSRF-Token": "admin-csrf"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["admins_removed"] == 1
        executed = mock_db["cursor"].execute.call_args_list
        # 제거: __ADMIN__ roster 행 DELETE 1건 (관리 권한만 회수)
        del_calls = [c for c in executed if "DELETE FROM institution_rosters" in str(c.args[0])]
        assert del_calls, "admin roster DELETE 미호출"
        assert "__ADMIN__" in del_calls[0].args[1]
        # 관리/열람 분리: 계정 정지·계정/유저 삭제 절대 금지
        assert not any("status = 'suspended'" in str(c.args[0]) for c in executed)
        assert not any("suspended" in str(c.args[0]) for c in executed)
        assert not any("DELETE FROM users" in str(c.args[0]) for c in executed)
        assert not any("UPDATE users" in str(c.args[0]) for c in executed)


def test_moonlighter_admin_removed_portal_blocked(client, mock_db):
    """겸직자(admin+조직학 학생) 관리자 제거 후: 포털 차단.

    __ADMIN__ 행만 삭제 → admin 명단 행 부재 → role='student' + _is_institution_admin=None → 랜딩 리다이렉트.
    계정은 active 그대로(정지 아님)임을 _authenticate 통과로 확인.
    """
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        payload = {"sub": "3", "institution_id": "YU", "role": "student",
                   "session_token": "sess-moon", "is_special": False}
        client.set_cookie(COOKIE_NAME, encode_token(payload))
        mock_db["cursor"].fetchone.side_effect = [
            # _authenticate: 계정 active, HST 등록, 유효 구독 (정지 안 됨)
            ("sess-moon", "active", "HST", None, "student", False, "YU",
             datetime.now(timezone.utc).date() + timedelta(days=365)),
            None,   # _is_institution_admin: 관리자 행 없음(제거됨)
        ]
        resp = client.get("http://localhost/portal")
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/")


def test_moonlighter_admin_removed_slides_kept(client, mock_db):
    """겸직자 관리자 제거 후: 조직학 슬라이드는 계속 열람.

    __ADMIN__ 행만 삭제이므로 users 계정·HST 과목 행은 그대로 → 슬라이드 게이트(과목 좌석) 영향 없음.
    HST 게이트 통과 → 503(미적재 로딩; 403/401 아님)으로 접근 허용 증명.
    """
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"), \
         patch("server_render.get_slide_institution", return_value=("SA", "HST", "deployed", "ready")), \
         patch("server_render._institution_subject_access", return_value=True):
        mock_get_db.return_value = mock_db["conn"]
        _gate_setup(client, mock_db, subject_code="HST", institution_id="YU", user_id="3")
        t = generate_tile_token("3", "YU", "SA-HST-001")
        resp = client.get(f"http://localhost/dzi/SA-HST-001.dzi?t={t}")
        assert resp.status_code == 503  # 게이트·타일토큰 통과 = 슬라이드 접근 허용


# ══════════════════════════════════════════════════════════════════════════
# 외부검증(Codex·Gemini) 보안 결함 7건 — 회귀 테스트
# ══════════════════════════════════════════════════════════════════════════

# ── #1 포털 권한 회수 우회 (Codex#1 / Gemini#3) ──────────────────────────
def test_portal_role_admin_but_roster_removed_blocked(client, mock_db):
    """#1: users.role='admin'이 DB에 남아 있어도 관리자 roster 행이 없으면 포털 차단(302).

    role 단독 우회 제거의 핵심 — 권한 회수(roster DELETE) 즉시 포털이 닫혀야 한다.
    """
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        payload = {"sub": "9", "institution_id": "YU", "role": "admin",
                   "session_token": "sess-ex-admin", "is_special": False}
        client.set_cookie(COOKIE_NAME, encode_token(payload))
        mock_db["cursor"].fetchone.side_effect = [
            # _authenticate: db_role='admin'이라 구독 게이트는 통과(계정 자체는 유효)
            ("sess-ex-admin", "active", "__ADMIN__", None, "admin", False, "YU", None),
            None,   # _is_institution_admin: 관리자 roster 행 없음(회수됨) → 포털 차단
        ]
        resp = client.get("http://localhost/portal")
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/")


# ── #2 JWT 신뢰 → DB 권위 (Codex#2 / Gemini#4) ──────────────────────────
def test_db_authority_is_special_revoked_blocks(client, mock_db):
    """#2: JWT payload는 is_special=True여도, DB의 is_special=False가 권위 → 만료 구독이면 차단.

    구 토큰을 신뢰했다면 만료 면제로 통과했을 것 — DB 값으로 판정해 SUBSCRIPTION_EXPIRED.
    """
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        payload = {"sub": "1", "institution_id": "YU", "role": "student",
                   "session_token": "valid-sess", "is_special": True}  # JWT는 특별계정이라 주장
        client.set_cookie(COOKIE_NAME, encode_token(payload))
        # DB 권위: is_special=False, 만료 구독(None) → 차단
        mock_db["cursor"].fetchone.return_value = (
            "valid-sess", "active", "HST", None, "student", False, "YU", None
        )
        resp = client.get("http://localhost/api/auth/me")
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "SUBSCRIPTION_EXPIRED"


def test_db_authority_role_admin_from_db_passes(client, mock_db):
    """#2: JWT role='student'(구독 없음)이어도 DB role='admin'이면 구독 게이트 면제(DB 권위)."""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        payload = {"sub": "1", "institution_id": "YU", "role": "student",
                   "session_token": "valid-sess", "is_special": False}
        client.set_cookie(COOKIE_NAME, encode_token(payload))
        mock_db["cursor"].fetchone.side_effect = [
            # DB role='admin' → 구독 None이어도 통과
            ("valid-sess", "active", "__ADMIN__", None, "admin", False, "YU", None),
            (1, "admin@test.com", "admin", "YU", False, "active", None),  # me()
        ]
        resp = client.get("http://localhost/api/auth/me")
        assert resp.status_code == 200
        # me()는 g가 아닌 DB를 다시 읽지만, _authenticate가 admin 분기로 통과했음을 200으로 확인
        assert resp.get_json()["data"]["role"] == "admin"


def test_admin_session_token_mismatch_blocks(client, mock_db):
    """#2(admin): Flask 세션 토큰과 DB session_token 불일치 → _get_admin_user None → 차단(401)."""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        # DB는 다른 토큰을 들고 있음(다른 곳에서 재로그인/로그아웃으로 회전됨)
        mock_db["cursor"].fetchone.return_value = (1, "super_admin", "Admin", "active", "NEW-token")
        with client.session_transaction() as sess:
            sess['admin_user_id'] = 1
            sess['admin_csrf_token'] = 'c'
            sess['admin_session_token'] = 'OLD-token'   # 불일치
        resp = client.post('/admin/api/slide', json={"id": "X"},
                           headers={'X-CSRF-Token': 'c'})
        assert resp.status_code == 401   # 로그인 필요(세션 무효)


# ── #3 어드민 로그인 브루트포스 차단 (Gemini#1) ─────────────────────────
def test_admin_login_locks_after_threshold(client, mock_db):
    """#3: 누적 실패가 임계값(10)에 도달하면 admin_users.locked_at 설정 + 잠금 안내."""
    from werkzeug.security import generate_password_hash
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        pw_hash = generate_password_hash("correct-pw")
        mock_db["cursor"].fetchone.side_effect = [
            # admin_login SELECT: id, password_hash, role, name, status, locked_at
            (1, pw_hash, "super_admin", "Admin", "active", None),
            # _admin_check_and_increment_failed SELECT: failed_attempts, failed_window_start (9 → 10)
            (9, datetime.now(timezone.utc)),
        ]
        resp = client.post('/admin/login',
                           data={"email": "admin@test.com", "password": "WRONG"})
        # 잠금 UPDATE(locked_at) 실행 확인
        executed = " ".join(str(c.args[0]) for c in mock_db["cursor"].execute.call_args_list)
        assert "locked_at" in executed
        assert "보안상 계정이 잠겼습니다" in resp.get_data(as_text=True)


def test_admin_login_auto_unlock_then_success(client, mock_db):
    """#3: locked_at이 24h 이전이면 자동 해제 후 정상 로그인(세션 토큰 회전)."""
    from werkzeug.security import generate_password_hash
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        pw_hash = generate_password_hash("correct-pw")
        old_lock = datetime.now(timezone.utc) - timedelta(hours=25)
        mock_db["cursor"].fetchone.return_value = (
            1, pw_hash, "super_admin", "Admin", "active", old_lock
        )
        resp = client.post('/admin/login',
                           data={"email": "admin@test.com", "password": "correct-pw"})
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/admin")
        executed = " ".join(str(c.args[0]) for c in mock_db["cursor"].execute.call_args_list)
        # 자동해제(locked_at = NULL) + 로그인 성공 시 session_token 회전
        assert "locked_at = NULL" in executed
        assert "session_token" in executed


# ── #4 특별계정 QC 미완료 노출 차단 (Gemini#7) ──────────────────────────
def test_special_qc_incomplete_blocked(client, mock_db):
    """#4: is_special이라도 conversion_status가 미완료(qc_check)면 접근 차단(403)."""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"), \
         patch("server_render.get_slide_institution",
               return_value=("SA", "HST", "deployed", "qc_check")), \
         patch("server_render._institution_subject_access", return_value=True):
        mock_get_db.return_value = mock_db["conn"]
        _gate_setup(client, mock_db, subject_code="HST", is_special=True)
        t = generate_tile_token("1", "YU", "SA-HST-001")
        resp = client.get(f"http://localhost/dzi/SA-HST-001.dzi?t={t}")
        assert resp.status_code == 403
        assert resp.get_json()["error"] == "FORBIDDEN"


def test_special_ready_no_mpp_allowed(client, mock_db):
    """#4: is_special은 ready_no_mpp(변환 완료) 슬라이드는 전 과목·전 기관 열람 유지(§15-8)."""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"), \
         patch("server_render.get_slide_institution",
               return_value=("SA", "PARA", "qc_pending", "ready_no_mpp")), \
         patch("server_render._institution_subject_access", return_value=False):
        mock_get_db.return_value = mock_db["conn"]
        # 특별계정은 과목(HST 등록)·기관·배포상태(qc_pending) 우회 — ready 계열이면 허용
        _gate_setup(client, mock_db, subject_code="HST", is_special=True)
        t = generate_tile_token("1", "YU", "SA-PARA-001")
        resp = client.get(f"http://localhost/dzi/SA-PARA-001.dzi?t={t}")
        assert resp.status_code == 503   # 게이트 통과(미적재 로딩) = 접근 허용


# ── #5 인증코드 CSPRNG (Codex#4) ────────────────────────────────────────
def test_gen_code_uses_csprng():
    """#5: _gen_code()는 secrets(CSPRNG) 기반이며 6자리 코드를 만든다."""
    from auth import auth as auth_mod
    with patch("auth.auth.secrets.randbelow", return_value=0) as mock_rand:
        code = auth_mod._gen_code()
        assert mock_rand.called          # random이 아닌 secrets.randbelow 사용
        assert code == "100000"          # randbelow(900000)+100000
    # 정상 호출도 항상 6자리
    for _ in range(50):
        c = auth_mod._gen_code()
        assert len(c) == 6 and c.isdigit()


# ── #6 이메일 1계정 정책 (Codex#3 / Gemini#5) ───────────────────────────
def test_register_duplicate_email_across_subject_blocked(client, mock_db):
    """#6: 이미 가입된 이메일은 다른 과목 명단으로 와도 새 계정/중복 pending을 만들지 않는다."""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"), \
         patch("auth.auth.send_verification_email") as mock_send:
        mock_get_db.return_value = mock_db["conn"]
        mock_db["cursor"].fetchone.side_effect = [
            ("PARA",),   # roster: 이번엔 기생충학 명단으로 가입 시도
            (1,),        # 전역 이메일 검사: 이미 계정 존재(이전 HST 가입)
        ]
        resp = client.post("/api/auth/register",
                           json={"email": "dup@univ.ac.kr", "password": "pw123456",
                                 "role": "student", "institution_id": "YU"})
        assert resp.status_code == 409
        assert resp.get_json()["error"] == "EMAIL_EXISTS"
        # 새 계정 INSERT·인증코드 발송이 일어나지 않아야 한다
        executed = " ".join(str(c.args[0]) for c in mock_db["cursor"].execute.call_args_list)
        assert "INSERT INTO users" not in executed
        assert not mock_send.called


# ── #7 입력 검증 (Codex#5) ──────────────────────────────────────────────
def test_institution_create_invalid_term_count_400(client, mock_db):
    """#7: term_count가 정수 아님 → 500이 아니라 400."""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        mock_db["cursor"].fetchone.return_value = (1, "super_admin", "Admin", "active", "admin-sess-tok")
        mock_db["cursor"].fetchall.return_value = [("HST",)]   # _subject_codes_set allowlist
        _admin_session(client, 'admin-csrf')
        resp = client.post("/admin/api/institutions",
                           json={"id": "YU", "university": "연세대", "college": "의대",
                                 "subscriptions": [
                                     {"subject_code": "HST", "start_term": "2026-fall",
                                      "plan": "standard", "term_count": "abc"}]},
                           headers={"X-CSRF-Token": "admin-csrf"})
        assert resp.status_code == 400
        assert "term_count" in resp.get_json()["error"]


def test_institution_create_invalid_plan_400(client, mock_db):
    """#7: 알 수 없는 plan(allowlist 밖) → 400."""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        mock_db["cursor"].fetchone.return_value = (1, "super_admin", "Admin", "active", "admin-sess-tok")
        mock_db["cursor"].fetchall.return_value = [("HST",)]
        _admin_session(client, 'admin-csrf')
        resp = client.post("/admin/api/institutions",
                           json={"id": "YU", "university": "연세대", "college": "의대",
                                 "subscriptions": [
                                     {"subject_code": "HST", "start_term": "2026-fall",
                                      "plan": "platinum", "term_count": 1}]},
                           headers={"X-CSRF-Token": "admin-csrf"})
        assert resp.status_code == 400
        assert "플랜" in resp.get_json()["error"]


def test_institution_create_unknown_subject_400(client, mock_db):
    """#7: subject_code가 subject_codes allowlist 밖 → 400."""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        mock_db["cursor"].fetchone.return_value = (1, "super_admin", "Admin", "active", "admin-sess-tok")
        mock_db["cursor"].fetchall.return_value = [("HST",)]
        _admin_session(client, 'admin-csrf')
        resp = client.post("/admin/api/institutions",
                           json={"id": "YU", "university": "연세대", "college": "의대",
                                 "subscriptions": [
                                     {"subject_code": "ZZZ", "start_term": "2026-fall",
                                      "plan": "standard", "term_count": 1}]},
                           headers={"X-CSRF-Token": "admin-csrf"})
        assert resp.status_code == 400
        assert "과목코드" in resp.get_json()["error"]
