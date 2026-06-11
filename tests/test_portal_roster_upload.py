"""
기관 포털 P1 — 명단 일괄 업로드(POST /portal/api/roster/upload) 과목=업로드 컨텍스트 전환 pytest.

★ 과목은 엑셀 칼럼이 아니라 요청 파라미터(form-data subject_code) — '한 업로드 = 한 과목'.
CLAUDE.md §0(데이터 모델: subject_code 여전히 과목별 채움)·§9(scope 격리: 서버 재검증)·§3(skip-and-report).
핵심 단언:
  1. 과목 파라미터를 모든 행에 일괄 적용 → _sync_member 가 그 subject_code 로 호출(누락=NULL 0건).
  2. 서버 재검증 — 비구독/타 기관 과목 파라미터면 행 처리 전 403(SUBJECT_NOT_SUBSCRIBED).
  3. 3칸(이름·지위·이메일) 파싱 — 과목 칼럼 없음. 지위 allowlist(행정직원 거절).
  4. 과목 파라미터 누락 → 400(MISSING_SUBJECT).

DB 는 mock. _sync_member·_subscribed_subjects 를 패치해 호출 인자/분기만 검증한다.
"""
import io
import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest")
os.environ.setdefault("GMAIL_USER", "test@gmail.com")
os.environ.setdefault("GMAIL_APP_PW", "test-app-pw")
os.environ.setdefault("ADMIN_SECRET_KEY", "test-admin-secret-for-pytest")

import pytest
import server_render as sr
from server_render import app

UPLOAD = "/portal/api/roster/upload"


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


def _xlsx_bytes(rows, header=("이름", "지위", "이메일")):
    """3칸 엑셀 bytes 생성(헤더 + 데이터 행)."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(list(header))
    for r in rows:
        ws.append(list(r))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _ctx(subjects, sync_outcome="added_no_user"):
    """인증+관리자 게이트 + _subscribed_subjects 고정 + _sync_member 스파이 + DB mock."""
    from contextlib import ExitStack
    st = ExitStack()
    st.enter_context(patch("auth.decorators._authenticate", _fake_auth()))
    st.enter_context(patch("auth.decorators._csrf_ok", lambda: True))
    st.enter_context(patch("server_render._is_institution_admin", return_value=True))
    st.enter_context(patch("server_render._subscribed_subjects", side_effect=lambda cur, inst: dict(subjects)))
    sync = st.enter_context(patch("server_render._sync_member", return_value=sync_outcome))
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = MagicMock()
    st.enter_context(patch("server_render.get_db_conn", return_value=conn))
    st.enter_context(patch("server_render.release_db_conn"))
    return st, sync


def _post(client, data, subject_code=None, fname="roster.xlsx"):
    payload = {"file": (io.BytesIO(data), fname)}
    if subject_code is not None:
        payload["subject_code"] = subject_code
    return client.post(UPLOAD, data=payload, content_type="multipart/form-data")


# ─────────────────────────────────────────────
# 1. 과목 파라미터 일괄 적용 — 모든 행 _sync_member(subject_code=선택과목)
# ─────────────────────────────────────────────
def test_upload_applies_subject_param_to_all_rows(client):
    data = _xlsx_bytes([("김", "학생", "a@c.ac"), ("이", "조교", "b@c.ac")])
    st, sync = _ctx({"HST": "조직학"})
    with st:
        resp = _post(client, data, subject_code="HST")
    assert resp.status_code == 200
    j = resp.get_json()
    assert j["success"] is True and j["subject_code"] == "HST"
    # 두 행 모두 _sync_member(inst, 'HST', email, name, position, ...) 로 호출 — 과목 일괄 적용
    assert sync.call_count == 2
    for c in sync.call_args_list:
        # _sync_member(cur, institution_id, subject_code, email, name, position, today, seat_cache)
        assert c.args[1] == "CNU" and c.args[2] == "HST"   # §0: subject_code 정확히 채움(누락 없음)
    emails = sorted(c.args[3] for c in sync.call_args_list)
    assert emails == ["a@c.ac", "b@c.ac"]


# ─────────────────────────────────────────────
# 2. 서버 재검증 — 비구독 과목 파라미터 → 403, 행 처리 안 함
# ─────────────────────────────────────────────
def test_upload_non_subscribed_subject_403_no_rows(client):
    data = _xlsx_bytes([("김", "학생", "a@c.ac")])
    st, sync = _ctx({"HST": "조직학"})        # PATH 미구독
    with st:
        resp = _post(client, data, subject_code="PATH")
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "SUBJECT_NOT_SUBSCRIBED"
    assert sync.call_count == 0                # 행 처리 전 전면 거부


def test_upload_subject_param_not_trusted_from_client(client):
    """?subject_code 조작(타 기관 과목)으로 비구독 과목 등록 불가 — 서버 _subscribed_subjects 재검증."""
    data = _xlsx_bytes([("김", "학생", "a@c.ac")])
    st, sync = _ctx({"HST": "조직학"})
    with st:
        resp = _post(client, data, subject_code="ANAT")   # 타 기관/미구독 과목
    assert resp.status_code == 403
    assert sync.call_count == 0


# ─────────────────────────────────────────────
# 3. 3칸 파싱 + 지위 allowlist
# ─────────────────────────────────────────────
def test_upload_position_allowlist_skip_and_report(client):
    """행정직원 등 allowlist 외 지위 → skip-and-report(전체 롤백 아님), 정상 행만 sync."""
    data = _xlsx_bytes([("김", "학생", "a@c.ac"),
                        ("박", "행정직원", "b@c.ac"),   # 거절(행정직원=admin-only)
                        ("이", "교수", "c@c.ac")])
    st, sync = _ctx({"HST": "조직학"})
    with st:
        resp = _post(client, data, subject_code="HST")
    assert resp.status_code == 200
    j = resp.get_json()
    assert j["counts"].get("invalid_position") == 1
    assert sync.call_count == 2                 # 정상 2행만 처리


def test_upload_dedup_email_within_one_subject(client):
    """같은 업로드(=같은 과목) 내 이메일 중복 → duplicate_row(1회만 sync)."""
    data = _xlsx_bytes([("김", "학생", "a@c.ac"), ("김2", "조교", "a@c.ac")])
    st, sync = _ctx({"HST": "조직학"})
    with st:
        resp = _post(client, data, subject_code="HST")
    j = resp.get_json()
    assert j["counts"].get("duplicate_row") == 1
    assert sync.call_count == 1


# ─────────────────────────────────────────────
# 4. 과목 파라미터 누락 → 400
# ─────────────────────────────────────────────
def test_upload_missing_subject_param_400(client):
    data = _xlsx_bytes([("김", "학생", "a@c.ac")])
    st, sync = _ctx({"HST": "조직학"})
    with st:
        resp = _post(client, data, subject_code=None)   # 과목 미선택
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "MISSING_SUBJECT"
    assert sync.call_count == 0


# ─────────────────────────────────────────────
# 5. [Codex#1] 커넥션 누수 차단 — 모든 경로에서 acquire == release (풀 고갈 없음)
# ─────────────────────────────────────────────
from contextlib import ExitStack


def _spy_ctx(subjects, sync_outcome="added_no_user"):
    """get_db_conn/release_db_conn 을 스파이로 잡아 acquire/release 균형을 검증."""
    st = ExitStack()
    st.enter_context(patch("auth.decorators._authenticate", _fake_auth()))
    st.enter_context(patch("auth.decorators._csrf_ok", lambda: True))
    st.enter_context(patch("server_render._is_institution_admin", return_value=True))
    st.enter_context(patch("server_render._subscribed_subjects", side_effect=lambda cur, inst: dict(subjects)))
    sync = st.enter_context(patch("server_render._sync_member", return_value=sync_outcome))
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = MagicMock()
    get_mock = st.enter_context(patch("server_render.get_db_conn", return_value=conn))
    rel_mock = st.enter_context(patch("server_render.release_db_conn"))
    return st, get_mock, rel_mock, conn


def test_upload_403_releases_connection(client):
    """비구독 과목 403 early return 에서도 커넥션이 정확히 1회 release(누수 없음)."""
    data = _xlsx_bytes([("김", "학생", "a@c.ac")])
    st, get_mock, rel_mock, conn = _spy_ctx({"HST": "조직학"})
    with st:
        resp = _post(client, data, subject_code="PATH")     # 비구독 → 403
    assert resp.status_code == 403
    assert get_mock.call_count == 1
    assert rel_mock.call_count == 1                          # acquire 1 == release 1
    assert rel_mock.call_args.args[0] is conn               # 그 conn 을 반환


def test_upload_repeated_403_no_pool_leak(client):
    """비구독 403 을 반복 호출해도 매번 release — 풀 고갈(누적 미반환) 없음."""
    data = _xlsx_bytes([("김", "학생", "a@c.ac")])
    for _ in range(10):
        st, get_mock, rel_mock, _conn = _spy_ctx({"HST": "조직학"})
        with st:
            resp = _post(client, data, subject_code="PATH")
        assert resp.status_code == 403
        assert get_mock.call_count == rel_mock.call_count == 1   # 매 호출 acquire==release


def test_upload_success_releases_connection(client):
    """정상 경로도 정확히 1회 release(중복 release 없음)."""
    data = _xlsx_bytes([("김", "학생", "a@c.ac")])
    st, get_mock, rel_mock, _conn = _spy_ctx({"HST": "조직학"})
    with st:
        resp = _post(client, data, subject_code="HST")
    assert resp.status_code == 200
    assert get_mock.call_count == rel_mock.call_count == 1


def test_upload_missing_subject_does_not_acquire_conn(client):
    """과목 누락(400)은 conn 획득 전에 거부 — 애초에 acquire 안 함(누수 불가)."""
    data = _xlsx_bytes([("김", "학생", "a@c.ac")])
    st, get_mock, rel_mock, _conn = _spy_ctx({"HST": "조직학"})
    with st:
        resp = _post(client, data, subject_code=None)
    assert resp.status_code == 400
    assert get_mock.call_count == 0 and rel_mock.call_count == 0


# ─────────────────────────────────────────────
# 6. 개별 추가(POST /portal/api/roster) — 커넥션 위생 + 빈 과목 통일(Codex#2)
# ─────────────────────────────────────────────
def _post_add(client, body):
    import json
    return client.post("/portal/api/roster", data=json.dumps(body),
                       content_type="application/json")


def test_add_403_releases_connection(client):
    """개별추가 비구독 403 early return 에서도 conn 1회 release(누수 없음)."""
    st, get_mock, rel_mock, conn = _spy_ctx({"HST": "조직학"})
    with st:
        resp = _post_add(client, {"name": "김", "position": "학생",
                                  "subject_code": "PATH", "email": "a@c.ac"})
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "SUBJECT_NOT_SUBSCRIBED"
    assert get_mock.call_count == 1 and rel_mock.call_count == 1
    assert rel_mock.call_args.args[0] is conn


def test_add_missing_subject_400_before_conn(client):
    """[Codex#2] 개별추가 빈/누락 과목 → conn 획득 전 400(MISSING_SUBJECT), 업로드와 대칭."""
    st, get_mock, rel_mock, _conn = _spy_ctx({"HST": "조직학"})
    with st:
        resp = _post_add(client, {"name": "김", "position": "학생",
                                  "subject_code": "", "email": "a@c.ac"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "MISSING_SUBJECT"
    assert get_mock.call_count == 0 and rel_mock.call_count == 0


def test_add_success_releases_connection(client):
    st, get_mock, rel_mock, _conn = _spy_ctx({"HST": "조직학"})
    with st:
        resp = _post_add(client, {"name": "김", "position": "학생",
                                  "subject_code": "HST", "email": "a@c.ac"})
    assert resp.status_code == 200
    assert get_mock.call_count == rel_mock.call_count == 1
