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
    # course 소속 OK(CNU/HST)지만 교수(99)≠나(5), 위임 없음(조교지만 미위임) → 403
    conn, cur = _mk_conn(fetchone=[("CNU", "HST", 99), ("조교",), None])
    with _stack(conn, _fake_auth(uid="5", subject="HST")):
        resp = client.put("/api/courses/1", json={"title": "변경"})
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "FORBIDDEN"


def test_delegated_assistant_can_edit(client):
    # 교수≠나(5)지만 course_assistants 위임 행 존재 → 편집 허용
    conn, cur = _mk_conn(fetchone=[("CNU", "HST", 99), ("조교",), (1,)])
    with _stack(conn, _fake_auth(uid="5", subject="HST")):
        resp = client.put("/api/courses/1", json={"title": "변경"})
    assert resp.status_code == 200


# ── ③ 비구독/미배포 슬라이드 배치 → 403 (게이트로 검증) ──────────────────────

def test_place_slide_blocked_by_access_gate(client):
    # _course_owner_or_assistant: professor OK → 주차 존재 → _slide_access_allowed=False → 403
    conn, cur = _mk_conn(fetchone=[("CNU", "HST", 5), ("교수",), (1,)])
    extra = [patch("server_render._slide_access_allowed", return_value=(False, None))]
    with _stack(conn, _fake_auth(uid="5", subject="HST"), extra):
        resp = client.post("/api/courses/1/weeks/2/slides", json={"slide_id": "SA-PATH-001"})
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "SLIDE_NOT_ALLOWED"


def test_place_slide_allowed_when_gate_passes(client):
    conn, cur = _mk_conn(fetchone=[("CNU", "HST", 5), ("교수",), (1,), (10,)])
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
    conn, cur = _mk_conn(fetchone=[("CNU", "HST", 99), ("조교",), (1,)])   # assistant 위임 존재
    with _stack(conn, _fake_auth(uid="5", subject="HST")):
        resp = client.delete("/api/courses/1")
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "FORBIDDEN"


# ── ⑤ 자유 수강등록 + 중복 멱등 ───────────────────────────────────────────────

def test_enroll_free_and_idempotent(client):
    # 각 POST: _course_in_scope(수업 존재) → _course_position(학생) → INSERT ON CONFLICT DO NOTHING
    conn, cur = _mk_conn(fetchone=[(1, "조직학", "2026-fall", 5), ("학생",),
                                   (1, "조직학", "2026-fall", 5), ("학생",)])
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
    # 교수(99)≠나(5), 위임 없음(지위 학생) → 403
    conn, cur = _mk_conn(fetchone=[("CNU", "HST", 99), ("학생",), None])
    with _stack(conn, _fake_auth(uid="5", subject="HST")):
        resp = client.get("/api/courses/1/roster")
    assert resp.status_code == 403


def test_roster_forbidden_other_institution(client):
    conn, cur = _mk_conn(fetchone=[("OTHER", "HST", 5)])
    with _stack(conn, _fake_auth(uid="5", inst="CNU", subject="HST")):
        resp = client.get("/api/courses/1/roster")
    assert resp.status_code == 403


def test_stats_forbidden_for_nondelegated_assistant(client):
    conn, cur = _mk_conn(fetchone=[("CNU", "HST", 99), ("조교",), None])
    with _stack(conn, _fake_auth(uid="5", subject="HST")):
        resp = client.get("/api/courses/1/stats")
    assert resp.status_code == 403


def test_roster_ok_for_professor_no_activity_fields(client):
    # 교수 본인 → 명단 반환. 활동/접속 컬럼이 응답에 없어야 함(이름·이메일·등록일만).
    conn, cur = _mk_conn(
        fetchone=[("CNU", "HST", 5), ("교수",)],
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
    conn, cur = _mk_conn(fetchone=[("CNU", "HST", 5), ("교수",), (3,), (2, 1), (4, 2)])
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
    conn, cur = _mk_conn(fetchone=[("CNU", "HST", 5), ("교수",), (0,), (0, 0), (0, 0)])
    with _stack(conn, _fake_auth(uid="5", subject="HST")):
        resp = client.get("/api/courses/1/stats")
    assert resp.status_code == 200
    assert resp.get_json()["stats"]["slide_view_rate"] == 0


# ── 조교 위임: 대상 검증 ──────────────────────────────────────────────────────

def test_assign_assistant_validates_target_position(client):
    # 교수 OK → 대상이 같은 과목 조교가 아님(None) → 400 INVALID_TARGET
    conn, cur = _mk_conn(fetchone=[("CNU", "HST", 5), ("교수",), None])
    with _stack(conn, _fake_auth(uid="5", subject="HST")):
        resp = client.post("/api/courses/1/assistants", json={"user_id": 42})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "INVALID_TARGET"


def test_assign_assistant_forbidden_for_assistant(client):
    # 위임 조교(편집 가능)라도 조교 지정은 교수만 → 403
    conn, cur = _mk_conn(fetchone=[("CNU", "HST", 99), ("조교",), (1,)])
    with _stack(conn, _fake_auth(uid="5", subject="HST")):
        resp = client.post("/api/courses/1/assistants", json={"user_id": 42})
    assert resp.status_code == 403


# ═════════════════════════════════════════════════════════════════════════════
# 외부검증 반영 수정 — 회귀 방지
#   1) 동적 position 재검증(강등 즉시 차단)  2) DELETE /enroll scope 재검증
#   3) 상세 미배포 슬라이드 필터          4) enroll position 가드
# ═════════════════════════════════════════════════════════════════════════════

# ── 수정1: 교수→학생 강등 후 소유 행 남아도 편집/삭제/주차/배치 전부 403 ──────

def test_demoted_professor_cannot_update(client):
    # professor_user_id(5)는 그대로지만 현재 position='학생'(강등) → 403
    conn, cur = _mk_conn(fetchone=[("CNU", "HST", 5), ("학생",), None])  # courses·position·assistant없음
    with _stack(conn, _fake_auth(uid="5", subject="HST")):
        resp = client.put("/api/courses/1", json={"title": "변경"})
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "FORBIDDEN"


def test_demoted_professor_cannot_delete(client):
    conn, cur = _mk_conn(fetchone=[("CNU", "HST", 5), ("학생",), None])
    with _stack(conn, _fake_auth(uid="5", subject="HST")):
        resp = client.delete("/api/courses/1")
    assert resp.status_code == 403


def test_demoted_professor_cannot_add_week(client):
    conn, cur = _mk_conn(fetchone=[("CNU", "HST", 5), ("학생",), None])
    with _stack(conn, _fake_auth(uid="5", subject="HST")):
        resp = client.post("/api/courses/1/weeks", json={"week_number": 1, "title": "1주차"})
    assert resp.status_code == 403


def test_demoted_professor_cannot_place_slide(client):
    # 강등이면 게이트(_slide_access_allowed) 도달 전에 권한에서 차단 → 403, slide gate 미호출
    conn, cur = _mk_conn(fetchone=[("CNU", "HST", 5), ("학생",), None])
    called = {"gate": False}

    def _gate(_sid):
        called["gate"] = True
        return (True, None)

    extra = [patch("server_render._slide_access_allowed", side_effect=_gate)]
    with _stack(conn, _fake_auth(uid="5", subject="HST"), extra):
        resp = client.post("/api/courses/1/weeks/2/slides", json={"slide_id": "SA-HST-001"})
    assert resp.status_code == 403
    assert called["gate"] is False   # 권한 실패가 게이트보다 먼저


def test_stripped_assistant_cannot_edit(client):
    # course_assistants 위임 행은 남아 있으나(=(1,)) 현재 position='학생'(조교 박탈) → 403
    conn, cur = _mk_conn(fetchone=[("CNU", "HST", 99), ("학생",), (1,)])
    with _stack(conn, _fake_auth(uid="5", subject="HST")):
        resp = client.put("/api/courses/1", json={"title": "변경"})
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "FORBIDDEN"


# ── 수정2: DELETE /enroll cross-scope cid 차단 ───────────────────────────────

def test_unenroll_cross_scope_blocked(client):
    conn, cur = _mk_conn(fetchone=[None])   # _course_in_scope → 없음(타기관/타과목)
    with _stack(conn, _fake_auth(role="viewer", subject="HST")):
        resp = client.delete("/api/courses/99/enroll")
    assert resp.status_code == 404
    # scope 미통과 시 DELETE 문이 실행되지 않았는지(삭제 차단)
    deletes = [c for c in cur.execute.call_args_list
               if "delete from course_enrollments" in " ".join(str(c.args[0]).split()).lower()]
    assert deletes == []


def test_unenroll_in_scope_ok(client):
    conn, cur = _mk_conn(fetchone=[(1, "조직학", "2026-fall", 5)])   # scope OK
    with _stack(conn, _fake_auth(role="viewer", subject="HST")):
        resp = client.delete("/api/courses/1/enroll")
    assert resp.status_code == 200
    deletes = [c for c in cur.execute.call_args_list
               if "delete from course_enrollments" in " ".join(str(c.args[0]).split()).lower()]
    assert len(deletes) == 1   # 해지는 position 무관 허용


# ── 수정3: 상세 응답에 미배포(qc_pending·rejected) 슬라이드 메타 미포함 ───────

DEPLOYED_ID = "SA-HST-001"
UNDEPLOYED_ID = "SA-HST-UNDEPLOYED"   # qc_pending/rejected 가정 — 응답 어디에도 등장하면 안 됨


def _slide_ids_in_payload(course):
    """course 응답 구조 전체를 순회해 등장하는 모든 slide_id 수집(구조 차원 부재 단언용)."""
    ids = []
    for wk in course.get("weeks", []):
        for sl in wk.get("slides", []):
            ids.append(sl.get("slide_id"))
    return ids


def test_detail_excludes_undeployed_slides(client):
    # ★ 보강: 미배포 슬라이드(UNDEPLOYED_ID)를 mock 에 명시적으로 포함(2주차에 배치된 것으로 가정).
    #   상세 SQL 의 ON 절(deploy_status='deployed')이 그 행을 떨궈, 2주차는 cws.*=NULL 인 '빈 주차'로
    #   DB 가 돌려준다(LEFT JOIN). 이 필터링된 결과를 mock 으로 재현하고, 최종 JSON 어디에도 미배포 ID 가
    #   없음을 raw 문자열·구조 양쪽으로 직접 부재 단언한다.
    rows = [
        # (cw.id, week_number, title, empty_reason, cws.id, slide_id, display_order, title_ko, stain)
        (10, 1, "1주차", None, 100, DEPLOYED_ID, 0, "위 점막", "H&E"),     # 배포 슬라이드(노출)
        (20, 2, "2주차", None, None, None, None, None, None),              # UNDEPLOYED_ID 배치분이 필터돼 빈 주차
    ]
    conn, cur = _mk_conn(fetchone=[(1, "조직학", "2026-fall", 5), None], fetchall=[rows])
    with _stack(conn, _fake_auth(role="viewer", subject="HST")):
        resp = client.get("/api/courses/1")
    assert resp.status_code == 200
    course = resp.get_json()["course"]
    weeks = course["weeks"]
    assert len(weeks) == 2
    wk1 = next(w for w in weeks if w["week_number"] == 1)
    wk2 = next(w for w in weeks if w["week_number"] == 2)
    assert [s["slide_id"] for s in wk1["slides"]] == [DEPLOYED_ID]
    assert wk2["slides"] == []   # 미배포 배치는 노출 안 됨(빈 주차)

    # (1) 원천 차단 기제: 상세 SQL 이 deploy_status='deployed' 필터를 포함(회귀 시 이 단언이 실패)
    sels = [" ".join(str(c.args[0]).split()).lower() for c in cur.execute.call_args_list]
    assert any("course_weeks" in s
               and "deploy_status = 'deployed'" in s
               and "select id from slides" in s for s in sels)

    # (2) 배포본 존재 확인(유지)
    raw = resp.get_data(as_text=True)
    assert DEPLOYED_ID in raw

    # (3) ★ 미배포 ID 직접 부재 단언 — raw 문자열·구조 어디에도 없음
    assert UNDEPLOYED_ID not in raw
    assert UNDEPLOYED_ID not in _slide_ids_in_payload(course)


def test_detail_relies_on_sql_filter_not_python(client):
    """★ 부재 단언이 vacuous 하지 않음을 보장하는 부정대조(negative control).

    상세 라우트는 자체 Python deploy 필터 없이 SQL ON 절 필터에 전적으로 의존한다 —
    따라서 'SQL 이 필터를 갖는다'는 단언이 load-bearing 이다. 만약 SQL 필터가 제거돼 DB 가
    미배포 행을 돌려주면(여기선 그 상황을 mock 으로 강제 주입), 라우트는 그대로 노출한다.
    이 테스트는 그 사실을 명시적으로 문서화해, 위 (1) 기제 단언이 진짜 방어선임을 못박는다.
    """
    leaked = [
        (10, 1, "1주차", None, 101, UNDEPLOYED_ID, 0, "미배포 본", "H&E"),  # 필터가 없었다면 새어나갈 행
    ]
    conn, cur = _mk_conn(fetchone=[(1, "조직학", "2026-fall", 5), None], fetchall=[leaked])
    with _stack(conn, _fake_auth(role="viewer", subject="HST")):
        resp = client.get("/api/courses/1")
    course = resp.get_json()["course"]
    # 라우트엔 Python 필터가 없으므로 DB 가 준 행을 그대로 통과 — 즉 방어는 전적으로 SQL ON 절에 있음.
    assert UNDEPLOYED_ID in _slide_ids_in_payload(course)
    # → 실제 DB 에서는 test_detail_excludes_undeployed_slides 의 (1) 필터가 이 행 자체를 막는다.


# ── 수정4: enroll position 가드(학생·조교만, 교수·행정직원 거부) ──────────────

@pytest.mark.parametrize("pos", ["학생", "조교"])
def test_enroll_allowed_for_student_and_assistant(client, pos):
    conn, cur = _mk_conn(fetchone=[(1, "조직학", "2026-fall", 5), (pos,)])
    with _stack(conn, _fake_auth(role="viewer", subject="HST")):
        resp = client.post("/api/courses/1/enroll")
    assert resp.status_code == 200
    inserts = [c for c in cur.execute.call_args_list
               if "insert into course_enrollments" in " ".join(str(c.args[0]).split()).lower()]
    assert len(inserts) == 1


@pytest.mark.parametrize("pos", ["교수", None])
def test_enroll_denied_for_professor_and_staff(client, pos):
    # 교수·행정직원(position NULL=admin-only/행정직원) → ENROLL_NOT_ALLOWED, INSERT 미실행
    conn, cur = _mk_conn(fetchone=[(1, "조직학", "2026-fall", 5), (pos,)])
    with _stack(conn, _fake_auth(role="viewer", subject="HST")):
        resp = client.post("/api/courses/1/enroll")
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "ENROLL_NOT_ALLOWED"
    inserts = [c for c in cur.execute.call_args_list
               if "insert into course_enrollments" in " ".join(str(c.args[0]).split()).lower()]
    assert inserts == []
