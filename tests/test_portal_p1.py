"""
기관 포털 P1(명단 관리) + D18(드롭다운 기준) pytest.

CLAUDE.md §9·§21·§3(sync D17 해결)·§18 D18. §12 체크리스트 1·3·5·6·7·8·9 직결.
- sync 4분기(A 전환 / B 다과목보류 / C 접근창닫힘보류 / D 신규) + 좌석부족 skip + no_change
- role 불변(겸직 admin 보존) / 좌석 FOR UPDATE 직렬화
- 제거 회수(active 좌석반환 / 겸직 계정보존 / __ADMIN__ 보호 / not_found / roster-only)
- 포털 scope 격리(인증 필요 / 비관리자 FORBIDDEN / 자기 기관 scope)
- D18 드롭다운 = 구독 보유 기관만(JOIN subscriptions)

DB 는 mock(로컬 RDS 접속 불가). 핵심 sync 로직은 순수 헬퍼 단위 테스트로 정밀 검증한다.
"""
import os
from datetime import date
from unittest.mock import MagicMock, patch

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest")
os.environ.setdefault("GMAIL_USER", "test@gmail.com")
os.environ.setdefault("GMAIL_APP_PW", "test-app-pw")
os.environ.setdefault("ADMIN_SECRET_KEY", "test-admin-secret-for-pytest")

import pytest
import server_render as sr   # 라이브 모듈 참조 — test_auth 가 importlib.reload(server_render)를
                             #   호출하므로, 예외 클래스/헬퍼는 반드시 모듈 속성으로 늦게 조회한다
                             #   (by-name import 는 reload 후 구 객체에 묶여 pytest.raises 가 어긋남).
from server_render import app, _sync_member, _remove_member
from auth.decorators import ADMIN_ROSTER_SUBJECT

TODAY = date(2026, 9, 1)


def _norm(sql):
    return " ".join(str(sql).split()).lower()


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _cur():
    c = MagicMock()
    return c


def _update_users_sqls(cur):
    """실행된 SQL 중 'UPDATE users ...' 문만 추출(공백 정규화·소문자)."""
    out = []
    for call in cur.execute.call_args_list:
        sql = " ".join(str(call.args[0]).split()).lower()
        if sql.startswith("update users"):
            out.append(sql)
    return out


# ─────────────────────────────────────────────
# _sync_member — 4분기 + 좌석부족 + no_change + role 불변
# ─────────────────────────────────────────────
def test_sync_branch_d_new_email_added_no_user():
    """분기 D: 기존 user 없음 → roster 행만 추가, 좌석 미점유."""
    cur = _cur()
    cur.fetchone.side_effect = [None]   # users 조회 → 없음
    out = _sync_member(cur, "CNU", "HST", "new@cnu.ac.kr", "김신규", "학생", TODAY, {})
    assert out == "added_no_user"
    assert _update_users_sqls(cur) == []   # user UPDATE 없음


def test_sync_branch_b_multi_subject_hold():
    """분기 B: 기존 user가 이미 다른 과목 active → 덮어쓰지 않음(D12)."""
    cur = _cur()
    cur.fetchone.side_effect = [(7, "PATH", "active")]   # 이미 PATH active
    out = _sync_member(cur, "CNU", "HST", "u@cnu.ac.kr", "이겸", "학생", TODAY, {})
    assert out == "multi_subject_hold"
    assert _update_users_sqls(cur) == []   # 기존 과목 유지, UPDATE 없음


def test_sync_branch_c_window_closed_pending():
    """분기 C: admin-only 사용자 + 접근창 닫힘(구독 없음/미래학기) → admin-only 유지(fail-closed)."""
    cur = _cur()
    # users=(id, NULL) → admin-only / active_window_subscription fetchone=None(창 닫힘)
    cur.fetchone.side_effect = [(9, None, "active"), None]
    out = _sync_member(cur, "CNU", "HST", "adm@cnu.ac.kr", "박관리", "조교", TODAY, {})
    assert out == "pending_window"
    assert _update_users_sqls(cur) == []   # subject_code 채우지 않음(fail-closed §5-4)


def test_sync_branch_a_promote_synced():
    """분기 A: admin-only + 접근창 열림 + 좌석 여유 → NULL→과목 전환, role 불변."""
    cur = _cur()
    # users=(id, NULL) / 구독 max_seats=150 / 현재 좌석 0
    cur.fetchone.side_effect = [(11, None, "active"), (150,), (0,)]
    seat_cache = {}
    out = _sync_member(cur, "CNU", "HST", "adm@cnu.ac.kr", "최겸직", "교수", TODAY, seat_cache)
    assert out == "synced"
    ups = _update_users_sqls(cur)
    assert len(ups) == 1
    assert "subject_code" in ups[0] and "position" in ups[0]
    assert "role" not in ups[0]            # ★ role 불변(겸직 admin 보존, §3)
    # 메모리 좌석 차감 확인
    assert seat_cache["HST"][1] == 1


def test_sync_branch_a_seat_full_skip():
    """분기 A 좌석부족: 좌석 소진 → skip(admin-only 유지), 전체 롤백 아님."""
    cur = _cur()
    cur.fetchone.side_effect = [(12, None, "active"), (5,), (5,)]   # max_seats=5, used=5
    out = _sync_member(cur, "CNU", "HST", "adm2@cnu.ac.kr", "정만석", "학생", TODAY, {})
    assert out == "seat_full"
    assert _update_users_sqls(cur) == []   # 전환 안 함


def test_sync_no_change_updates_position_only():
    """이미 같은 과목 active → position 만 동기화(좌석·subject·role 불변)."""
    cur = _cur()
    cur.fetchone.side_effect = [(13, "HST", "active")]
    out = _sync_member(cur, "CNU", "HST", "s@cnu.ac.kr", "강학생", "조교", TODAY, {})
    assert out == "no_change"
    ups = _update_users_sqls(cur)
    assert len(ups) == 1
    assert "position" in ups[0]
    assert "subject_code" not in ups[0]    # 과목은 유지
    assert "role" not in ups[0]


def test_sync_seat_cache_serializes_bulk():
    """일괄: 같은 과목 두 admin-only 전환 시 좌석 캐시로 누적 차감(과목 단위 직렬화)."""
    cur = _cur()
    # 1행: users(NULL) → 구독 max_seats=1, used=0 → 전환(used→1)
    # 2행: users(NULL) → 캐시 사용(추가 구독/카운트 쿼리 없음) → used=1>=1 → seat_full
    cur.fetchone.side_effect = [(21, None, "active"), (1,), (0,), (22, None, "active")]
    seat_cache = {}
    o1 = _sync_member(cur, "CNU", "HST", "a@cnu.ac.kr", "A", "학생", TODAY, seat_cache)
    o2 = _sync_member(cur, "CNU", "HST", "b@cnu.ac.kr", "B", "학생", TODAY, seat_cache)
    assert o1 == "synced"
    assert o2 == "seat_full"


def test_sync_branch_a_uses_for_update_lock():
    """분기 A 좌석검사는 구독 행 FOR UPDATE 로 직렬화한다(§5-3)."""
    cur = _cur()
    cur.fetchone.side_effect = [(30, None, "active"), (150,), (0,)]
    _sync_member(cur, "CNU", "HST", "x@cnu.ac.kr", "X", "학생", TODAY, {})
    sqls = " ".join(" ".join(str(c.args[0]).split()).lower() for c in cur.execute.call_args_list)
    assert "for update" in sqls


# ─────────────────────────────────────────────
# _remove_member — 회수/보호
# ─────────────────────────────────────────────
def test_remove_active_subject_reclaims_seat():
    """active 과목 행 삭제 → subject_code NULL 회수(좌석 반환), 계정 삭제 아님."""
    cur = _cur()
    cur.rowcount = 1
    cur.fetchone.side_effect = [(40, "HST")]   # user 현재 active 과목 == 삭제 과목
    out = _remove_member(cur, "CNU", "HST", "s@cnu.ac.kr")
    assert out == "removed_seat_reclaimed"
    ups = _update_users_sqls(cur)
    assert len(ups) == 1
    assert "subject_code = null" in ups[0].replace("  ", " ")
    assert "role" not in ups[0]                # 계정·role 불변(§9)
    # users DELETE 없음
    assert not any(str(c.args[0]).strip().lower().startswith("delete from users")
                   for c in cur.execute.call_args_list)


def test_remove_moonlight_keeps_account():
    """겸직(__ADMIN__ 보유) active 과목 제거 → admin-only 복귀(계정 보존, role 불변)."""
    cur = _cur()
    cur.rowcount = 1
    cur.fetchone.side_effect = [(41, "HST")]
    out = _remove_member(cur, "CNU", "HST", "moon@cnu.ac.kr")
    assert out == "removed_seat_reclaimed"
    # 삭제된 것은 institution_rosters 행뿐 + users는 UPDATE(subject NULL)만
    deletes = [str(c.args[0]).strip().lower() for c in cur.execute.call_args_list
               if str(c.args[0]).strip().lower().startswith("delete")]
    assert all("institution_rosters" in d for d in deletes)


def test_remove_admin_row_protected():
    """__ADMIN__ 행은 포털에서 제거 불가(읽기전용, 슈퍼관리자 관할)."""
    cur = _cur()
    out = _remove_member(cur, "CNU", ADMIN_ROSTER_SUBJECT, "adm@cnu.ac.kr")
    assert out == "admin_row_protected"
    cur.execute.assert_not_called()           # DB 변경 없음


def test_remove_not_found():
    """없는 명단 행 삭제 → not_found(영향 0)."""
    cur = _cur()
    cur.rowcount = 0
    out = _remove_member(cur, "CNU", "HST", "ghost@cnu.ac.kr")
    assert out == "not_found"
    assert _update_users_sqls(cur) == []


def test_remove_roster_only_when_user_on_other_subject():
    """삭제 과목이 user의 현재 active 과목이 아니면 roster 행만 제거(좌석 변화 없음)."""
    cur = _cur()
    cur.rowcount = 1
    cur.fetchone.side_effect = [(42, "PATH")]   # user는 PATH active, 삭제는 HST
    out = _remove_member(cur, "CNU", "HST", "u@cnu.ac.kr")
    assert out == "removed_roster_only"
    assert _update_users_sqls(cur) == []


# ─────────────────────────────────────────────
# D18 — 가입 드롭다운 = 구독 보유 기관만
# ─────────────────────────────────────────────
def test_d18_dropdown_subscription_join(client):
    """GET /api/institutions 는 subscriptions JOIN 으로 구독 보유 기관만 반환(SA·공급사 제외)."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.fetchall.return_value = [("CNU", "충남대학교 의과대학"), ("SNU", "서울대학교")]
    with patch("server_render.get_db_conn", return_value=mock_conn), \
         patch("server_render.release_db_conn"):
        resp = client.get("/api/institutions")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    ids = [i["id"] for i in data["institutions"]]
    assert ids == ["CNU", "SNU"]
    sql = " ".join(str(mock_cur.execute.call_args.args[0]).split()).lower()
    assert "join subscriptions" in sql
    assert "is_subscribable" not in sql        # 죽은 컬럼 의존 제거


# ─────────────────────────────────────────────
# 포털 scope 격리 게이트
# ─────────────────────────────────────────────
def test_portal_roster_requires_auth(client):
    """비로그인 GET /portal/api/roster → 401(login_required)."""
    resp = client.get("/portal/api/roster")
    assert resp.status_code == 401


def _fake_auth(uid="5", inst="CNU", role="admin", subject="HST"):
    def f():
        from flask import g
        g.user_id = uid
        g.institution_id = inst
        g.role = role
        g.subject_code = subject
        return None
    return f


def test_portal_guard_forbidden_non_admin(client):
    """로그인했으나 관리자 roster 행 없음 → 403 FORBIDDEN(role 단독 우회 불가)."""
    with patch("auth.decorators._authenticate", _fake_auth(role="viewer")), \
         patch("server_render._is_institution_admin", return_value=False):
        resp = client.get("/portal/api/roster")
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "FORBIDDEN"


def test_portal_roster_scope_uses_g_institution(client):
    """GET 명단은 자기 기관(g.institution_id)으로만 조회한다(§9 scope 격리)."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.fetchall.side_effect = [
        [("HST", "조직학")],                                    # _subscribed_subjects
        [("김민준", "학생", "HST", "mj@cnu.ac.kr", True),       # member
         ("관리자", None, ADMIN_ROSTER_SUBJECT, "adm@cnu.ac.kr", False)],  # admin(읽기전용)
    ]
    with patch("auth.decorators._authenticate", _fake_auth(inst="CNU")), \
         patch("server_render._is_institution_admin", return_value=True), \
         patch("server_render.get_db_conn", return_value=mock_conn), \
         patch("server_render.release_db_conn"):
        resp = client.get("/portal/api/roster")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["institution_id"] == "CNU"
    assert len(data["members"]) == 1
    assert len(data["admins"]) == 1            # __ADMIN__ 행은 admins 로 분리(읽기전용)
    # 모든 쿼리가 'CNU' scope 로 파라미터화됐는지
    used_insts = []
    for c in mock_cur.execute.call_args_list:
        if len(c.args) > 1 and c.args[1]:
            used_insts.extend([a for a in c.args[1] if a == "CNU"])
    assert "CNU" in used_insts


# ═════════════════════════════════════════════════════════════════════════════
# 외부검증(Codex+Gemini) 반영 수정 — 회귀 방지 (v3.9)
# ═════════════════════════════════════════════════════════════════════════════

# ── High#1 IDOR: user 조회·UPDATE가 institution_id 로 스코프되는가 ──
def test_sync_user_lookup_scoped_to_institution():
    """A기관 sync가 타 기관 user를 못 본다 — user SELECT 가 institution_id 로 스코프(타 기관 이메일=없음 취급)."""
    cur = _cur()
    cur.fetchone.side_effect = [None]   # 스코프 밖 → '현재 기관에 user 없음'
    out = _sync_member(cur, "CNU", "HST", "victim@other.ac.kr", "X", "학생", TODAY, {})
    assert out == "added_no_user"
    sel = [c for c in cur.execute.call_args_list
           if "from users" in _norm(c.args[0])][0]
    assert "institution_id" in _norm(sel.args[0])
    assert "CNU" in sel.args[1]
    assert _update_users_sqls(cur) == []   # 타 기관 user 변경 없음


def test_sync_synced_update_scoped_to_institution():
    """분기 A 의 user UPDATE 도 institution_id 로 스코프된다(타 기관 user 변조 차단)."""
    cur = _cur()
    cur.fetchone.side_effect = [(11, None, "active"), (150,), (0,)]
    _sync_member(cur, "CNU", "HST", "u@cnu.ac.kr", "U", "학생", TODAY, {})
    ups = _update_users_sqls(cur)
    assert len(ups) == 1
    assert "institution_id" in ups[0]


def test_remove_user_lookup_scoped_to_institution():
    """제거 회수도 institution_id 로 스코프 — 타 기관 user의 active 과목을 NULL 회수하지 못한다."""
    cur = _cur()
    cur.rowcount = 1
    cur.fetchone.side_effect = [None]   # 스코프 밖 user
    out = _remove_member(cur, "CNU", "HST", "victim@other.ac.kr")
    assert out == "removed_roster_only"
    sel = [c for c in cur.execute.call_args_list
           if "select id, subject_code from users" in _norm(c.args[0])][0]
    assert "institution_id" in _norm(sel.args[0])
    assert "CNU" in sel.args[1]
    assert _update_users_sqls(cur) == []


# ── Med#3: seat_full 이면 roster 행도 만들지 않는다 ──
def test_sync_seat_full_does_not_upsert_roster():
    """좌석 소진 시 roster upsert 자체가 일어나지 않아야 한다(그 행만 skip, 아무 것도 안 바뀜)."""
    cur = _cur()
    cur.fetchone.side_effect = [(12, None, "active"), (5,), (5,)]   # admin-only, max=5, used=5
    out = _sync_member(cur, "CNU", "HST", "a@cnu.ac.kr", "A", "학생", TODAY, {})
    assert out == "seat_full"
    inserts = [c for c in cur.execute.call_args_list
               if "insert into institution_rosters" in _norm(c.args[0])]
    assert inserts == []                   # roster 행 미생성(Med#3)
    assert _update_users_sqls(cur) == []   # user 불변


def test_sync_accepted_branches_do_upsert_roster():
    """seat_full 외 분기(예: 분기 D)는 roster 행을 남긴다."""
    cur = _cur()
    cur.fetchone.side_effect = [None]   # 신규(분기 D)
    out = _sync_member(cur, "CNU", "HST", "new@cnu.ac.kr", "N", "학생", TODAY, {})
    assert out == "added_no_user"
    inserts = [c for c in cur.execute.call_args_list
               if "insert into institution_rosters" in _norm(c.args[0])]
    assert len(inserts) == 1


# ── High#2: 이메일 validator allowlist (저장형 XSS 차단) ──
@pytest.mark.parametrize("bad", [
    "a');alert(1)//@b.com",
    'a"@b.com',
    "a;b@b.com",
    "a(b)@b.com",
    "a<b>@b.com",
    "a b@b.com",
    "noat.example.com",
])
def test_email_regex_rejects_unsafe(bad):
    assert not sr._PORTAL_EMAIL_RE.match(bad)


@pytest.mark.parametrize("good", [
    "mj.kim+1@cnu.ac.kr",
    "a_b-c%d@sub.domain.co",
    "Prof123@univ.ac.kr",
])
def test_email_regex_accepts_normal(good):
    assert sr._PORTAL_EMAIL_RE.match(good)


# ── High#4: xlsx/업로드 안전 파싱 ──
def test_rows_from_iter_row_cap():
    """스트리밍 중 행상한 초과 시 즉시 거부(다 읽은 뒤가 아님). 시트는 3칸(이름·지위·이메일)."""
    def gen():
        yield ("이름", "지위", "이메일")   # 헤더 — 스킵
        for i in range(10):
            yield (f"n{i}", "학생", f"u{i}@c.ac")
    with pytest.raises(sr._RosterParseError):
        sr._rows_from_iter(gen(), 3)


def test_rows_from_iter_within_cap_ok():
    def gen():
        yield ("김", "학생", "a@c.ac")
        yield ("이", "조교", "b@c.ac")
    rows = sr._rows_from_iter(gen(), 2000)
    assert len(rows) == 2
    assert rows[0] == ("김", "학생", "a@c.ac")   # 3칸 위치읽기(이름·지위·이메일)


def test_read_capped_rejects_oversize():
    import io
    big = io.BytesIO(b"x" * (1024 * 1024))   # 1MB
    with pytest.raises(sr._RosterParseError):
        sr._read_capped(big, 100 * 1024)        # 100KB 상한


def test_read_capped_allows_small():
    import io
    data = sr._read_capped(io.BytesIO(b"hello"), 100 * 1024)
    assert data == b"hello"


def test_xlsx_zip_guard_rejects_extreme_entries():
    """극단적 비정상(>1000 entry)만 거른다(압축폭탄 보조 backstop)."""
    import io, zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for i in range(1100):                # > _PORTAL_XLSX_MAX_ENTRIES(1000)
            z.writestr(f"f{i}.xml", b"x")
    with pytest.raises(sr._RosterParseError):
        sr._xlsx_zip_guard(buf.getvalue())


def test_xlsx_zip_guard_allows_normal_business_file():
    """[Low#2] 시트·이미지·로고·스타일 다수(entry 100 초과)인 정상 업무 xlsx는 통과해야 한다(오탐 방지)."""
    import io, zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for i in range(150):                 # 100 초과지만 정상 범위
            z.writestr(f"xl/media/image{i}.png", b"\x89PNG")
        z.writestr("xl/worksheets/sheet1.xml", b"<x/>")
    sr._xlsx_zip_guard(buf.getvalue())        # 예외 없이 통과


def test_xlsx_zip_guard_rejects_non_zip():
    with pytest.raises(sr._RosterParseError):
        sr._xlsx_zip_guard(b"this is not a zip file")


def test_xlsx_zip_guard_passes_normal():
    import io, zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/worksheets/sheet1.xml", b"<x/>")
    sr._xlsx_zip_guard(buf.getvalue())          # 예외 없이 통과


# ── Codex 2차 Med#1: 좌석 캐시가 pending user를 좌석 점유로 오산하지 않는가 ──
def test_sync_pending_user_does_not_consume_seat():
    """max_seats=1, active=0. 1행=pending admin-only 전환(좌석 미점유) → 2행=active user 정상 처리(seat_full 아님)."""
    cur = _cur()
    # 1행: pending admin-only(NULL,'pending_verification') → window open, active_count=0
    #   2행: active admin-only(NULL,'active') → 캐시상 used 여전히 0 이라 전환 성공(증분 +1)
    cur.fetchone.side_effect = [
        (51, None, "pending_verification"),  # 1행 user
        (1,),                                 # active_window max_seats=1
        (0,),                                 # active_seat_count=0
        (52, None, "active"),                 # 2행 user (캐시 재사용 — 추가 구독/카운트 쿼리 없음)
    ]
    seat_cache = {}
    o1 = _sync_member(cur, "CNU", "HST", "pend@cnu.ac.kr", "P", "학생", TODAY, seat_cache)
    o2 = _sync_member(cur, "CNU", "HST", "act@cnu.ac.kr", "A", "학생", TODAY, seat_cache)
    assert o1 == "synced"                     # pending 도 subject_code 동기화
    assert seat_cache["HST"][1] == 1          # active(2행)만 좌석 +1 — pending(1행)은 미가산(§0 active 기준)
    assert o2 == "synced"                     # 빈 좌석이므로 정상 전환(오거부 아님)


def test_sync_pending_user_not_blocked_by_seat_full():
    """좌석이 꽉 차도(active=max) pending user 전환은 seat_full로 막지 않는다(verify가 활성화 시점 집행)."""
    cur = _cur()
    cur.fetchone.side_effect = [
        (60, None, "pending_verification"),   # pending admin-only
        (1,),                                 # max_seats=1
        (1,),                                 # active_seat_count=1 (이미 만석)
    ]
    out = _sync_member(cur, "CNU", "HST", "p2@cnu.ac.kr", "P2", "학생", TODAY, {})
    assert out == "synced"                    # seat_full 아님 — subject 동기화, 좌석은 verify FOR UPDATE가 집행
    ups = _update_users_sqls(cur)
    assert len(ups) == 1 and "subject_code" in ups[0]
