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

# Flask 앱 로딩
from server_render import app
from auth.decorators import encode_token, decode_token, COOKIE_NAME


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
        mock_db["cursor"].fetchone.side_effect = [(1,), (1,)]
        
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
            (1,),        # 명단 존재
            None,        # 이메일 없음
            (10,),       # max_users=10
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
            (1,),        # 명단
            None,        # 이메일 없음
            (100,),      # max_users
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


def test_verify_email_code_expired(client, mock_db):
    """인증코드 확인: 만료된 코드 → 410 CODE_EXPIRED"""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        
        mock_db["cursor"].fetchone.side_effect = [
            (1, "YU", "student", False),
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
            (1, "YU", "student", False),
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
            (1, "YU", "student", False),
            (
                1, "123456",
                datetime.now(timezone.utc) + timedelta(minutes=5),
                False, 3
            )
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
            (1, "YU", "student", False),
            (
                1, "123456", 
                datetime.now(timezone.utc) + timedelta(minutes=5),
                False, 4
            )
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
            (1, "YU", "student", False),
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
            (1, "YU", "student", False),
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
        
        mock_db["cursor"].fetchone.return_value = (
            1, "YU", "student", False,
            correct_hash,
            "active",
            datetime.now(timezone.utc) + timedelta(days=365)
        )
        
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
    """login_required: 쿠키 없음 → 401 SESSION_EXPIRED"""
    resp = client.get("/api/auth/me")
    
    assert resp.status_code == 401
    data = resp.get_json()
    assert data["error"] == "SESSION_EXPIRED"


def test_login_required_invalid_token(client):
    """login_required: 유효하지 않은 JWT → 401"""
    client.set_cookie(COOKIE_NAME, "invalid.jwt.token")
    
    resp = client.get("/api/auth/me")
    
    assert resp.status_code == 401


def test_login_required_expired_token(client):
    """login_required: 만료된 JWT → 401 SESSION_EXPIRED"""
    with patch("auth.decorators.decode_token") as mock_decode:
        import jwt
        mock_decode.side_effect = jwt.ExpiredSignatureError()
        
        client.set_cookie(COOKIE_NAME, "dummy-token")
        resp = client.get("/api/auth/me")
        
        assert resp.status_code == 401
        data = resp.get_json()
        assert data["error"] == "SESSION_EXPIRED"


def test_login_required_session_token_mismatch(client, mock_db):
    """login_required: DB session_token 불일치 (다른 기기) → 401 SESSION_EXPIRED"""
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

        mock_db["cursor"].fetchone.return_value = (
            "new-session-token",
            "active"
        )

        resp = client.get("/api/auth/me", headers={"Cookie": f"{COOKIE_NAME}={token}"})

        assert resp.status_code == 401
        data = resp.get_json()
        assert data["error"] == "SESSION_EXPIRED"


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
            "valid-session-123",
            "pending_verification"
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
            ("valid-session-123", "active"),
            (1, "test@example.com", "student", "YU", False, "active", None)
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
        client.set_cookie(COOKIE_NAME, token)

        mock_db["cursor"].fetchone.return_value = (
            "valid-session-123", "active"
        )

        # Werkzeug 3.x: set_cookie requires full URL for domain matching
        resp = client.post("http://localhost/api/auth/logout")

        assert resp.status_code == 200
        assert any("Delete" in c or "Max-Age=0" in c
                  for c in resp.headers.getlist("Set-Cookie"))
