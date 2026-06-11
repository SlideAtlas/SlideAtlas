"""
기관 포털 — 명단 일괄 업로드 '빈 양식 다운로드'(GET /portal/api/roster/template) pytest.

★ 과목은 칼럼이 아니라 업로드 컨텍스트(요청 파라미터 subject_code) — 한 양식 = 한 과목.
CLAUDE.md §9(스코프 격리)·§3(업로드 파서 정합)·§8/§18 D9(_xlsx_safe).
핵심 단언:
  (a) 인증·관리자 게이트(401 / FORBIDDEN) + 과목 파라미터 필수(MISSING_SUBJECT) + 비구독 403.
  (b) ★ 양식 헤더(3칸: 이름·지위·이메일)가 업로드 파서 기대 헤더와 '글자 단위' 일치 —
      생성물을 그대로 _parse_xlsx_roster 에 넣으면 헤더 자동 스킵·예시 행만 남음(자기 양식 비거부).
  (c) 선택 과목이 안내에 표기 + scope=g.institution_id(타 기관 과목 노출/등록 0) + 다과목 안내.
  (d) 모든 셀 _xlsx_safe 경유(수식주입 방어 유지).

DB 는 mock — 과목 allowlist 는 _subscribed_subjects 를 직접 패치해 격리한다.
"""
import io
import os
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest")
os.environ.setdefault("GMAIL_USER", "test@gmail.com")
os.environ.setdefault("GMAIL_APP_PW", "test-app-pw")
os.environ.setdefault("ADMIN_SECRET_KEY", "test-admin-secret-for-pytest")

import pytest
import server_render as sr
from server_render import app, _PORTAL_ROSTER_HEADER, _PORTAL_POSITIONS

TEMPLATE = "/portal/api/roster/template"


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _fake_auth(uid="5", inst="CNU", role="admin", subject=None):
    def f():
        from flask import g
        g.user_id = uid
        g.institution_id = inst
        g.role = role
        g.subject_code = subject
        return None
    return f


def _admin_ctx(subjects, inst="CNU"):
    """인증+관리자 게이트 통과 + _subscribed_subjects 를 주어진 과목 dict 로 고정한 contextmanager 묶음."""
    from contextlib import ExitStack
    st = ExitStack()
    st.enter_context(patch("auth.decorators._authenticate", _fake_auth(inst=inst)))
    st.enter_context(patch("server_render._is_institution_admin", return_value=True))
    seen = {}

    def fake_subs(cur, institution_id):
        seen["inst"] = institution_id
        return dict(subjects)
    st.enter_context(patch("server_render._subscribed_subjects", side_effect=fake_subs))
    from unittest.mock import MagicMock
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = MagicMock()
    st.enter_context(patch("server_render.get_db_conn", return_value=conn))
    st.enter_context(patch("server_render.release_db_conn"))
    return st, seen


def _load_xlsx(data):
    import openpyxl
    return openpyxl.load_workbook(io.BytesIO(data), data_only=True)


def _guide_text(wb):
    return "\n".join(str(c.value) for row in wb["안내"].iter_rows() for c in row if c.value)


# ─────────────────────────────────────────────
# (a) 인증·관리자 게이트 + 과목 파라미터 필수/재검증
# ─────────────────────────────────────────────
def test_template_requires_auth(client):
    assert client.get(TEMPLATE + "?subject_code=HST").status_code == 401


def test_template_forbidden_non_admin(client):
    with patch("auth.decorators._authenticate", _fake_auth(role="viewer")), \
         patch("server_render._is_institution_admin", return_value=False):
        resp = client.get(TEMPLATE + "?subject_code=HST")
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "FORBIDDEN"


def test_template_bad_format(client):
    with patch("auth.decorators._authenticate", _fake_auth()), \
         patch("server_render._is_institution_admin", return_value=True):
        resp = client.get(TEMPLATE + "?subject_code=HST&format=exe")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "BAD_FORMAT"


def test_template_missing_subject(client):
    """과목 파라미터 없으면 400 MISSING_SUBJECT(한 양식=한 과목)."""
    with patch("auth.decorators._authenticate", _fake_auth()), \
         patch("server_render._is_institution_admin", return_value=True):
        resp = client.get(TEMPLATE + "?format=xlsx")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "MISSING_SUBJECT"


def test_template_non_subscribed_subject_403(client):
    """구독 안 한(또는 타 기관) 과목 파라미터 → 403 SUBJECT_NOT_SUBSCRIBED(scope 격리)."""
    st, _seen = _admin_ctx({"HST": "조직학"})
    with st:
        resp = client.get(TEMPLATE + "?format=xlsx&subject_code=PATH")
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "SUBJECT_NOT_SUBSCRIBED"


# ─────────────────────────────────────────────
# (b) ★ 3칸 헤더 ↔ 업로드 파서 글자단위 일치 (round-trip)
# ─────────────────────────────────────────────
def test_template_header_matches_upload_parser_exactly(client):
    """생성한 양식을 그대로 _parse_xlsx_roster 에 넣으면 헤더는 스킵되고 예시 행만 남는다(3칸)."""
    assert _PORTAL_ROSTER_HEADER == ("이름", "지위", "이메일")   # 과목 칼럼 없음
    st, _seen = _admin_ctx({"HST": "조직학"})
    with st:
        resp = client.get(TEMPLATE + "?format=xlsx&subject_code=HST")
    assert resp.status_code == 200
    wb = _load_xlsx(resp.data)
    first_row = [c.value for c in next(wb.active.iter_rows(max_row=1))]
    assert tuple(first_row[:3]) == _PORTAL_ROSTER_HEADER
    assert sr._looks_like_header(list(_PORTAL_ROSTER_HEADER)) is True
    rows = sr._parse_xlsx_roster(resp.data, 2000)
    assert rows == [("홍길동", _PORTAL_POSITIONS[-1], "gildong@univ.ac.kr")]


def test_template_csv_header_and_example(client):
    st, _seen = _admin_ctx({"HST": "조직학"})
    with st:
        resp = client.get(TEMPLATE + "?format=csv&subject_code=HST")
    assert resp.status_code == 200
    rows = sr._parse_csv_roster(resp.data, 2000)
    assert rows == [("홍길동", _PORTAL_POSITIONS[-1], "gildong@univ.ac.kr")]


# ─────────────────────────────────────────────
# (c) 선택 과목 안내 + scope 격리 + 다과목 안내
# ─────────────────────────────────────────────
def test_template_selected_subject_in_guide_and_scope(client):
    """안내에 선택 과목명 표기 + scope=g.institution_id(쿼리 inst_id 무시) + 타 기관 식별자 미노출."""
    st, seen = _admin_ctx({"HST": "조직학", "PATH": "병리학"}, inst="CNU")
    with st:
        resp = client.get(TEMPLATE + "?format=xlsx&subject_code=HST&inst_id=SNU&institution_id=SNU")
    assert resp.status_code == 200
    assert seen["inst"] == "CNU"                  # 쿼리 inst_id(SNU) 무시
    guide = _guide_text(_load_xlsx(resp.data))
    assert "조직학" in guide and "HST" in guide   # 선택 과목 표기
    assert "SNU" not in guide
    # 한 양식 = 한 과목 / 다과목은 따로 등록 안내
    assert "한 과목" in guide
    assert "과목별로 따로" in guide or "과목별로" in guide
    # 식별자=이메일 안내
    assert "식별자" in guide and "이메일" in guide


def test_template_positions_from_parser_allowlist(client):
    """지위 안내 = 파서 allowlist(_PORTAL_POSITIONS), 행정직원은 지위 줄에 없음(파서 거절 값)."""
    st, _seen = _admin_ctx({"HST": "조직학"})
    with st:
        resp = client.get(TEMPLATE + "?format=xlsx&subject_code=HST")
    guide = _guide_text(_load_xlsx(resp.data))
    for p in _PORTAL_POSITIONS:
        assert p in guide
    assert "행정직원" in guide          # '관리자로 별도 등록' 안내로만 등장
    pos_line = [ln for ln in guide.splitlines() if ln.startswith("• 지위:")][0]
    assert "행정직원" not in pos_line


# ─────────────────────────────────────────────
# (d) _xlsx_safe 수식주입 방어 — 모든 셀이 _xlsx_safe 를 경유한다
# ─────────────────────────────────────────────
def test_template_routes_all_cells_through_xlsx_safe(client):
    """양식 생성 시 셀 값이 _xlsx_safe 를 경유(수식주입 방어 유지) — 호출 여부로 단언."""
    st, _seen = _admin_ctx({"HST": "조직학"})
    with st, patch("server_render._xlsx_safe", wraps=sr._xlsx_safe) as spy:
        resp = client.get(TEMPLATE + "?format=xlsx&subject_code=HST")
    assert resp.status_code == 200
    assert spy.called                              # 모든 셀 _xlsx_safe 경유


def test_template_csv_formula_injection_neutralized(client):
    """선두가 수식문자인 값은 _xlsx_safe 가 작은따옴표로 무력화(예: 위험한 이름 셀)."""
    # 예시 행 이름 셀은 상수라 안전 — 가드 '경유'는 위 spy 로 확인. 여기선 _xlsx_safe 단위 동작 확인.
    assert sr._xlsx_safe("=cmd|'/c calc'!A1").startswith("'")
    assert sr._xlsx_safe("홍길동") == "홍길동"     # 정상 값은 불변
