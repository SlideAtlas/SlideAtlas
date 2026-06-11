"""
LMS 3단계-B 학생 프론트 — 페이지 라우트 권한 가드 + 신규 표시/즐겨찾기/기록 API scope.

불변 원칙(어기면 reject):
 · 학생 페이지(/course/<id>·/mypage)는 새 권한 판정 로직을 만들지 않는다 — scope·존재는
   기존 학생 API(GET /api/courses/<cid>)가 판정. 페이지는 셸만 렌더.
 · 신규 favorites·history API 는 scope=g.user_id 강제(본인 것만, IDOR 차단). 타인 user_id 미참조.
 · 슬라이드 접근 판정(_slide_access_allowed)·_visible_slides·auth 무수정.

DB 는 mock(로컬 RDS 접속 불가) — 라우트 실행 경로의 fetch 시퀀스를 정확히 모킹한다.
"""
import os
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest")
os.environ.setdefault("GMAIL_USER", "test@gmail.com")
os.environ.setdefault("GMAIL_APP_PW", "test-app-pw")
os.environ.setdefault("ADMIN_SECRET_KEY", "test-admin-secret-for-pytest")

import pytest
import server_render as sr
from server_render import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _fake_auth(uid="5", inst="CNU", role="viewer", subject="HST", is_special=False):
    def f():
        from flask import g
        g.user_id = uid
        g.institution_id = inst
        g.role = role
        g.subject_code = subject
        g.is_special = is_special
        return None
    return f


def _mk_conn(fetchone=None, fetchall=None, rowcount=1):
    cur = MagicMock()
    if fetchone is not None:
        cur.fetchone.side_effect = list(fetchone)
    if fetchall is not None:
        cur.fetchall.side_effect = list(fetchall)
    cur.rowcount = rowcount
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    return conn, cur


def _stack(conn, auth=None, extra=None):
    auth = auth or _fake_auth()
    st = ExitStack()
    st.enter_context(patch("auth.decorators._authenticate", auth))
    st.enter_context(patch("auth.decorators._csrf_ok", lambda: True))
    st.enter_context(patch("server_render.get_db_conn", return_value=conn))
    st.enter_context(patch("server_render.release_db_conn"))
    for p in (extra or []):
        st.enter_context(p)
    return st


# ── /course/<cid> 페이지 라우트 ──────────────────────────────────────────────

def test_course_page_requires_auth(client):
    """비로그인 → page_login_required 가 랜딩(/)으로 redirect."""
    from urllib.parse import urlparse
    resp = client.get("/course/1")
    assert resp.status_code == 302
    assert urlparse(resp.headers["Location"]).path == "/"


def test_admin_only_redirected_from_course_page(client):
    """admin-only(role=admin·subject 없음, 콘텐츠 비소비) → /portal."""
    conn, _ = _mk_conn()
    with _stack(conn, _fake_auth(role="admin", subject=None)):
        resp = client.get("/course/1")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/portal")


def test_viewer_sees_course_page(client):
    """일반 viewer → 셸 렌더(데이터는 프론트가 GET /api/courses/<cid> 호출)."""
    conn, _ = _mk_conn()
    with _stack(conn, _fake_auth(role="viewer", subject="HST")):
        resp = client.get("/course/1")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "/api/courses/" in body          # 프론트가 기존 학생 API 호출
    assert "etoggleEnroll" not in body       # (셸 sanity)


# ── GET /api/courses/<cid> 표시 필드 보강(B-2) ───────────────────────────────

def test_course_detail_has_display_fields(client):
    """상세 응답에 게이트 무관 표시필드(professor_name·subject_name·슬라이드 organ)가 보강된다."""
    rows = [(10, 1, "1주차", None, 100, "SA-HST-001", 0, "위 점막", "H&E", "위")]
    conn, _ = _mk_conn(
        fetchone=[(1, "조직학 실습 A반", "2026 가을", 5), None, ("김조직",), ("조직학",)],
        fetchall=[rows],
    )
    with _stack(conn, _fake_auth(role="viewer", subject="HST")):
        resp = client.get("/api/courses/1")
    assert resp.status_code == 200
    c = resp.get_json()["course"]
    assert c["professor_name"] == "김조직"
    assert c["subject_name"] == "조직학"
    s = c["weeks"][0]["slides"][0]
    assert s["organ"] == "위"               # load_slides 'system'=자유텍스트 organ 표시축(§6-1)
    assert s["title_ko"] == "위 점막" and s["stain"] == "H&E"
    # 타일/토큰 필드가 새지 않는다(표시 메타만).
    assert "tile_token" not in s and "thumbnail_url" not in s


# ── /mypage 페이지 ───────────────────────────────────────────────────────────

def test_mypage_requires_auth(client):
    from urllib.parse import urlparse
    resp = client.get("/mypage")
    assert resp.status_code == 302
    assert urlparse(resp.headers["Location"]).path == "/"


def test_mypage_renders_profile(client):
    # 프로필 SELECT: (email, name, position, institution_name, subject_name)
    conn, _ = _mk_conn(fetchone=[("mj@cnu.ac.kr", "김민준", "학생", "충남대 의과대학", "조직학")])
    with _stack(conn, _fake_auth(role="viewer", subject="HST")):
        resp = client.get("/mypage")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "마이페이지" in body
    assert "김민준" in body and "충남대 의과대학" in body and "학생" in body
    # 소속·지위 읽기전용 안내 존재
    assert "직접 수정할 수 없습니다" in body


# ── GET /api/favorites — scope=g.user_id ─────────────────────────────────────

def test_favorites_list_scoped_to_user(client):
    conn, cur = _mk_conn(fetchall=[[("SA-HST-001", "위 점막", "위", "H&E")]])
    # 쿼리스트링으로 타인 user_id 를 넣어도 무시돼야 한다(scope=g.user_id).
    with _stack(conn, _fake_auth(uid="5", subject="HST")):
        resp = client.get("/api/favorites?user_id=999")
    assert resp.status_code == 200
    favs = resp.get_json()["favorites"]
    assert favs[0]["slide_id"] == "SA-HST-001" and favs[0]["organ"] == "위"
    # SELECT 파라미터[0] = g.user_id(=5, INT), [1] = g.subject_code — body/쿼리 user_id 미참조(IDOR 불가)
    sel = [c for c in cur.execute.call_args_list if "FROM favorites" in str(c.args[0])]
    assert sel and sel[0].args[1][0] == 5 and sel[0].args[1][1] == "HST"
    assert 999 not in sel[0].args[1]


# ── POST /api/favorites/<id> — 접근 게이트 통과만 ─────────────────────────────

def test_favorite_add_blocked_when_no_access(client):
    """접근권 없는 슬라이드는 _slide_access_allowed 가 막아 북마크 불가(INSERT 미실행)."""
    conn, cur = _mk_conn()
    extra = [patch("server_render._slide_access_allowed", return_value=(False, ("forbidden", 403)))]
    with _stack(conn, _fake_auth(uid="5", subject="HST"), extra=extra):
        resp = client.post("/api/favorites/SA-PATH-001")
    assert resp.status_code == 403
    inserts = [c for c in cur.execute.call_args_list if "INSERT INTO favorites" in str(c.args[0])]
    assert not inserts                       # 게이트 미통과 → INSERT 안 함


def test_favorite_add_inserts_for_accessible(client):
    conn, cur = _mk_conn()
    extra = [patch("server_render._slide_access_allowed", return_value=(True, None))]
    with _stack(conn, _fake_auth(uid="5", subject="HST"), extra=extra):
        resp = client.post("/api/favorites/SA-HST-001")
    assert resp.status_code == 200 and resp.get_json()["success"] is True
    ins = [c for c in cur.execute.call_args_list if "INSERT INTO favorites" in str(c.args[0])]
    assert ins and ins[0].args[1] == (5, "SA-HST-001")   # (g.user_id, slide_id)


# ── DELETE /api/favorites/<id> — 본인 행만 ───────────────────────────────────

def test_favorite_remove_scoped_to_user(client):
    conn, cur = _mk_conn()
    with _stack(conn, _fake_auth(uid="5", subject="HST")):
        resp = client.delete("/api/favorites/SA-HST-001")
    assert resp.status_code == 200
    dels = [c for c in cur.execute.call_args_list if "DELETE FROM favorites" in str(c.args[0])]
    assert dels and dels[0].args[1] == (5, "SA-HST-001")  # user_id=g.user_id 강제


# ── GET /api/me/history — scope=g.user_id ────────────────────────────────────

def test_history_scoped_to_user(client):
    import datetime
    ts = datetime.datetime(2026, 6, 11, 9, 0, 0)
    conn, cur = _mk_conn(fetchall=[[("SA-HST-001", "위 점막", "위", "H&E", ts)]])
    with _stack(conn, _fake_auth(uid="5", subject="HST")):
        resp = client.get("/api/me/history?user_id=999")
    assert resp.status_code == 200
    h = resp.get_json()["history"]
    assert h[0]["slide_id"] == "SA-HST-001" and h[0]["accessed_at"] == ts.isoformat()
    sel = [c for c in cur.execute.call_args_list if "FROM access_logs" in str(c.args[0])]
    assert sel and sel[0].args[1][0] == 5    # al.user_id = g.user_id (남의 기록 조회 불가)
    assert 999 not in sel[0].args[1]
