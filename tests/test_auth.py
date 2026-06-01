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
            "new-session-token", "active", "HST", None, None  # session_token, status, subject_code, special_expires_at, subscription_end
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
            "valid-session-123", "pending_verification", "HST", None, None
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
            ("valid-session-123", "active", "HST", None,
             datetime.now(timezone.utc).date() + timedelta(days=365)),   # _authenticate: session_token, status, subject_code, special_expires_at, subscription_end
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
            "valid-session-123", "active", "HST", None,
            datetime.now(timezone.utc).date() + timedelta(days=365)   # session_token, status, subject_code, special_expires_at, subscription_end
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
            "sess123", "active", "HST", None, datetime.now(timezone.utc).date() + timedelta(days=365))

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
            "sess123", "active", "HST", None, datetime.now(timezone.utc).date() + timedelta(days=365))

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
        # _get_admin_user: SELECT id, role, name, status FROM admin_users
        mock_db["cursor"].fetchone.return_value = (1, "super_admin", "Admin", "active")

        with client.session_transaction() as sess:
            sess['admin_user_id'] = 1
            sess['admin_csrf_token'] = 'test-admin-csrf-123'

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
        mock_db["cursor"].fetchone.return_value = (1, "super_admin", "Admin", "active")

        with client.session_transaction() as sess:
            sess['admin_user_id'] = 1
            sess['admin_csrf_token'] = 'correct-token'

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
        mock_db["cursor"].fetchone.return_value = (1, "super_admin", "Admin", "active")

        with client.session_transaction() as sess:
            sess['admin_user_id'] = 1
            sess['admin_csrf_token'] = 'test-csrf'

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
            "different-token-in-db", "active", "HST", None, None
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
            "valid-sess", "active", "HST", None, expired_date
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
        # 접근창 밖 → subquery NULL: (session, status, subject, special_expires_at, subscription_end=None)
        mock_db["cursor"].fetchone.return_value = (
            "valid-sess", "active", "HST", None, None
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
        mock_db["cursor"].fetchone.return_value = (
            "valid-sess", "active", None, date.today() - timedelta(days=1), None
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
            ("valid-sess", "active", None, None, None),   # _authenticate: special_expires_at=None → 통과
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
            ("valid-sess", "active", None, None, expired_date),   # _authenticate: is_special(subject_code·special_expires_at 무관, 구독만료 면제)
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
        # 단일 게이트 계약: (institution_id, subject_code, deploy_status)
        mock_inst.return_value = ("SA", "HST", "deployed")

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
            "valid-sess", "active", "HST", None, datetime.now(timezone.utc).date() + timedelta(days=365)
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
    # _authenticate row: (session_token, status, subject_code, special_expires_at, subscription_end)
    mock_db["cursor"].fetchone.return_value = (
        "valid-sess", "active", subject_code, None,
        datetime.now(timezone.utc).date() + timedelta(days=365),
    )


def test_gate_cross_institution_same_subject_allowed(client, mock_db):
    """★#1: 기관이 SA가 아니어도(YU 학생) SA-HST-* 슬라이드 접근 허용 (과목 구독 기준)."""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"), \
         patch("server_render.get_slide_institution", return_value=("SA", "HST", "deployed")), \
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
         patch("server_render.get_slide_institution", return_value=("SA", "PRT", "deployed")), \
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
         patch("server_render.get_slide_institution", return_value=("SA", "PRT", "deployed")), \
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
         patch("server_render.get_slide_institution", return_value=("SA", "HST", "qc_pending")), \
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
         patch("server_render.get_slide_institution", return_value=("SA", "PRT", "deployed")), \
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
         patch("server_render.get_slide_institution", return_value=("SA", "HST", "deployed")), \
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


def _admin_session(client, csrf='admin-csrf'):
    with client.session_transaction() as sess:
        sess['admin_user_id'] = 1
        sess['admin_csrf_token'] = csrf


def test_inquiry_reply_mail_failure_keeps_open(client, mock_db):
    """[2-2#3] 메일 발송 실패 시 status='answered'로 바꾸지 않음(open 유지) + 경고 반환."""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"), \
         patch("server_render._send_inquiry_reply_email", return_value=False):
        mock_get_db.return_value = mock_db["conn"]
        mock_db["cursor"].fetchone.side_effect = [
            (1, "super_admin", "Admin", "active"),  # _get_admin_user
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
            (1, "super_admin", "Admin", "active"),
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


# ════════════════════════════════════════════════════════════════════════
# 외부검증 출시블로커 회귀 테스트 (audit-blockers-2026-06)
# ════════════════════════════════════════════════════════════════════════

# ── 블로커4: 잠금 해제가 pending_verification → active 승급을 만들지 않는다 ──
def test_auto_unlock_pending_account_stays_blocked(client, mock_db):
    """[블로커4] 미검증(last_login NULL) 계정이 24h 후 자동해제돼도 active로 승급되지 않는다.
    올바른 비밀번호로 로그인해도 verify_email(구독·좌석·접근창)을 우회해 active가 되면 안 됨."""
    from werkzeug.security import generate_password_hash
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]

        locked_at = datetime.now(timezone.utc) - timedelta(hours=25)  # 24h 경과 → 자동해제 대상
        mock_db["cursor"].fetchone.side_effect = [
            # 로그인 SELECT: status='locked'
            (1, "YU", "student", False,
             generate_password_hash("password"), "locked", locked_at, None,
             datetime.now(timezone.utc).date() + timedelta(days=365)),
            # _check_auto_unlock 의 SELECT last_login → NULL (한 번도 검증된 적 없음)
            (None,),
        ]

        resp = client.post("/api/auth/login",
                           json={"email": "test@example.com", "password": "password"})

        # active 로 승급 금지 → 비활성 계정으로 차단(ACCOUNT_INACTIVE), 로그인 성공(200) 금지.
        assert resp.status_code == 403
        assert resp.get_json()["error"] == "ACCOUNT_INACTIVE"
        # 복원 UPDATE 의 status 파라미터가 'active' 가 아니라 'pending_verification' 인지 확인.
        update_calls = [c for c in mock_db["cursor"].execute.call_args_list
                        if "SET status = %s" in str(c.args[0]) and "locked_at = NULL" in str(c.args[0])]
        assert update_calls, "자동해제 UPDATE 가 실행되지 않음"
        assert update_calls[0].args[1][0] == "pending_verification"  # active 승급 금지


def test_auto_unlock_verified_account_restores_active(client, mock_db):
    """[블로커4] 검증 이력(last_login NOT NULL) 계정은 24h 후 자동해제 시 active 로 복원되어 로그인 성공."""
    from werkzeug.security import generate_password_hash
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]

        locked_at = datetime.now(timezone.utc) - timedelta(hours=25)
        mock_db["cursor"].fetchone.side_effect = [
            (1, "YU", "student", False,
             generate_password_hash("password"), "locked", locked_at, None,
             datetime.now(timezone.utc).date() + timedelta(days=365)),
            # last_login 존재 → 과거 active 였음 → active 복원
            (datetime.now(timezone.utc) - timedelta(days=10),),
        ]

        resp = client.post("/api/auth/login",
                           json={"email": "test@example.com", "password": "password"})

        assert resp.status_code == 200
        assert resp.get_json()["success"] is True


# ── 블로커3: 대시보드 API 는 super_admin 전용(staff 403) ──
def test_dashboard_api_staff_forbidden(client, mock_db):
    """[블로커3] staff 가 /admin/api/dashboard 직접 호출 → 403 (재무 데이터 노출 차단)."""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        # _get_admin_user: (id, role, name, status) — staff 권한
        mock_db["cursor"].fetchone.return_value = (2, "staff", "Staff", "active")
        _admin_session(client, 'admin-csrf')

        resp = client.get("/admin/api/dashboard")
        assert resp.status_code == 403


# ── 블로커2: ec2_proxy 경로 트래버설/비화이트리스트 차단 + 안전 재구성 ──
def test_ec2_parse_subpath_valid_patterns():
    """[블로커2] 허용 패턴은 검증된 컴포넌트로 재구성되고 slide_id 가 정확히 추출된다."""
    from server_render import _ec2_parse_subpath
    assert _ec2_parse_subpath("dzi/SA-HST-001.dzi") == ("SA-HST-001", "dzi/SA-HST-001.dzi")
    sid, sp = _ec2_parse_subpath("dzi/SA-HST-001_files/12/3_4.jpeg")
    assert sid == "SA-HST-001" and sp == "dzi/SA-HST-001_files/12/3_4.jpeg"
    assert _ec2_parse_subpath("thumbnail/SA-PARA-009") == ("SA-PARA-009", "thumbnail/SA-PARA-009")
    assert _ec2_parse_subpath("info/SA-HST-001") == ("SA-HST-001", "info/SA-HST-001")


def test_ec2_parse_subpath_rejects_traversal_and_garbage():
    """[블로커2] '..'/'%'/추가 슬래시/비화이트리스트 확장자/잘못된 slide_id 는 전부 거부(None)."""
    from server_render import _ec2_parse_subpath
    bad = [
        "dzi/SA-HST-001_files/../../SA-PATH-001_files/0/0_0.jpeg",  # 트래버설
        "dzi/SA-HST-001_files/..%2f..%2fSA-PATH-001.dzi",          # 인코딩 우회
        "dzi/SA-HST-001_files/0/0_0.png",                          # 비화이트리스트 ext
        "dzi/SA-HST-001/extra/0_0.jpeg",                           # 추가 슬래시
        "dzi/EVIL-x-1.dzi",                                        # slide_id 형식 위반(소문자)
        "dzi/../etc/passwd",                                       # 절대경로 트래버설
        "secret/SA-HST-001",                                       # 미허용 prefix
        "dzi/SA-HST-001.dzi.bak",                                  # 꼬리 오염
    ]
    for s in bad:
        assert _ec2_parse_subpath(s) == (None, None), f"거부 실패: {s}"


def test_ec2_proxy_rejects_bad_path_with_400(client, mock_db):
    """[블로커2] 인증 통과 후에도 비화이트리스트 경로는 업스트림 전달 전 400 거부."""
    with patch("server_render.get_db_conn") as mock_get_db, \
         patch("server_render.release_db_conn"):
        mock_get_db.return_value = mock_db["conn"]
        payload = {"sub": "1", "institution_id": "YU", "role": "student",
                   "session_token": "valid-session-123", "is_special": False}
        client.set_cookie(COOKIE_NAME, encode_token(payload))
        # _authenticate 통과용 (session_token, status, subject_code, special_expires_at, subscription_end)
        mock_db["cursor"].fetchone.return_value = (
            "valid-session-123", "active", "HST", None,
            datetime.now(timezone.utc).date() + timedelta(days=365))
        # 비화이트리스트 ext → 파서 거부(400). '..' 는 URL 정규화 영향이 있어 ext 위반으로 검증.
        resp = client.get("http://localhost/ec2tile/dzi/SA-HST-001_files/0/0_0.png")
        assert resp.status_code == 400


# ── 블로커1: 타일서버가 직접 검증하는 HMAC 토큰이 Flask 발급분과 동일 시크릿·페이로드로 호환 ──
def _tileserver_verify(token, user_id, institution_id, slide_id):
    """tileserver/main.py._verify_tile_token 과 동일한 검증 로직(시크릿·페이로드 호환성 계약).
    main.py 는 fastapi/openslide 의존으로 로컬 import 불가하므로 동일 알고리즘을 재현해 계약을 고정한다."""
    import hmac as _h, hashlib as _hh, time as _t
    secret = os.environ["JWT_SECRET_KEY"]
    try:
        exp_str, sig = token.split(":", 1)
        exp = int(exp_str)
        if exp < int(_t.time()):
            return False
        msg = f"{user_id}:{institution_id}:{slide_id}:{exp}"
        expected = _h.new(secret.encode(), msg.encode(), _hh.sha256).hexdigest()
        return _h.compare_digest(sig, expected)
    except Exception:
        return False


def test_tileserver_token_contract_valid():
    """[블로커1] Flask generate_tile_token 발급 토큰이 타일서버 검증 로직을 통과(동일 시크릿·페이로드)."""
    tok = generate_tile_token("1", "YU", "SA-HST-001")
    assert _tileserver_verify(tok, "1", "YU", "SA-HST-001") is True


def test_tileserver_token_contract_slide_binding():
    """[블로커1] 토큰은 slide_id 에 바인딩 — 다른 슬라이드 경로엔 통하지 않는다(트래버설 방어)."""
    tok = generate_tile_token("1", "YU", "SA-HST-001")
    assert _tileserver_verify(tok, "1", "YU", "SA-PATH-001") is False
    # 사용자/기관 바인딩도 검증
    assert _tileserver_verify(tok, "2", "YU", "SA-HST-001") is False
    assert _tileserver_verify(tok, "1", "CNU", "SA-HST-001") is False


def test_tileserver_token_contract_tampered_and_expired():
    """[블로커1] 서명 변조·만료 토큰은 거부."""
    import hmac as _h, hashlib as _hh
    tok = generate_tile_token("1", "YU", "SA-HST-001")
    exp_str, sig = tok.split(":", 1)
    tampered = f"{exp_str}:{'0'*len(sig)}"
    assert _tileserver_verify(tampered, "1", "YU", "SA-HST-001") is False
    # 만료 토큰: 과거 exp 로 직접 서명
    past = int(datetime.now(timezone.utc).timestamp()) - 10
    msg = f"1:YU:SA-HST-001:{past}"
    s = _h.new(os.environ["JWT_SECRET_KEY"].encode(), msg.encode(), _hh.sha256).hexdigest()
    assert _tileserver_verify(f"{past}:{s}", "1", "YU", "SA-HST-001") is False


# ════════════════════════════════════════════════════════════════════════
# 실사용 단계 경계·상태전이·집계 정합성 시나리오 (edge-scenarios-2026-06)
#
# 한계 명시: RDS 직접 접속 불가로 DB는 mock(cursor.fetchone side_effect)으로 구동한다.
# 따라서 SQL WHERE 부등호(<=,>=) 자체의 의미는 DB가 실행하므로 mock으로는 검증 불가.
# 이 시나리오들은 (1) Python 측 경계 비교·fail-closed 분기, (2) today 소스가 KST인지,
# (3) 집계가 어떤 컬럼/테이블을 기준으로 하는지(SQL 문자열 근거), (4) 게이트 분기를 검증한다.
# 집계/스키마 정합성(5·9)은 실행된 SQL 문자열·DDL 파일을 근거로 한 정적 검증이다.
# ════════════════════════════════════════════════════════════════════════

# ── 공통 헬퍼: 로그인 row (9컬럼) ──
def _login_row(status="active", subscription_end=None, is_special=False,
               special_expires_at=None, locked_at=None, pw="password"):
    from werkzeug.security import generate_password_hash
    return (1, "YU", "student", is_special,
            generate_password_hash(pw), status, locked_at, special_expires_at,
            subscription_end)


# ─────────────────────── A. 접근창·만료 경계 ───────────────────────

# 시나리오 1a: _today_kst()가 서버 로컬 TZ와 무관하게 UTC+9(KST)로 산출되는가
def test_s1_today_kst_is_utc_plus_9_and_tz_independent(monkeypatch):
    """[시나리오1] _today_kst()는 서버 TZ(UTC/America/New_York 등) 설정과 무관하게
    동일한 KST 날짜를 낸다. UTC 15:30(06-01)은 KST 00:30(06-02) → 날짜가 하루 넘어감(9h 차이 검증)."""
    import time as _time
    from datetime import datetime as _dt, timezone as _tz, date as _date
    import auth.decorators as deco

    fixed_utc = _dt(2026, 6, 1, 15, 30, tzinfo=_tz.utc)  # KST로는 2026-06-02 00:30

    class _FakeDatetime:
        @staticmethod
        def now(tz=None):
            return fixed_utc
    monkeypatch.setattr(deco, "datetime", _FakeDatetime)

    # 순수 UTC .date()였다면 06-01 이 나왔을 것 — KST는 06-02 여야 한다(9시간 경계).
    assert fixed_utc.date() == _date(2026, 6, 1)
    expected_kst = _date(2026, 6, 2)

    saved_tz = os.environ.get("TZ")
    try:
        for tzname in ("UTC", "America/New_York", "Asia/Kolkata", "Asia/Seoul"):
            os.environ["TZ"] = tzname
            try:
                _time.tzset()
            except AttributeError:
                pass  # Windows: tzset 없음 — 그래도 now(utc)는 절대시각이라 무관
            assert deco._today_kst() == expected_kst, f"TZ={tzname} 에서 KST 날짜가 어긋남"
    finally:
        if saved_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = saved_tz
        try:
            _time.tzset()
        except AttributeError:
            pass


# 시나리오 1b/3: 만료 경계 — subscription_end == today 는 통과(<=포함), today-1 은 차단
def test_s1_s3_login_boundary_subscription_end_inclusive(client, mock_db, monkeypatch):
    """[시나리오1·3] login 의 Python 만료 비교는 subscription_end >= today(당일 포함).
    today == end → 통과(200). end == today-1 → SUBSCRIPTION_EXPIRED(403)."""
    import auth.auth as aa
    from datetime import date as _date
    D = _date(2026, 6, 1)
    monkeypatch.setattr(aa, "_today_kst", lambda: D)

    # (3) today == subscription_end → 접근 허용
    with patch("server_render.get_db_conn") as g1, patch("server_render.release_db_conn"):
        g1.return_value = mock_db["conn"]
        mock_db["cursor"].fetchone.return_value = _login_row(subscription_end=D)
        resp = client.post("/api/auth/login",
                           json={"email": "t@example.com", "password": "password"})
        assert resp.status_code == 200, "당일(== end)은 통과해야 함(<= 경계 포함)"
        assert resp.get_json()["success"] is True

    # (1b) 다음날(today = end+1 → end == today-1) → 차단
    with patch("server_render.get_db_conn") as g2, patch("server_render.release_db_conn"):
        g2.return_value = mock_db["conn"]
        mock_db["cursor"].fetchone.return_value = _login_row(subscription_end=D - timedelta(days=1))
        resp = client.post("/api/auth/login",
                           json={"email": "t@example.com", "password": "password"})
        assert resp.status_code == 403
        assert resp.get_json()["error"] == "SUBSCRIPTION_EXPIRED"


# 시나리오 2: access_open_date 하루 전 — 미래 active 구독이 있어도 접근창 전엔 가입·로그인 차단
def test_s2_before_access_window_blocks_login_and_register(client, mock_db, monkeypatch):
    """[시나리오2/Codex#3] 미래 학기 구독이 status='active'여도 access_open_date 전이면
    접근창 쿼리가 매칭 0건 → login(subscription_end=None)→SUBSCRIPTION_EXPIRED,
    register(매칭 구독 None)→SUBSCRIPTION_INACTIVE."""
    import auth.auth as aa
    from datetime import date as _date
    monkeypatch.setattr(aa, "_today_kst", lambda: _date(2026, 6, 1))

    # login: 접근창 밖이므로 subquery(subscription_end)=None → fail-closed
    with patch("server_render.get_db_conn") as g1, patch("server_render.release_db_conn"):
        g1.return_value = mock_db["conn"]
        mock_db["cursor"].fetchone.return_value = _login_row(subscription_end=None)
        resp = client.post("/api/auth/login",
                           json={"email": "t@example.com", "password": "password"})
        assert resp.status_code == 403
        assert resp.get_json()["error"] == "SUBSCRIPTION_EXPIRED"

    # register: 접근창 내 active 구독 매칭 0건 → SUBSCRIPTION_INACTIVE
    with patch("server_render.get_db_conn") as g2, patch("server_render.release_db_conn"):
        g2.return_value = mock_db["conn"]
        mock_db["cursor"].fetchone.side_effect = [
            ("HST",),   # roster subject_code
            None,        # 기존 user 없음
            None,        # 접근창 내 active 구독 없음 → 거부
        ]
        resp = client.post("/api/auth/register",
                           json={"email": "t@example.com", "password": "pw",
                                 "role": "student", "institution_id": "YU"})
        assert resp.status_code == 403
        assert resp.get_json()["error"] == "SUBSCRIPTION_INACTIVE"


# 시나리오 4: 학기 사이 공백 → 차단, 다음 학기 access_open_date 도래 → 통과
def test_s4_inter_term_gap_blocks_then_opens(client, mock_db, monkeypatch):
    """[시나리오4] 이전 학기 만료 + 다음 학기 구독 존재. 두 접근창 사이 공백엔 차단(매칭 None),
    다음 학기 창이 열리면 매칭되어 통과. (동일 fail-closed 메커니즘의 시간 전이 표현.)"""
    import auth.auth as aa
    from datetime import date as _date

    # 공백 기간: 접근창 매칭 없음 → None → 차단
    monkeypatch.setattr(aa, "_today_kst", lambda: _date(2026, 8, 15))  # 가을학기 오픈(8/1~ 가정) 이전 공백
    with patch("server_render.get_db_conn") as g1, patch("server_render.release_db_conn"):
        g1.return_value = mock_db["conn"]
        mock_db["cursor"].fetchone.return_value = _login_row(subscription_end=None)
        resp = client.post("/api/auth/login",
                           json={"email": "t@example.com", "password": "password"})
        assert resp.status_code == 403
        assert resp.get_json()["error"] == "SUBSCRIPTION_EXPIRED"

    # 다음 학기 창 도래: 매칭되어 유효 subscription_end 반환 → 통과
    monkeypatch.setattr(aa, "_today_kst", lambda: _date(2026, 9, 1))
    with patch("server_render.get_db_conn") as g2, patch("server_render.release_db_conn"):
        g2.return_value = mock_db["conn"]
        mock_db["cursor"].fetchone.return_value = _login_row(
            subscription_end=_date(2027, 2, 28))
        resp = client.post("/api/auth/login",
                           json={"email": "t@example.com", "password": "password"})
        assert resp.status_code == 200


# ─────────────────────── B. 자동해제 상태전이 ───────────────────────

# 시나리오 6: 미검증 계정 자동해제 → pending 유지(active 안 됨)
def test_s6_unverified_autounlock_stays_pending(client, mock_db):
    """[시나리오6/블로커4] pending_verification → locked → 24h 후 자동해제 시 active 승급 금지.
    정답 비번 로그인해도 403 ACCOUNT_INACTIVE."""
    from werkzeug.security import generate_password_hash
    with patch("server_render.get_db_conn") as g1, patch("server_render.release_db_conn"):
        g1.return_value = mock_db["conn"]
        locked_at = datetime.now(timezone.utc) - timedelta(hours=25)
        mock_db["cursor"].fetchone.side_effect = [
            (1, "YU", "student", False, generate_password_hash("password"),
             "locked", locked_at, None,
             datetime.now(timezone.utc).date() + timedelta(days=365)),
            (None,),  # _check_auto_unlock: last_login NULL → 미검증
        ]
        resp = client.post("/api/auth/login",
                           json={"email": "t@example.com", "password": "password"})
        assert resp.status_code == 403
        assert resp.get_json()["error"] == "ACCOUNT_INACTIVE"


# ─────────────────────── C. 좌석 카운터 정합성 ───────────────────────

# 시나리오 8: 정원 경계 — max_seats 꽉 참 → 가입/인증 거부
def test_s8_capacity_full_blocks_register(client, mock_db, monkeypatch):
    """[시나리오8] register: active_count >= max_seats 면 CAPACITY_EXCEEDED(409). 단건 순차 경계."""
    import auth.auth as aa
    from datetime import date as _date
    monkeypatch.setattr(aa, "_today_kst", lambda: _date(2026, 6, 1))
    with patch("server_render.get_db_conn") as g1, patch("server_render.release_db_conn"):
        g1.return_value = mock_db["conn"]
        mock_db["cursor"].fetchone.side_effect = [
            ("HST",),   # roster
            None,        # 기존 user 없음
            (2,),        # max_seats = 2
            (2,),        # active_count = 2 → 2>=2 초과
        ]
        resp = client.post("/api/auth/register",
                           json={"email": "t@example.com", "password": "pw",
                                 "role": "student", "institution_id": "YU"})
        assert resp.status_code == 409
        assert resp.get_json()["error"] == "CAPACITY_EXCEEDED"


def test_s8_capacity_full_blocks_verify_email(client, mock_db, monkeypatch):
    """[시나리오8] verify_email: 좌석 재검사(동시성 방어, FOR UPDATE)도 active_count>=max_seats 차단."""
    import auth.auth as aa
    from datetime import date as _date
    monkeypatch.setattr(aa, "_today_kst", lambda: _date(2026, 6, 1))
    future = datetime.now(timezone.utc) + timedelta(minutes=5)
    with patch("server_render.get_db_conn") as g1, patch("server_render.release_db_conn"):
        g1.return_value = mock_db["conn"]
        mock_db["cursor"].fetchone.side_effect = [
            (1, "YU", "student", False, "HST"),       # user (pending)
            (10, "123456", future, False, 0),          # email_verifications row
            (2,),                                       # max_seats
            (2,),                                       # active_count → 초과
        ]
        resp = client.post("/api/auth/verify-email",
                           json={"email": "t@example.com", "code": "123456"})
        assert resp.status_code == 409
        assert resp.get_json()["error"] == "CAPACITY_EXCEEDED"


# 시나리오 7: 가입→삭제→재가입 좌석 반환 — 좌석 카운터 기준 검증 + 삭제 경로 부재 노출
def test_s7_register_capacity_counts_active_users(client, mock_db, monkeypatch):
    """[시나리오7] 가입 정원 게이트의 좌석 카운터 기준은 COUNT(users WHERE status='active').
    좌석이 빈 상태(active_count < max_seats)면 가입 통과 → 점유. (반환=행 삭제/비활성이지만
    학생 삭제 엔드포인트가 코드에 없음 — 보고서 (b) 참조.)"""
    import auth.auth as aa
    from datetime import date as _date
    monkeypatch.setattr(aa, "_today_kst", lambda: _date(2026, 6, 1))
    with patch("server_render.get_db_conn") as g1, patch("server_render.release_db_conn"), \
         patch("auth.auth.send_verification_email", return_value=None):
        g1.return_value = mock_db["conn"]
        mock_db["cursor"].fetchone.side_effect = [
            ("HST",),   # roster
            None,        # 기존 user 없음
            (50,),       # max_seats = 50
            (10,),       # active_count = 10 < 50 → 여유
            (123,),      # INSERT users RETURNING id
        ]
        resp = client.post("/api/auth/register",
                           json={"email": "new@example.com", "password": "pw",
                                 "role": "student", "institution_id": "YU"})
        assert resp.status_code == 200
        # 좌석 카운터 기준이 users.status='active' 임을 실행된 SQL로 확인
        sqls = " ".join(str(c.args[0]) for c in mock_db["cursor"].execute.call_args_list)
        assert "COUNT(*)" in sqls and "status = 'active'" in sqls


def test_s7_no_student_delete_route_exists():
    """[시나리오7] §9 '학생 삭제 시 좌석 반환' 흐름의 전제인 roster/학생 삭제 라우트가
    현재 서버에 존재하지 않음을 노출(좌석 반환 흐름 미구현)."""
    from server_render import app as _app
    rules = [str(r) for r in _app.url_map.iter_rules()]
    # users/roster 를 DELETE 하는 학생 관리 라우트가 없음(공지/슬라이드 삭제만 존재)
    student_delete = [r for r in rules if ("roster" in r.lower() or "student" in r.lower())]
    assert student_delete == [], f"예상과 달리 학생/roster 라우트 발견: {student_delete}"


# 시나리오 9: 한 학생 두 과목 — register 는 단일 과목만 채번 + 스키마가 다과목 N-레코드 불가
def test_s9_register_captures_single_subject_only(client, mock_db, monkeypatch):
    """[시나리오9/D12] register 의 roster 조회는 ORDER BY subject_code LIMIT 1 →
    한 이메일이 두 과목 명단에 있어도 가장 이른 과목 1건만 채번(두 번째 과목 미등록)."""
    import auth.auth as aa
    from datetime import date as _date
    monkeypatch.setattr(aa, "_today_kst", lambda: _date(2026, 6, 1))
    with patch("server_render.get_db_conn") as g1, patch("server_render.release_db_conn"), \
         patch("auth.auth.send_verification_email", return_value=None):
        g1.return_value = mock_db["conn"]
        # roster 가 (HST, PARA) 두 행이어도 LIMIT 1 → 'HST' 한 건만 반환되도록 mock
        mock_db["cursor"].fetchone.side_effect = [
            ("HST",),   # roster: ORDER BY subject_code LIMIT 1 → 'HST'
            None,        # 기존 user 없음
            (50,),       # max_seats
            (0,),        # active_count
            (200,),      # INSERT RETURNING id
        ]
        resp = client.post("/api/auth/register",
                           json={"email": "dual@example.com", "password": "pw",
                                 "role": "student", "institution_id": "YU"})
        assert resp.status_code == 200
        # INSERT 된 users.subject_code 가 단일('HST')임을 확인 — PARA 는 별도 가입 불가
        insert_calls = [c for c in mock_db["cursor"].execute.call_args_list
                        if "INSERT INTO users" in str(c.args[0])]
        assert insert_calls, "users INSERT 가 실행되지 않음"
        params = insert_calls[0].args[1]
        assert "HST" in params and "PARA" not in params


def test_s9_schema_blocks_multi_subject_records():
    """[시나리오9/D12] 실제 DDL이 다과목 N-레코드 모델을 막는다는 근거(스키마 파일).
    users.email UNIQUE(전역) + institution_rosters UNIQUE(institution_id, email) →
    동일 이메일의 과목별 독립 레코드 불가. CLAUDE.md §7(UNIQUE(institution_id,subject_code,email))과 불일치."""
    import os as _os
    base = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    with open(_os.path.join(base, "db", "schema.sql"), encoding="utf-8") as f:
        schema = f.read()
    with open(_os.path.join(base, "db", "auth_schema.sql"), encoding="utf-8") as f:
        auth_schema = f.read()
    # users.email 이 전역 UNIQUE (복합 UNIQUE 아님)
    assert "email           VARCHAR(200) UNIQUE NOT NULL" in schema
    # roster UNIQUE 에 subject_code 없음
    assert "UNIQUE(institution_id, email)" in auth_schema
    assert "UNIQUE(institution_id, subject_code, email)" not in auth_schema


# ─────────────────────── D. 슬라이드 상태 경계 (2축) ───────────────────────

def _gate_eval(slide_tuple, *, subject="HST", inst="YU", is_special=False, access=True):
    """_slide_access_allowed 를 request context + g 세팅으로 평가."""
    from server_render import _slide_access_allowed
    from flask import g
    with app.test_request_context():
        g.user_id = 1
        g.institution_id = inst
        g.subject_code = subject
        g.is_special = is_special
        with patch("server_render.get_slide_institution", return_value=slide_tuple), \
             patch("server_render._institution_subject_access", return_value=access):
            return _slide_access_allowed("SA-HST-001")


# 시나리오 10: ready 비배포 → 학생 비노출 (변환완료 != 배포)
def test_s10_ready_not_deployed_blocked(client, mock_db):
    """[시나리오10] conversion_status='ready'여도 deploy_status != 'deployed' 면 게이트 차단(403).
    게이트는 deploy_status만 보고 conversion_status는 보지 않는다(§4-5)."""
    # get_slide_institution 은 (institution_id, subject_code, deploy_status) 반환 — conversion_status 무관
    allowed, err = _gate_eval(("SA", "HST", "qc_pending"))
    assert allowed is False
    assert err.status_code == 403

    # 목록(_visible_slides)에서도 제외
    from server_render import _visible_slides
    with app.test_request_context():
        from flask import g
        g.is_special = False
        g.subject_code = "HST"
        g.institution_id = "YU"
        with patch("server_render._institution_subject_access", return_value=True):
            vis = _visible_slides([
                {"id": "SA-HST-001", "deploy_status": "qc_pending", "subject_code": "HST"},
                {"id": "SA-HST-002", "deploy_status": "deployed", "subject_code": "HST"},
            ])
    assert [s["id"] for s in vis] == ["SA-HST-002"]


# 시나리오 11: revoked 즉시 차단 (deployed → revoke → qc_pending)
def test_s11_revoked_immediately_blocked(client, mock_db):
    """[시나리오11] 배포 슬라이드가 철회되면 deploy_status='deployed'→'qc_pending'(§7 revoked→qc_pending).
    동일 슬라이드가 배포 상태에선 통과, 철회 후 상태에선 즉시 차단됨을 게이트로 확인."""
    # 배포 상태: 통과
    allowed_before, _ = _gate_eval(("SA", "HST", "deployed"))
    assert allowed_before is True
    # 철회 후 상태(qc_pending): 차단
    allowed_after, err = _gate_eval(("SA", "HST", "qc_pending"))
    assert allowed_after is False
    assert err.status_code == 403

    # 철회 엔드포인트 SQL 이 deployed→qc_pending 전이임을 근거로 확인
    import server_render as _sr, inspect
    src = inspect.getsource(_sr.api_slide_revoke)
    assert "deploy_status='qc_pending'" in src and "deploy_status='deployed'" in src


# 시나리오 12: ready_no_mpp 서빙 — 배포되면 타일 정상 서빙(배율만 별도 비활성)
def test_s12_ready_no_mpp_served_when_deployed(client, mock_db):
    """[시나리오12] conversion_status='ready_no_mpp' + deploy_status='deployed' → 게이트 통과(서빙).
    게이트는 conversion_status를 보지 않으므로 ready_no_mpp도 배포되면 타일 응답 정상.
    (배율 비활성은 뷰어 측 mpp 처리 — 게이트 책임 아님.)"""
    allowed, err = _gate_eval(("SA", "HST", "deployed"))  # deploy_status='deployed'
    assert allowed is True and err is None


# ─────────────────────── B(추가). 만료 구독의 집계 동결 ───────────────────────

# 시나리오 5: 만료 구독 학생이 좌석/리포트 '활성' 집계에서 빠지는가 (집계 기준 검증)
def test_s5_active_user_aggregation_basis_is_users_status_not_subscription(client, mock_db):
    """[시나리오5/D9] 이용 리포트의 '활성 사용자' 집계가 무엇을 기준으로 하는지 실행 SQL로 확인.
    현재 구현은 COUNT(users WHERE status='active') 기준이며 subscriptions(유효 구독 창)와
    조인하지 않는다. 따라서 구독이 만료돼도 users.status가 active로 남으면 집계가 0으로
    동결되지 않는다(만료 시 status를 바꾸는 배치/트리거 부재). → 보고서 (b) 결함."""
    with patch("server_render.get_db_conn") as g1, patch("server_render.release_db_conn"):
        g1.return_value = mock_db["conn"]
        mock_db["cursor"].fetchone.side_effect = [
            (1, "super_admin", "Admin", "active"),  # _get_admin_user
            (5,),     # active_users (users.status='active')
            (150,),   # max_seats (subscriptions)
            (300,),   # total_views
            (40,),    # ai_questions
            (None,),  # last_activity
        ]
        _admin_session(client, "admin-csrf")
        resp = client.get("/admin/api/reports/kpi?inst_id=YU&subject_code=HST&period=all")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["active_users"] == 5  # mock 이 그대로 반환 — 집계가 status 기준임을 전제

        # 활성 사용자 집계 SQL 추출: COUNT(u.id) / FROM users / status='active'
        active_sql = None
        for c in mock_db["cursor"].execute.call_args_list:
            s = str(c.args[0])
            if "COUNT(u.id)" in s and "FROM" in s and "users" in s and "status" in s:
                active_sql = s
                break
        assert active_sql is not None, "활성 사용자 집계 SQL 을 찾지 못함"
        # (b) 근거 1: subscriptions(유효 구독 창)와 조인/필터하지 않음 → 만료돼도 집계 미동결
        assert "subscription" not in active_sql.lower()
        # (b) 근거 2: subject_code 로 분리하지 않음 → 과목별 산출 아님(기관 전체 합산), §18 D9
        assert "subject_code" not in active_sql


def test_s5_dashboard_active_user_kpi_also_status_based():
    """[시나리오5/D9] 대시보드 KPI '활성 사용자'도 동일하게 users.status 기준이며 subscriptions
    유효성과 무관함을 소스로 확인(다중 쿼리 mock 회피 위해 정적 검증)."""
    import server_render as _sr, inspect
    src = inspect.getsource(_sr.api_dashboard)
    # KPI3 활성 사용자 블록: users 를 status='active' 로 카운트
    assert "SELECT COUNT(*) FROM users" in src
    assert "status, 'active') = 'active'" in src
    # 해당 카운트가 subscriptions 와 조인되지 않음(블록 단위 근거): users 카운트 줄에
    # subscription_end 조건이 붙지 않는다 — 만료 사용자도 집계됨.
    idx = src.find("SELECT COUNT(*) FROM users")
    snippet = src[idx:idx + 200]
    assert "subscription" not in snippet.lower()
