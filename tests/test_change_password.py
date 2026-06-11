"""
D31 — 로그인 사용자 본인 비밀번호 변경(POST /api/auth/change-password) pytest.

CLAUDE.md §8(세션·동시접속)·§13-2(인증 반환 shape 불변)·IDOR 금지.
핵심 단언:
  1. 본인만(IDOR 차단) — scope=g.user_id, body user_id 무시(타인 비번 변경 불가).
  2. 현재 비밀번호 검증 — 틀리면 CURRENT_PASSWORD_INVALID(403, UPDATE 안 함), 맞아야만 변경.
  3. 새 비번 정책 — 8자 미만 WEAK_PASSWORD(conn 전 거부), new==current SAME_PASSWORD.
  4. 성공 시 password_hash + session_token 회전(세션 무효화) + 새 쿠키 재발급.

DB 는 mock. _authenticate(login_required) → 첫 fetchone, change SELECT → 둘째 fetchone.
"""
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest")
os.environ.setdefault("GMAIL_USER", "test@gmail.com")
os.environ.setdefault("GMAIL_APP_PW", "test-app-pw")
os.environ.setdefault("ADMIN_SECRET_KEY", "test-admin-secret-for-pytest")

import pytest
from werkzeug.security import generate_password_hash
from server_render import app
from auth.decorators import encode_token, COOKIE_NAME

URL = "http://localhost/api/auth/change-password"
SESSION = "valid-session-123"
CSRF = "test-csrf-token-1234"


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _mock_db():
    from unittest.mock import MagicMock
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    conn.cursor.return_value.__exit__.return_value = None
    return conn, cur


def _auth_row(role="viewer", subject="HST", is_special=False, inst="YU"):
    # _authenticate 메인쿼리 8컬럼: (session_token, status, subject_code, special_expires_at,
    #                               role, is_special, institution_id, subscription_end)
    return (SESSION, "active", subject, None, role, is_special, inst,
            datetime.now(timezone.utc).date() + timedelta(days=365))


def _login(client, uid="1"):
    payload = {"sub": uid, "institution_id": "YU", "role": "viewer",
               "session_token": SESSION, "is_special": False}
    client.set_cookie(COOKIE_NAME, encode_token(payload))
    client.set_cookie("csrf_token", CSRF)


def _execs(cur):
    return [str(c.args[0]) for c in cur.execute.call_args_list]


def _update_calls(cur):
    return [c for c in cur.execute.call_args_list
            if "UPDATE users SET password_hash" in str(c.args[0])]


# ─────────────────────────────────────────────
# 1. 성공 — 현재 비번 일치 + 새 비번 유효 → 변경 + 세션 회전
# ─────────────────────────────────────────────
def test_change_password_success(client):
    conn, cur = _mock_db()
    cur.fetchone.side_effect = [
        _auth_row(),                                          # _authenticate
        (generate_password_hash("oldpass12"), "YU", "viewer", False),  # change SELECT
    ]
    _login(client, uid="1")
    with patch("server_render.get_db_conn", return_value=conn), \
         patch("server_render.release_db_conn"):
        resp = client.post(URL, headers={"X-CSRF-Token": CSRF},
                           json={"current_password": "oldpass12", "new_password": "newpass34"})
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True
    ups = _update_calls(cur)
    assert len(ups) == 1
    # UPDATE 파라미터: (new_hash, session_token, user_id) — user_id 는 g(토큰 sub='1')
    args = ups[0].args[1]
    assert args[2] == "1"                       # scope=g.user_id
    assert args[0] != generate_password_hash    # 새 해시(상수 아님)
    # 세션 회전: 새 쿠키 재발급(access_token + csrf)
    setc = " ".join(resp.headers.getlist("Set-Cookie"))
    assert COOKIE_NAME in setc and "csrf_token" in setc


# ─────────────────────────────────────────────
# 2. 현재 비밀번호 오류 → 403, UPDATE 안 함
# ─────────────────────────────────────────────
def test_change_password_wrong_current_rejected(client):
    conn, cur = _mock_db()
    cur.fetchone.side_effect = [
        _auth_row(),
        (generate_password_hash("oldpass12"), "YU", "viewer", False),
    ]
    _login(client)
    with patch("server_render.get_db_conn", return_value=conn), \
         patch("server_render.release_db_conn"):
        resp = client.post(URL, headers={"X-CSRF-Token": CSRF},
                           json={"current_password": "WRONGpass", "new_password": "newpass34"})
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "CURRENT_PASSWORD_INVALID"
    assert _update_calls(cur) == []             # 비번 변경 안 됨


# ─────────────────────────────────────────────
# 3. ★ IDOR — body user_id 무시, 항상 g.user_id 만 변경
# ─────────────────────────────────────────────
def test_change_password_idor_ignores_body_user_id(client):
    conn, cur = _mock_db()
    cur.fetchone.side_effect = [
        _auth_row(),
        (generate_password_hash("oldpass12"), "YU", "viewer", False),
    ]
    _login(client, uid="1")
    with patch("server_render.get_db_conn", return_value=conn), \
         patch("server_render.release_db_conn"):
        resp = client.post(URL, headers={"X-CSRF-Token": CSRF},
                           json={"current_password": "oldpass12", "new_password": "newpass34",
                                 "user_id": 999, "id": 999})   # 조작 시도
    assert resp.status_code == 200
    # SELECT·UPDATE 어디에도 999 가 파라미터로 쓰이지 않음 — scope=g.user_id('1')
    for c in cur.execute.call_args_list:
        params = c.args[1] if len(c.args) > 1 else ()
        assert 999 not in (params or ())
    ups = _update_calls(cur)
    assert ups and ups[0].args[1][2] == "1"     # g.user_id 만


# ─────────────────────────────────────────────
# 4. 새 비번 정책 — 8자 미만 거부(conn 전), new==current 거부
# ─────────────────────────────────────────────
def test_change_password_weak_rejected_before_db(client):
    conn, cur = _mock_db()
    cur.fetchone.side_effect = [_auth_row()]     # _authenticate 만(이후 진입 전 거부)
    _login(client)
    with patch("server_render.get_db_conn", return_value=conn), \
         patch("server_render.release_db_conn"):
        resp = client.post(URL, headers={"X-CSRF-Token": CSRF},
                           json={"current_password": "oldpass12", "new_password": "short"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "WEAK_PASSWORD"
    # change SELECT(비번 조회) 자체가 실행되지 않음
    assert not any("FROM users WHERE id = %s FOR UPDATE" in s for s in _execs(cur))


def test_change_password_same_as_current_rejected(client):
    conn, cur = _mock_db()
    cur.fetchone.side_effect = [
        _auth_row(),
        (generate_password_hash("oldpass12"), "YU", "viewer", False),
    ]
    _login(client)
    with patch("server_render.get_db_conn", return_value=conn), \
         patch("server_render.release_db_conn"):
        resp = client.post(URL, headers={"X-CSRF-Token": CSRF},
                           json={"current_password": "oldpass12", "new_password": "oldpass12"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "SAME_PASSWORD"
    assert _update_calls(cur) == []


# ─────────────────────────────────────────────
# 5. CSRF·인증 게이트 (login_required)
# ─────────────────────────────────────────────
def test_change_password_requires_csrf(client):
    conn, cur = _mock_db()
    cur.fetchone.side_effect = [_auth_row()]
    _login(client)
    with patch("server_render.get_db_conn", return_value=conn), \
         patch("server_render.release_db_conn"):
        resp = client.post(URL,   # X-CSRF-Token 없음
                           json={"current_password": "oldpass12", "new_password": "newpass34"})
    assert resp.status_code == 403


def test_change_password_requires_auth(client):
    resp = client.post(URL, json={"current_password": "x", "new_password": "newpass34"})
    assert resp.status_code == 401


# ─────────────────────────────────────────────
# 6. [Codex] 커넥션 누수 차단 — 검증실패 early return 에서도 release(acquire==release)
# ─────────────────────────────────────────────
def test_change_password_wrong_current_releases_connection(client):
    """현재 비번 오류 403 early return 에서도 conn release — acquire==release(누수 없음)."""
    conn, cur = _mock_db()
    cur.fetchone.side_effect = [
        _auth_row(),
        (generate_password_hash("oldpass12"), "YU", "viewer", False),
    ]
    _login(client)
    with patch("server_render.get_db_conn", return_value=conn) as gm, \
         patch("server_render.release_db_conn") as rm:
        resp = client.post(URL, headers={"X-CSRF-Token": CSRF},
                           json={"current_password": "WRONGpass", "new_password": "newpass34"})
    assert resp.status_code == 403
    assert gm.call_count == rm.call_count and gm.call_count >= 2   # _authenticate + change 둘 다 균형


def test_change_password_success_releases_connection(client):
    conn, cur = _mock_db()
    cur.fetchone.side_effect = [
        _auth_row(),
        (generate_password_hash("oldpass12"), "YU", "viewer", False),
    ]
    _login(client)
    with patch("server_render.get_db_conn", return_value=conn) as gm, \
         patch("server_render.release_db_conn") as rm:
        resp = client.post(URL, headers={"X-CSRF-Token": CSRF},
                           json={"current_password": "oldpass12", "new_password": "newpass34"})
    assert resp.status_code == 200
    assert gm.call_count == rm.call_count


def test_change_password_repeated_failure_no_pool_leak(client):
    """현재 비번 오류를 반복해도 매 요청 release — 풀 고갈(누적 미반환) 없음."""
    for _ in range(8):
        conn, cur = _mock_db()
        cur.fetchone.side_effect = [
            _auth_row(),
            (generate_password_hash("oldpass12"), "YU", "viewer", False),
        ]
        _login(client)
        with patch("server_render.get_db_conn", return_value=conn) as gm, \
             patch("server_render.release_db_conn") as rm:
            resp = client.post(URL, headers={"X-CSRF-Token": CSRF},
                               json={"current_password": "WRONGpass", "new_password": "newpass34"})
        assert resp.status_code == 403
        assert gm.call_count == rm.call_count


# ─────────────────────────────────────────────
# 7. [Codex sweep] resend-code 검증실패 early return 에서도 release
# ─────────────────────────────────────────────
def test_resend_code_early_return_releases_connection(client):
    """resend-code: 이미 인증된 계정(ALREADY_VERIFIED) early return 에서도 conn release(누수 없음)."""
    conn, cur = _mock_db()
    cur.fetchone.return_value = (1, "active")     # status='active' → ALREADY_VERIFIED(409) early return
    with patch("server_render.get_db_conn", return_value=conn) as gm, \
         patch("server_render.release_db_conn") as rm:
        resp = client.post("http://localhost/api/auth/resend-code", json={"email": "a@b.c"})
    assert resp.status_code == 409
    assert resp.get_json()["error"] == "ALREADY_VERIFIED"
    assert gm.call_count == rm.call_count == 1     # 검증실패 경로도 정확히 1회 release
