"""
6번 A안 — login·verify-email 응답에 position(랜딩 힌트) additive 추가 검증.

CLAUDE.md §13-2(반환 shape 추가는 additive — 기존 필드·값 불변). position 은 랜딩 분기용 힌트일 뿐,
권한 게이트는 서버 _course_position(매 요청 DB)이 별도 판정(프론트 position 위조로 우회 불가).

DB 는 mock. position 은 main transaction 과 분리된 _fetch_position 의 별도 조회 → fetchone 마지막에 1개 추가.
"""
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest")
os.environ.setdefault("GMAIL_USER", "test@gmail.com")
os.environ.setdefault("GMAIL_APP_PW", "test-app-pw")
os.environ.setdefault("ADMIN_SECRET_KEY", "test-admin-secret-for-pytest")

import pytest
from werkzeug.security import generate_password_hash
from server_render import app

FUTURE = datetime.now(timezone.utc).date() + timedelta(days=365)


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _conn():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    conn.cursor.return_value.__exit__.return_value = None
    return conn, cur


# ── login: position additive + 기존 필드 불변 ──
def test_login_success_includes_position(client):
    conn, cur = _conn()
    cur.fetchone.side_effect = [
        # login 메인쿼리 10컬럼
        (1, "YU", "viewer", "HST", False, generate_password_hash("password1"),
         "active", None, None, FUTURE),
        ("교수",),   # _fetch_position
    ]
    with patch("server_render.get_db_conn", return_value=conn), \
         patch("server_render.release_db_conn"):
        resp = client.post("/api/auth/login",
                           json={"email": "p@b.c", "password": "password1"})
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["position"] == "교수"                    # 랜딩 힌트 추가됨
    for k in ("user_id", "institution_id", "role", "subject_code", "csrf_token"):
        assert k in data                                  # 기존 필드 불변(additive)


def test_login_success_position_none_when_lookup_empty(client):
    """position 조회가 빈 결과여도 200·position=None(랜딩 /home 폴백) — 인증 깨지지 않음."""
    conn, cur = _conn()
    cur.fetchone.side_effect = [
        (1, "YU", "viewer", "HST", False, generate_password_hash("password1"),
         "active", None, None, FUTURE),
        None,   # _fetch_position → 없음
    ]
    with patch("server_render.get_db_conn", return_value=conn), \
         patch("server_render.release_db_conn"):
        resp = client.post("/api/auth/login",
                           json={"email": "p@b.c", "password": "password1"})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["position"] is None


# ── verify-email: position additive ──
def test_verify_success_includes_position(client):
    conn, cur = _conn()
    cur.fetchone.side_effect = [
        (1, "YU", "viewer", False, "HST"),                       # user
        (1, "123456", datetime.now(timezone.utc) + timedelta(minutes=5), False, 0),  # ev
        (100,),                                                  # active_window_subscription max_seats
        (5,),                                                    # active_seat_count
        ("조교",),                                               # _fetch_position
    ]
    with patch("server_render.get_db_conn", return_value=conn), \
         patch("server_render.release_db_conn"):
        resp = client.post("/api/auth/verify-email",
                           json={"email": "p@b.c", "code": "123456"})
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["position"] == "조교"
    for k in ("user_id", "institution_id", "role", "subject_code", "csrf_token"):
        assert k in data


# ── [Codex Low] verify·login position 둘 다 '맨 뒤', 기존 필드 순서 동일 ──
def test_position_is_last_field_both_login_and_verify(client):
    # login
    conn, cur = _conn()
    cur.fetchone.side_effect = [
        (1, "YU", "viewer", "HST", False, generate_password_hash("password1"),
         "active", None, None, FUTURE),
        ("교수",),
    ]
    with patch("server_render.get_db_conn", return_value=conn), \
         patch("server_render.release_db_conn"):
        ld = client.post("/api/auth/login",
                         json={"email": "p@b.c", "password": "password1"}).get_json()["data"]
    # verify
    conn2, cur2 = _conn()
    cur2.fetchone.side_effect = [
        (1, "YU", "viewer", False, "HST"),
        (1, "123456", datetime.now(timezone.utc) + timedelta(minutes=5), False, 0),
        (100,), (5,), ("교수",),
    ]
    with patch("server_render.get_db_conn", return_value=conn2), \
         patch("server_render.release_db_conn"):
        vd = client.post("/api/auth/verify-email",
                         json={"email": "p@b.c", "code": "123456"}).get_json()["data"]
    # Flask 가 키를 알파벳 정렬해 직렬화하므로 wire 순서는 login·verify 가 이미 동일.
    #   (Codex Low 의 'verify 가 position 을 중간 삽입' 은 소스 dict 한정 — 본 수정으로 소스도 통일.)
    assert "position" in ld and "position" in vd
    assert list(ld.keys()) == list(vd.keys())   # 두 응답 키 순서 완전 동일(직렬화 일관)
    for k in ("user_id", "institution_id", "role", "subject_code", "csrf_token"):
        assert k in ld and k in vd               # 기존 필드 전부 보존(additive)


# ── 인증 실패 경로는 position 조회 전에 반환(부가조회 미발생) ──
def test_login_failure_does_not_break(client):
    conn, cur = _conn()
    cur.fetchone.return_value = None      # 사용자 없음 → INVALID_CREDENTIALS
    with patch("server_render.get_db_conn", return_value=conn), \
         patch("server_render.release_db_conn"):
        resp = client.post("/api/auth/login",
                           json={"email": "p@b.c", "password": "password1"})
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "INVALID_CREDENTIALS"
