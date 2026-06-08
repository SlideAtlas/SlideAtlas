"""
LMS(교수 수업 페이지) 2단계 백엔드 pytest — §21 / §8 단일 게이트 불변 / §15-7 개인정보.

검증 항목(지시 ①~⑧):
 ① 학생이 수업 개설 시도 → 403 (position 기반 권한, role 무관)
 ② 조교가 위임 없이 편집 → 403 (course_assistants 행 없음)
 ③ 비구독/미배포 슬라이드 배치 → 403 (_slide_access_allowed 게이트로 검증, 수업≠게이트)
 ④ 타 기관/타 과목 course_id IDOR → 403 (scope=g.institution_id·g.subject_code 강제)
 ⑤ 자유 수강등록 + 중복등록 멱등(ON CONFLICT DO NOTHING)
 ⑥ 미등록 학생도 GET /api/courses/<cid> 상세 조회 가능(수업=게이트 아님 §21-6)
 ⑦ roster·stats 를 학생/타기관/미위임 조교가 호출 → 403
 ⑧ /stats 응답에 학생 개별 식별자(user_id·email·이름)·학생별 행 없음(익명 집계만 §15-7)

DB 는 mock(로컬 RDS 접속 불가). 라우트 실행 경로의 cursor fetch 시퀀스를 정확히 모킹한다.
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
    """공통 패치: 인증(g 적재)·CSRF 통과·DB conn 모킹."""
    auth = auth or _fake_auth()
    st = ExitStack()
    st.enter_context(patch("auth.decorators._authenticate", auth))
    st.enter_context(patch("auth.decorators._csrf_ok", lambda: True))
    st.enter_context(patch("server_render.get_db_conn", return_value=conn))
    st.enter_context(patch("server_render.release_db_conn"))
    for p in (extra or []):
        st.enter_context(p)
    return st


# ── 인증 게이트(기본) ─────────────────────────────────────────────────────────

def test_create_requires_auth(client):
    """비로그인 POST /api/courses → 401(login_required)."""
    resp = client.post("/api/courses", json={"title": "x"})
    assert resp.status_code == 401


# ── ① 학생 개설 시도 → 403 (position 기반) ────────────────────────────────────

def test_student_cannot_create_course(client):
    conn, cur = _mk_conn(fetchone=[("학생",)])   # _course_position → 학생
    with _stack(conn, _fake_auth(role="viewer", subject="HST")):
        resp = client.post("/api/courses", json={"title": "조직학 실습"})
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "FORBIDDEN"


def test_professor_can_create_course(client):
    conn, cur = _mk_conn(fetchone=[("교수",), (7,)])   # position 교수 → INSERT RETURNING id
    with _stack(conn, _fake_auth(role="viewer", subject="HST")):
        resp = client.post("/api/courses", json={"title": "조직학 실습", "semester": "2026-fall"})
    assert resp.status_code == 200
    assert resp.get_json()["course_id"] == 7
    # subject_code·professor_user_id 는 g 에서만 — INSERT 파라미터에 g 값이 들어갔는지
    ins = [c for c in cur.execute.call_args_list if "insert into courses" in " ".join(str(c.args[0]).split()).lower()]
    assert ins and ins[0].args[1][0] == "CNU" and ins[0].args[1][2] == "5"


# ── ② 위임 없는 조교 편집 → 403 ───────────────────────────────────────────────

def test_assistant_without_delegation_cannot_edit(client):
    # course 소속 OK(CNU/HST)지만 교수(99)≠나(5), course_assistants 없음 → 403
    conn, cur = _mk_conn(fetchone=[("CNU", "HST", 99), None])
    with _stack(conn, _fake_auth(uid="5", subject="HST")):
        resp = client.put("/api/courses/1", json={"title": "변경"})
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "FORBIDDEN"


def test_delegated_assistant_can_edit(client):
    # 교수≠나(5)지만 course_assistants 위임 행 존재 → 편집 허용
    conn, cur = _mk_conn(fetchone=[("CNU", "HST", 99), (1,)])
    with _stack(conn, _fake_auth(uid="5", subject="HST")):
        resp = client.put("/api/courses/1", json={"title": "변경"})
    assert resp.status_code == 200


# ── ③ 비구독/미배포 슬라이드 배치 → 403 (게이트로 검증) ──────────────────────

def test_place_slide_blocked_by_access_gate(client):
    # _course_owner_or_assistant: professor OK → 주차 존재 → _slide_access_allowed=False → 403
    conn, cur = _mk_conn(fetchone=[("CNU", "HST", 5), (1,)])
    extra = [patch("server_render._slide_access_allowed", return_value=(False, None))]
    with _stack(conn, _fake_auth(uid="5", subject="HST"), extra):
        resp = client.post("/api/courses/1/weeks/2/slides", json={"slide_id": "SA-PATH-001"})
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "SLIDE_NOT_ALLOWED"


def test_place_slide_allowed_when_gate_passes(client):
    conn, cur = _mk_conn(fetchone=[("CNU", "HST", 5), (1,), (10,)])
    extra = [patch("server_render._slide_access_allowed", return_value=(True, None))]
    with _stack(conn, _fake_auth(uid="5", subject="HST"), extra):
        resp = client.post("/api/courses/1/weeks/2/slides",
                           json={"slide_id": "SA-HST-001", "display_order": 1})
    assert resp.status_code == 200
    assert resp.get_json()["id"] == 10


# ── ④ 타 기관/타 과목 course IDOR → 403 ───────────────────────────────────────

def test_other_institution_course_idor(client):
    conn, cur = _mk_conn(fetchone=[("OTHER", "HST", 5)])   # course 는 OTHER 기관
    with _stack(conn, _fake_auth(uid="5", inst="CNU", subject="HST")):
        resp = client.put("/api/courses/1", json={"title": "탈취시도"})
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "FORBIDDEN"   # NOT_FOUND 아님 — 존재 은닉


def test_other_subject_course_idor(client):
    conn, cur = _mk_conn(fetchone=[("CNU", "PATH", 5)])   # 같은 기관, 다른 과목
    with _stack(conn, _fake_auth(uid="5", inst="CNU", subject="HST")):
        resp = client.delete("/api/courses/1")
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "FORBIDDEN"


def test_delete_course_assistant_forbidden(client):
    # 위임 조교(편집은 가능)라도 수업 삭제는 교수만 → 403
    conn, cur = _mk_conn(fetchone=[("CNU", "HST", 99), (1,)])   # assistant 위임 존재
    with _stack(conn, _fake_auth(uid="5", subject="HST")):
        resp = client.delete("/api/courses/1")
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "FORBIDDEN"


# ── ⑤ 자유 수강등록 + 중복 멱등 ───────────────────────────────────────────────

def test_enroll_free_and_idempotent(client):
    # _course_in_scope → 수업 존재(2회분), INSERT ON CONFLICT DO NOTHING
    conn, cur = _mk_conn(fetchone=[(1, "조직학", "2026-fall", 5),
                                   (1, "조직학", "2026-fall", 5)])
    with _stack(conn, _fake_auth(role="viewer", subject="HST")):
        r1 = client.post("/api/courses/1/enroll")
        r2 = client.post("/api/courses/1/enroll")   # 중복 — 멱등
    assert r1.status_code == 200 and r2.status_code == 200
    # INSERT 에 ON CONFLICT DO NOTHING 포함(멱등 보장)
    inserts = [" ".join(str(c.args[0]).split()).lower()
               for c in cur.execute.call_args_list
               if "insert into course_enrollments" in " ".join(str(c.args[0]).split()).lower()]
    assert inserts and "on conflict" in inserts[0] and "do nothing" in inserts[0]


def test_enroll_other_scope_404(client):
    conn, cur = _mk_conn(fetchone=[None])   # _course_in_scope → 없음(타기관/타과목)
    with _stack(conn, _fake_auth(role="viewer", subject="HST")):
        resp = client.post("/api/courses/99/enroll")
    assert resp.status_code == 404


# ── ⑥ 미등록 학생도 상세 조회 가능(수업=게이트 아님) ─────────────────────────

def test_unenrolled_student_can_view_detail(client):
    # course 존재 → 미등록(None) → weeks 없음([])
    conn, cur = _mk_conn(fetchone=[(1, "조직학", "2026-fall", 5), None],
                         fetchall=[[]])
    with _stack(conn, _fake_auth(role="viewer", subject="HST")):
        resp = client.get("/api/courses/1")
    assert resp.status_code == 200
    data = resp.get_json()["course"]
    assert data["enrolled"] is False     # 미등록이어도 열람 가능
    assert data["weeks"] == []


def test_detail_other_scope_404(client):
    conn, cur = _mk_conn(fetchone=[None])   # _course_in_scope → 없음
    with _stack(conn, _fake_auth(role="viewer", subject="HST")):
        resp = client.get("/api/courses/77")
    assert resp.status_code == 404


# ── ⑦ roster/stats 권한 — 학생·타기관·미위임 조교 → 403 ──────────────────────

def test_roster_forbidden_for_student(client):
    # 교수(99)≠나(5), 위임 없음 → 403
    conn, cur = _mk_conn(fetchone=[("CNU", "HST", 99), None])
    with _stack(conn, _fake_auth(uid="5", subject="HST")):
        resp = client.get("/api/courses/1/roster")
    assert resp.status_code == 403


def test_roster_forbidden_other_institution(client):
    conn, cur = _mk_conn(fetchone=[("OTHER", "HST", 5)])
    with _stack(conn, _fake_auth(uid="5", inst="CNU", subject="HST")):
        resp = client.get("/api/courses/1/roster")
    assert resp.status_code == 403


def test_stats_forbidden_for_nondelegated_assistant(client):
    conn, cur = _mk_conn(fetchone=[("CNU", "HST", 99), None])
    with _stack(conn, _fake_auth(uid="5", subject="HST")):
        resp = client.get("/api/courses/1/stats")
    assert resp.status_code == 403


def test_roster_ok_for_professor_no_activity_fields(client):
    # 교수 본인 → 명단 반환. 활동/접속 컬럼이 응답에 없어야 함(이름·이메일·등록일만).
    conn, cur = _mk_conn(
        fetchone=[("CNU", "HST", 5)],
        fetchall=[[("김민준", "mj@cnu.ac.kr", None), ("이서연", "sy@cnu.ac.kr", None)]],
    )
    with _stack(conn, _fake_auth(uid="5", subject="HST")):
        resp = client.get("/api/courses/1/roster")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["count"] == 2
    for s in data["students"]:
        assert set(s.keys()) == {"name", "email", "enrolled_at"}   # 활동/접속 데이터 없음


# ── ⑧ stats 익명 집계만 — 개별 식별자/학생별 행 없음 ─────────────────────────

def test_stats_anonymous_aggregate_only(client):
    # 교수 OK → enrolled=3 → (active=2,inactive=1) → (placed=4,viewed=2)
    conn, cur = _mk_conn(fetchone=[("CNU", "HST", 5), (3,), (2, 1), (4, 2)])
    with _stack(conn, _fake_auth(uid="5", subject="HST")):
        resp = client.get("/api/courses/1/stats")
    assert resp.status_code == 200
    body = resp.get_json()
    stats = body["stats"]
    # 익명 집계 숫자만
    assert stats["enrolled_count"] == 3
    assert stats["active_recent_count"] == 2
    assert stats["inactive_count"] == 1
    assert stats["slide_view_rate"] == 50   # viewed2/placed4
    # ★ 개인 식별자·학생별 행 부재 단언(§15-7)
    assert all(isinstance(v, int) for v in stats.values())   # 전부 정수 집계
    raw = resp.get_data(as_text=True).lower()
    assert "email" not in raw
    assert "user_id" not in raw
    assert "students" not in body          # 학생별 행 컨테이너 자체가 없음
    assert "name" not in raw


def test_stats_zero_guard(client):
    # 등록 0·배치 0 → 0나눗셈 가드(slide_view_rate=0)
    conn, cur = _mk_conn(fetchone=[("CNU", "HST", 5), (0,), (0, 0), (0, 0)])
    with _stack(conn, _fake_auth(uid="5", subject="HST")):
        resp = client.get("/api/courses/1/stats")
    assert resp.status_code == 200
    assert resp.get_json()["stats"]["slide_view_rate"] == 0


# ── 조교 위임: 대상 검증 ──────────────────────────────────────────────────────

def test_assign_assistant_validates_target_position(client):
    # 교수 OK → 대상이 같은 과목 조교가 아님(None) → 400 INVALID_TARGET
    conn, cur = _mk_conn(fetchone=[("CNU", "HST", 5), None])
    with _stack(conn, _fake_auth(uid="5", subject="HST")):
        resp = client.post("/api/courses/1/assistants", json={"user_id": 42})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "INVALID_TARGET"


def test_assign_assistant_forbidden_for_assistant(client):
    # 위임 조교(편집 가능)라도 조교 지정은 교수만 → 403
    conn, cur = _mk_conn(fetchone=[("CNU", "HST", 99), (1,)])
    with _stack(conn, _fake_auth(uid="5", subject="HST")):
        resp = client.post("/api/courses/1/assistants", json={"user_id": 42})
    assert resp.status_code == 403
