"""
register·verify_email·login 커넥션 누수 수정(전수 점검 후속) 검증.

CLAUDE.md §13-2(인증 의미·반환 shape 불변). 본 테스트는 '판정'이 아니라 '커넥션 정리'만 본다:
검증실패 early return 경로에서도 release_db_conn 이 정확히 1회 호출돼 acquire==release(풀 미고갈).

DB 는 mock — 각 라우트의 첫 분기(검증실패)로 진입시켜 release 균형만 단언한다.
"""
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest")
os.environ.setdefault("GMAIL_USER", "test@gmail.com")
os.environ.setdefault("GMAIL_APP_PW", "test-app-pw")
os.environ.setdefault("ADMIN_SECRET_KEY", "test-admin-secret-for-pytest")

import pytest
from server_render import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _mock_db():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    conn.cursor.return_value.__exit__.return_value = None
    return conn, cur


# ── register: EMAIL_EXISTS 검증실패 early return ──
def test_register_email_exists_releases_connection(client):
    conn, cur = _mock_db()
    cur.fetchone.return_value = (1,)         # 이미 가입된 이메일 → EMAIL_EXISTS(409)
    with patch("server_render.get_db_conn", return_value=conn) as gm, \
         patch("server_render.release_db_conn") as rm:
        resp = client.post("/api/auth/register",
                           json={"institution_id": "YU", "email": "a@b.c", "password": "password1"})
    assert resp.status_code == 409
    assert resp.get_json()["error"] == "EMAIL_EXISTS"
    assert gm.call_count == rm.call_count == 1   # 검증실패 early return 도 release


def test_register_repeated_email_exists_no_pool_leak(client):
    for _ in range(8):
        conn, cur = _mock_db()
        cur.fetchone.return_value = (1,)
        with patch("server_render.get_db_conn", return_value=conn) as gm, \
             patch("server_render.release_db_conn") as rm:
            resp = client.post("/api/auth/register",
                               json={"institution_id": "YU", "email": "a@b.c", "password": "password1"})
        assert resp.status_code == 409
        assert gm.call_count == rm.call_count == 1


# ── verify_email: USER_NOT_FOUND 검증실패 early return ──
def test_verify_user_not_found_releases_connection(client):
    conn, cur = _mock_db()
    cur.fetchone.return_value = None         # pending 사용자 없음 → USER_NOT_FOUND(404)
    with patch("server_render.get_db_conn", return_value=conn) as gm, \
         patch("server_render.release_db_conn") as rm:
        resp = client.post("/api/auth/verify-email",
                           json={"email": "a@b.c", "code": "123456"})
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "USER_NOT_FOUND"
    assert gm.call_count == rm.call_count == 1


# ── login: INVALID_CREDENTIALS(사용자 없음) 검증실패 early return ──
def test_login_invalid_credentials_releases_connection(client):
    conn, cur = _mock_db()
    cur.fetchone.return_value = None         # 사용자 없음 → INVALID_CREDENTIALS(401)
    with patch("server_render.get_db_conn", return_value=conn) as gm, \
         patch("server_render.release_db_conn") as rm:
        resp = client.post("/api/auth/login",
                           json={"email": "a@b.c", "password": "password1"})
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "INVALID_CREDENTIALS"
    assert gm.call_count == rm.call_count == 1


def test_login_email_not_verified_releases_connection(client):
    """pending_verification 사용자 로그인 → EMAIL_NOT_VERIFIED(403), release 1회."""
    conn, cur = _mock_db()
    # login 메인쿼리 10컬럼: (id, institution_id, role, subject_code, is_special,
    #                        password_hash, status, locked_at, special_expires_at, subscription_end)
    cur.fetchone.return_value = (
        1, "YU", "viewer", "HST", False, "x", "pending_verification", None, None,
        datetime.now(timezone.utc).date() + timedelta(days=365),
    )
    with patch("server_render.get_db_conn", return_value=conn) as gm, \
         patch("server_render.release_db_conn") as rm:
        resp = client.post("/api/auth/login",
                           json={"email": "a@b.c", "password": "password1"})
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "EMAIL_NOT_VERIFIED"
    assert gm.call_count == rm.call_count == 1


def test_login_repeated_invalid_no_pool_leak(client):
    for _ in range(8):
        conn, cur = _mock_db()
        cur.fetchone.return_value = None
        with patch("server_render.get_db_conn", return_value=conn) as gm, \
             patch("server_render.release_db_conn") as rm:
            resp = client.post("/api/auth/login",
                               json={"email": "a@b.c", "password": "password1"})
        assert resp.status_code == 401
        assert gm.call_count == rm.call_count == 1
