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
            (1, "YU", "student", False),
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
        
        # Login query: id, institution_id, role, is_special, pw_hash, status, locked_at, subscription_end
        # Then _check_and_increment_failed queries: failed_attempts, failed_window_start
        mock_db["cursor"].fetchone.side_effect = [
            (1, "YU", "student", False, correct_hash, "active", None,
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
            "new-session-token", "active", None  # session_token, status, subscription_end
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
            "valid-session-123", "pending_verification", None
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
            ("valid-session-123", "active", None),   # _authenticate: session_token, status, subscription_end
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
            "valid-session-123", "active", None   # session_token, status, subscription_end
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
            (1, "YU", "student", False, correct_hash, "active", None,
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
            (1, "YU", "student", False),
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

        mock_db["cursor"].fetchone.return_value = ("sess123", "active", None)

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

        mock_db["cursor"].fetchone.return_value = ("sess123", "active", None)

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
            "different-token-in-db", "active", None
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
            "valid-sess", "active", expired_date
        )

        resp = client.get("http://localhost/api/auth/me")

        assert resp.status_code == 401
        data = resp.get_json()
        assert data["error"] == "SUBSCRIPTION_EXPIRED"


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
            ("valid-sess", "active", expired_date),   # _authenticate
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
         patch("server_render.get_slide_institution") as mock_inst:
        mock_get_db.return_value = mock_db["conn"]
        mock_inst.return_value = ("YU", "deployed")  # inst_id, deploy_status (현 계약)

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

        mock_db["cursor"].fetchone.return_value = (
            "valid-sess", "active", None
        )

        # 타일 토큰 없이 DZI 접근 (?t= 미포함)
        resp = client.get("http://localhost/dzi/SA-HST-001.dzi")

        assert resp.status_code == 401
        data = resp.get_json()
        assert data["error"] == "TILE_TOKEN_INVALID"
        # 프론트 인터셉터가 로그인 세션 에러로 오판하지 않도록 구분
        assert data["error"] not in ("SESSION_REVOKED", "SUBSCRIPTION_EXPIRED", "TOKEN_INVALID")
