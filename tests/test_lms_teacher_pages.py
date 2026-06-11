"""
LMS 교수/조교 프론트 라우트(3단계-A) pytest — 페이지 권한 가드 + 신규 표시용 GET API 가드.

불변 원칙(어기면 reject):
 · 프론트 라우트는 새 권한 판정 로직을 만들지 않는다 — position(_course_position)·
   편집권(_course_owner_or_assistant) 기존 헬퍼만 재사용한다.
 · 학생/타 기관·과목/미위임 조교는 /teacher/* 접근 시 redirect(/home) 또는 403.
 · 신규 GET API(available-slides·assistants·assistant-candidates)는 모두 편집권 게이트 통과자만.

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


def _fake_auth(uid="5", inst="CNU", role="viewer", subject="HST"):
    def f():
        from flask import g
        g.user_id = uid
        g.institution_id = inst
        g.role = role
        g.subject_code = subject
        g.is_special = False
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


# ── /teacher/courses : position∈{교수,조교}만 ────────────────────────────────

def test_courses_page_requires_auth(client):
    """비로그인 → page_login_required 가 랜딩(/)으로 redirect."""
    from urllib.parse import urlparse
    resp = client.get("/teacher/courses")
    assert resp.status_code == 302
    # [외부검증 수정3] endswith("") 는 항상 참(무력) → 리다이렉트 경로가 정확히 '/'(랜딩)인지 실질 단언.
    assert urlparse(resp.headers["Location"]).path == "/"


def test_student_redirected_from_courses_page(client):
    """학생(position=학생) → /home 으로 redirect(교수/조교 아님)."""
    conn, _ = _mk_conn(fetchone=[("학생",)])
    with _stack(conn, _fake_auth(role="viewer", subject="HST")):
        resp = client.get("/teacher/courses")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/home")


def test_professor_sees_courses_page(client):
    conn, _ = _mk_conn(fetchone=[("교수",)])
    with _stack(conn, _fake_auth(role="viewer", subject="HST")):
        resp = client.get("/teacher/courses")
    assert resp.status_code == 200
    assert "내 수업 관리" in resp.get_data(as_text=True)


def test_assistant_sees_courses_page(client):
    conn, _ = _mk_conn(fetchone=[("조교",)])
    with _stack(conn, _fake_auth(role="viewer", subject="HST")):
        resp = client.get("/teacher/courses")
    assert resp.status_code == 200


# ── /teacher/course/<cid> : 편집권자(교수·위임조교)만 ────────────────────────

def test_non_editor_403_on_edit_page(client):
    """학생(소유 아님·위임 없음) → 403 페이지."""
    # _course_owner_or_assistant: course(CNU/HST/prof=99) → position 학생 → assistants None
    conn, _ = _mk_conn(fetchone=[("CNU", "HST", 99), ("학생",), None])
    with _stack(conn, _fake_auth(uid="5", subject="HST")):
        resp = client.get("/teacher/course/1")
    assert resp.status_code == 403
    assert "접근 권한이 없습니다" in resp.get_data(as_text=True)


def test_other_institution_course_403(client):
    """타 기관 수업(scope 불일치) → 403(존재 숨김)."""
    conn, _ = _mk_conn(fetchone=[("SNU", "HST", 5)])   # course inst=SNU ≠ g.inst=CNU
    with _stack(conn, _fake_auth(uid="5", inst="CNU", subject="HST")):
        resp = client.get("/teacher/course/1")
    assert resp.status_code == 403


def test_owner_professor_sees_edit_page(client):
    conn, _ = _mk_conn(fetchone=[("CNU", "HST", 5), ("교수",)])
    with _stack(conn, _fake_auth(uid="5", inst="CNU", subject="HST")):
        resp = client.get("/teacher/course/1")
    assert resp.status_code == 200
    assert "주차 구성" in resp.get_data(as_text=True)


def test_delegated_assistant_sees_edit_page(client):
    # 교수=99≠나(5), 위임행 존재, position 조교 → assistant 편집권
    conn, _ = _mk_conn(fetchone=[("CNU", "HST", 99), ("조교",), (1,)])
    with _stack(conn, _fake_auth(uid="5", inst="CNU", subject="HST")):
        resp = client.get("/teacher/course/1")
    assert resp.status_code == 200


# ── /teacher/course/<cid>/assistants : 교수만 ────────────────────────────────

def test_delegated_assistant_cannot_open_assistants_page(client):
    """위임 조교는 편집권은 있으나 조교 지정 화면은 교수 전용 → 403."""
    conn, _ = _mk_conn(fetchone=[("CNU", "HST", 99), ("조교",), (1,)])
    with _stack(conn, _fake_auth(uid="5", inst="CNU", subject="HST")):
        resp = client.get("/teacher/course/1/assistants")
    assert resp.status_code == 403


def test_professor_opens_assistants_page(client):
    conn, _ = _mk_conn(fetchone=[("CNU", "HST", 5), ("교수",)])
    with _stack(conn, _fake_auth(uid="5", inst="CNU", subject="HST")):
        resp = client.get("/teacher/course/1/assistants")
    assert resp.status_code == 200
    assert "조교 추가" in resp.get_data(as_text=True)


# ── /teacher/course/<cid>/dashboard : 편집권자 ───────────────────────────────

def test_non_editor_403_on_dashboard_page(client):
    conn, _ = _mk_conn(fetchone=[("CNU", "HST", 99), ("학생",), None])
    with _stack(conn, _fake_auth(uid="5", inst="CNU", subject="HST")):
        resp = client.get("/teacher/course/1/dashboard")
    assert resp.status_code == 403


def test_assistant_sees_dashboard_page(client):
    conn, _ = _mk_conn(fetchone=[("CNU", "HST", 99), ("조교",), (1,)])
    with _stack(conn, _fake_auth(uid="5", inst="CNU", subject="HST")):
        resp = client.get("/teacher/course/1/dashboard")
    assert resp.status_code == 200
    assert "익명 집계" in resp.get_data(as_text=True)


# ── 신규 표시용 GET API 가드 ─────────────────────────────────────────────────

def test_available_slides_blocks_non_editor(client):
    """비편집자 → _course_owner_or_assistant 가 403."""
    conn, _ = _mk_conn(fetchone=[("CNU", "HST", 99), ("학생",), None])
    with _stack(conn, _fake_auth(uid="5", inst="CNU", subject="HST")):
        resp = client.get("/api/courses/1/available-slides")
    assert resp.status_code == 403


def _mixed_slides():
    """배포/미배포·과목 혼합 카탈로그(load_slides 형태)."""
    return {"slides": [
        {"id": "SA-HST-001", "title_ko": "단층 편평상피", "system": "소화기", "stain": "H&E",
         "subject_code": "HST", "deploy_status": "deployed", "conversion_status": "ready"},
        {"id": "SA-HST-PENDING", "title_ko": "검수 대기본", "system": "소화기", "stain": "H&E",
         "subject_code": "HST", "deploy_status": "qc_pending", "conversion_status": "ready"},
        {"id": "SA-PATH-001", "title_ko": "간경변", "system": "간담췌", "stain": "H&E",
         "subject_code": "PATH", "deploy_status": "deployed", "conversion_status": "ready"},
    ]}


def test_available_slides_excludes_undeployed(client):
    """[외부검증 수정3] _visible_slides 를 통째로 mock 하지 않고 load_slides 만 mock + 미배포 섞어,
    결과에서 미배포(qc_pending)·타 과목이 실제로 빠지는지 직접 단언(vacuous 방지)."""
    conn, _ = _mk_conn(fetchone=[("CNU", "HST", 5), ("교수",)])
    extra = [
        patch("server_render.load_slides", return_value=_mixed_slides()),
        patch("server_render._institution_subject_access", return_value=True),
    ]
    with _stack(conn, _fake_auth(uid="5", inst="CNU", subject="HST"), extra=extra):
        resp = client.get("/api/courses/1/available-slides")
    assert resp.status_code == 200
    ids = [s["id"] for s in resp.get_json()["slides"]]
    assert ids == ["SA-HST-001"]              # 배포·HST 만
    assert "SA-HST-PENDING" not in ids        # 미배포 제외
    assert "SA-PATH-001" not in ids           # 타 과목 제외
    # 타일/토큰 필드가 새지 않는다(카탈로그 메타만).
    assert set(resp.get_json()["slides"][0].keys()) == {"id", "title_ko", "organ", "stain"}


def test_available_slides_subject_filter_for_special_editor(client):
    """[외부검증 수정1] is_special 편집자는 _visible_slides 가 타 과목까지 반환하지만, 후보 목록은
    이 수업 과목(HST)으로 제한돼 PATH 슬라이드가 노출되지 않는다(배치 가드와 같은 과목 집합)."""
    def _auth_special():
        from flask import g
        g.user_id = "5"; g.institution_id = "CNU"; g.role = "viewer"
        g.subject_code = "HST"; g.is_special = True
        return None
    conn, _ = _mk_conn(fetchone=[("CNU", "HST", 5), ("교수",)])
    extra = [patch("server_render.load_slides", return_value=_mixed_slides())]
    with _stack(conn, _auth_special, extra=extra):
        resp = client.get("/api/courses/1/available-slides")
    assert resp.status_code == 200
    ids = [s["id"] for s in resp.get_json()["slides"]]
    assert "SA-PATH-001" not in ids           # 특별계정도 타 과목 후보 비노출
    assert "SA-HST-001" in ids


def test_assistant_candidates_professor_only(client):
    """위임 조교(편집권 O)라도 조교 검색은 교수 전용 → 403."""
    conn, _ = _mk_conn(fetchone=[("CNU", "HST", 99), ("조교",), (1,)])
    with _stack(conn, _fake_auth(uid="5", inst="CNU", subject="HST")):
        resp = client.get("/api/courses/1/assistant-candidates?q=조")
    assert resp.status_code == 403


def test_assistant_candidates_scope_is_g_only(client):
    """교수 → 후보 검색 scope 는 g.institution_id·g.subject_code 강제(IDOR 차단)."""
    conn, cur = _mk_conn(
        fetchone=[("CNU", "HST", 5), ("교수",)],
        fetchall=[[(9, "조민수", "minsu@test.ac.kr")]],
    )
    with _stack(conn, _fake_auth(uid="5", inst="CNU", subject="HST")):
        resp = client.get("/api/courses/1/assistant-candidates?q=조")
    assert resp.status_code == 200
    assert resp.get_json()["candidates"][0]["user_id"] == 9
    # 후보 SELECT 파라미터 1·2 가 g.institution_id·g.subject_code 인지(body/쿼리 미참조)
    sel = [c for c in cur.execute.call_args_list
           if "u.position = '조교'" in " ".join(str(c.args[0]).split())]
    assert sel and sel[0].args[1][0] == "CNU" and sel[0].args[1][1] == "HST"


def test_assistant_candidates_excludes_non_active(client):
    """[외부검증 수정2] 후보 SQL 에 u.status='active' 조건이 있어 locked/pending 계정은 후보에서 빠진다.
    (DB mock 은 활성 행만 반환하지만, 필터 자체가 SQL 에 박혀 있음을 직접 단언 — vacuous 방지.)"""
    conn, cur = _mk_conn(
        fetchone=[("CNU", "HST", 5), ("교수",)],
        fetchall=[[(9, "조민수", "minsu@test.ac.kr")]],   # active 만 반환됐다고 가정
    )
    with _stack(conn, _fake_auth(uid="5", inst="CNU", subject="HST")):
        resp = client.get("/api/courses/1/assistant-candidates?q=조")
    assert resp.status_code == 200
    sel = [c for c in cur.execute.call_args_list
           if "u.position = '조교'" in " ".join(str(c.args[0]).split())]
    sql = " ".join(str(sel[0].args[0]).split())
    assert "u.status = 'active'" in sql        # locked/pending 비노출 조건 존재


def test_assistants_list_blocks_non_editor(client):
    conn, _ = _mk_conn(fetchone=[("CNU", "HST", 99), ("학생",), None])
    with _stack(conn, _fake_auth(uid="5", inst="CNU", subject="HST")):
        resp = client.get("/api/courses/1/assistants")
    assert resp.status_code == 403


def test_assistants_list_returns_names(client):
    conn, _ = _mk_conn(
        fetchone=[("CNU", "HST", 5), ("교수",)],
        fetchall=[[(7, "박지훈", "jihoon@test.ac.kr")]],
    )
    with _stack(conn, _fake_auth(uid="5", inst="CNU", subject="HST")):
        resp = client.get("/api/courses/1/assistants")
    assert resp.status_code == 200
    a = resp.get_json()["assistants"][0]
    assert a["user_id"] == 7 and a["name"] == "박지훈"


# ── [Codex Med] /api/courses/mine : position DB 권위 재검증(강등/박탈 즉시 반영, fail-closed) ──

def _mine_sqls(cur):
    return [" ".join(str(c.args[0]).split()) for c in cur.execute.call_args_list]


def test_mine_professor_sees_only_owned(client):
    """position '교수' → 소유 수업만(professor_user_id), course_assistants 분기 미사용."""
    conn, cur = _mk_conn(
        fetchone=[("교수",)],                                   # _course_position
        fetchall=[[(1, "조직학 A반", "2026-fall", True, 3)]],   # 소유 수업
    )
    with _stack(conn, _fake_auth(uid="5", inst="CNU", subject="HST")):
        resp = client.get("/api/courses/mine")
    assert resp.status_code == 200
    cs = resp.get_json()["courses"]
    assert len(cs) == 1 and cs[0]["role"] == "professor"
    listsql = [s for s in _mine_sqls(cur) if "FROM courses" in s][0]
    assert "c.professor_user_id = %s" in listsql
    assert "course_assistants" not in listsql       # 교수 분기엔 위임 EXISTS 없음


def test_mine_assistant_sees_only_delegated(client):
    """position '조교' → 위임 수업만(course_assistants EXISTS)."""
    conn, cur = _mk_conn(
        fetchone=[("조교",)],
        fetchall=[[(2, "병리 실습", "2026-fall", False, 5)]],
    )
    with _stack(conn, _fake_auth(uid="9", inst="CNU", subject="HST")):
        resp = client.get("/api/courses/mine")
    assert resp.status_code == 200
    cs = resp.get_json()["courses"]
    assert len(cs) == 1 and cs[0]["role"] == "assistant"
    listsql = [s for s in _mine_sqls(cur) if "FROM courses" in s][0]
    assert "course_assistants" in listsql


def test_mine_demoted_professor_empty_fail_closed(client):
    """교수 강등(position→'학생', professor_user_id 잔존) → 빈 목록(stale 메타 미노출)."""
    conn, cur = _mk_conn(fetchone=[("학생",)])      # 강등됨
    with _stack(conn, _fake_auth(uid="5", inst="CNU", subject="HST")):
        resp = client.get("/api/courses/mine")
    assert resp.status_code == 200
    assert resp.get_json()["courses"] == []          # 소유 수업 안 보임
    assert not any("FROM courses" in s for s in _mine_sqls(cur))   # 목록 쿼리 미실행


def test_mine_none_position_empty_fail_closed(client):
    """지위 박탈(position None) → fail-closed 빈 목록."""
    conn, cur = _mk_conn(fetchone=[(None,)])
    with _stack(conn, _fake_auth(uid="9", inst="CNU", subject="HST")):
        resp = client.get("/api/courses/mine")
    assert resp.status_code == 200
    assert resp.get_json()["courses"] == []
    assert not any("FROM courses" in s for s in _mine_sqls(cur))


def test_mine_revalidates_position_each_request(client):
    """같은 user라도 position을 매 요청 DB 재조회 — 강등 즉시 반영(교수→학생 사이 목록 사라짐)."""
    # 1차: 교수 → 소유 수업 보임
    conn1, _ = _mk_conn(fetchone=[("교수",)], fetchall=[[(1, "A", "2026-fall", True, 0)]])
    with _stack(conn1, _fake_auth(uid="5", inst="CNU", subject="HST")):
        r1 = client.get("/api/courses/mine")
    assert len(r1.get_json()["courses"]) == 1
    # 2차: 같은 user 강등 → 빈 목록
    conn2, _ = _mk_conn(fetchone=[("학생",)])
    with _stack(conn2, _fake_auth(uid="5", inst="CNU", subject="HST")):
        r2 = client.get("/api/courses/mine")
    assert r2.get_json()["courses"] == []
