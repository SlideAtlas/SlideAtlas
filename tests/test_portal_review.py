"""
포털 P2+P3 외부검증(Codex+Gemini) 반영 수정 5건 회귀 방지 pytest.

1. [High] P3 조회수는 access_logs 스냅샷(al.institution_id·al.subject_code) 기준 — 현재 u/s 재분류 금지
2. [Med] P3 active_users = status='active'(NULL 제외) — active_seat_count(§0)와 일치
3. [Med] max_seats 합산에 접근창 필터(미래 갱신 구독 합산 차단) — active_seat_count 불변
4. [타임존] P2·P3 날짜 연산 _today_kst(KST) 일괄 — _sub_status·report_range
5. [Low] 잘못된 period → 전체 아닌 기본 '3m'
"""
import os
from datetime import date
from unittest.mock import MagicMock, patch

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest")
os.environ.setdefault("GMAIL_USER", "test@gmail.com")
os.environ.setdefault("GMAIL_APP_PW", "test-app-pw")
os.environ.setdefault("ADMIN_SECRET_KEY", "test-admin-secret-for-pytest")

import pytest
import server_render as sr
from server_render import app


def _norm(sql):
    return " ".join(str(sql).split()).lower()


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _fake_auth(uid="5", inst="CNU", role="admin", subject="HST"):
    def f():
        from flask import g
        g.user_id = uid
        g.institution_id = inst
        g.role = role
        g.subject_code = subject
        return None
    return f


def _mock_db():
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    return mock_conn, mock_cur


def _setup_report(mock_cur, *, subjects=(("HST", "조직학"),),
                  by_position=(("학생", 10),), window_rows=(("HST", 150),),
                  members=(8, 3, 1), total_views=400, monthly=(("2026-05", 120),),
                  top=(("SA-HST-001", "소장", "H&E", 90),),
                  ai_q=42, ai_monthly=(("2026-05", 20),)):
    # v3.15(2R): 좌석은 window 구독 rows(subject_code, max_seats) fetchall 로 Python 합산.
    #   members fetchone 은 window_codes 있을 때만.
    mock_cur.fetchall.side_effect = [
        list(subjects), list(by_position), list(window_rows),
        list(monthly), list(top), list(ai_monthly),
    ]
    fone = []
    if window_rows:
        fone.append(members)
    fone += [(total_views,), (ai_q,)]
    mock_cur.fetchone.side_effect = fone


def _run(client, mock_conn, path, auth=None):
    auth = auth or _fake_auth(inst="CNU")
    with patch("auth.decorators._authenticate", auth), \
         patch("server_render._is_institution_admin", return_value=True), \
         patch("server_render.get_db_conn", return_value=mock_conn), \
         patch("server_render.release_db_conn"):
        return client.get(path)


def _access_sqls(mock_cur):
    return [_norm(c.args[0]) for c in mock_cur.execute.call_args_list
            if "access_logs al" in _norm(c.args[0])]


# ═════════════════════════════════════════════════════════════════
# 1. [High] 조회수 = access_logs 스냅샷 기준
# ═════════════════════════════════════════════════════════════════
def test_views_filter_on_access_log_snapshot_not_current(client):
    """total_views·monthly·top 은 al.institution_id·al.subject_code(스냅샷)로 필터, u/s 현재값 아님."""
    mock_conn, mock_cur = _mock_db()
    _setup_report(mock_cur)
    _run(client, mock_conn, "/portal/api/report?subject_code=HST")
    al_sqls = _access_sqls(mock_cur)
    assert len(al_sqls) == 3        # total_views, monthly, top_slides
    for sql in al_sqls:
        assert "al.institution_id = %s" in sql      # 사용자 기관 스냅샷
        assert "al.subject_code" in sql             # 슬라이드 과목 스냅샷
        assert "s.subject_code" not in sql          # 현재 슬라이드 과목으로 재분류 금지
        assert "u.institution_id" not in sql        # 현재 사용자 기관으로 재분류 금지


def test_total_views_and_monthly_do_not_join_users(client):
    """조회수/월별은 users 조인 불요(스냅샷 컬럼만) — 현재 u 상태 의존 제거."""
    mock_conn, mock_cur = _mock_db()
    _setup_report(mock_cur)
    _run(client, mock_conn, "/portal/api/report?subject_code=HST")
    for sql in _access_sqls(mock_cur):
        if "group by s.id" in sql:
            continue   # top_slides 는 표시용 slides 조인 허용(필터는 al 스냅샷)
        assert "join users" not in sql


def test_views_snapshot_uses_log_subject_for_all(client):
    """'all'도 al.subject_code = ANY(구독과목)로 스냅샷 필터(시간축 오염 방지)."""
    mock_conn, mock_cur = _mock_db()
    _setup_report(mock_cur, subjects=(("HST", "조직학"), ("PATH", "병리학")))
    _run(client, mock_conn, "/portal/api/report?subject_code=all")
    for sql in _access_sqls(mock_cur):
        assert "al.subject_code = any(%s)" in sql


# ═════════════════════════════════════════════════════════════════
# 2. [Med] active = status='active' (NULL 제외, active_seat_count 일치)
# ═════════════════════════════════════════════════════════════════
def test_active_excludes_null_status(client):
    """구성원 활동 active 버킷은 u.status='active'(COALESCE 금지) — NULL 은 active 아님(§0)."""
    mock_conn, mock_cur = _mock_db()
    _setup_report(mock_cur)
    _run(client, mock_conn, "/portal/api/report?subject_code=HST")
    msql = [_norm(c.args[0]) for c in mock_cur.execute.call_args_list
            if "filter (where u.status=" in _norm(c.args[0])][0]
    assert "u.status='active'" in msql
    assert "coalesce(u.status,'active')='active'" not in msql   # NULL→active 오판 제거
    assert "is distinct from" in msql                           # NULL 안전 비활성 분류


def test_active_count_matches_seat_definition(client):
    """active_seat_count(auth)도 status='active' 만 센다 — P3 active 정의와 동일(§0)."""
    import inspect
    from auth.auth import active_seat_count
    src = inspect.getsource(active_seat_count)
    assert "status = 'active'" in " ".join(src.split())
    assert "coalesce" not in src.lower()    # NULL 포함 안 함 → P3 와 같은 기준


# ═════════════════════════════════════════════════════════════════
# 3. [Med] max_seats 합산 접근창 필터
# ═════════════════════════════════════════════════════════════════
def test_max_seats_sum_applies_access_window(client):
    """좌석 정원은 접근창(access_open_date<=today<=subscription_end) 내 구독만 합산(today=_today_kst)."""
    mock_conn, mock_cur = _mock_db()
    _setup_report(mock_cur)
    with patch("server_render._today_kst", return_value=date(2026, 9, 1)):
        _run(client, mock_conn, "/portal/api/report?subject_code=HST")
    seat_sql = [(_norm(c.args[0]), c.args[1]) for c in mock_cur.execute.call_args_list
                if "from subscriptions" in _norm(c.args[0]) and "access_open_date" in _norm(c.args[0])][0]
    assert "access_open_date <= %s" in seat_sql[0]
    assert "subscription_end >= %s" in seat_sql[0]
    assert date(2026, 9, 1) in seat_sql[1]      # today=_today_kst 가 파라미터로


def test_max_seats_does_not_touch_active_seat_count(client):
    """좌석 윈도우 필터는 정원(SUM max_seats)만 — 사용자 점유 카운트 함수는 호출/변경 안 함(불변)."""
    mock_conn, mock_cur = _mock_db()
    _setup_report(mock_cur)
    with patch("server_render.active_seat_count") as asc:
        _run(client, mock_conn, "/portal/api/report?subject_code=HST")
        asc.assert_not_called()    # P3 report 는 active_seat_count 를 직접 쓰지 않음(members 쿼리로 산출)


# ═════════════════════════════════════════════════════════════════
# 4. [타임존] _today_kst 일괄 적용
# ═════════════════════════════════════════════════════════════════
def test_report_range_uses_today_kst():
    with patch("server_render._today_kst", return_value=date(2026, 9, 1)):
        start, end = sr._portal_report_range("3m")
    assert end == date(2026, 9, 1)
    assert start == date(2026, 6, 3)       # 90일 전 (KST today 기준)


def test_report_range_all_is_unbounded():
    start, end = sr._portal_report_range("all")
    assert start is None and end is None


def test_sub_status_uses_today_kst():
    """_sub_status 가 _date.today() 가 아니라 _today_kst 기준으로 판정(자정~9시 어긋남 제거)."""
    open_d, end_d = date(2026, 9, 1), date(2027, 2, 28)
    with patch("server_render._today_kst", return_value=date(2026, 9, 1)):
        assert sr._sub_status(open_d, end_d)[0] == "active"
    with patch("server_render._today_kst", return_value=date(2026, 8, 15)):
        assert sr._sub_status(open_d, end_d)[0] in ("upcoming", "pending")
    with patch("server_render._today_kst", return_value=date(2027, 3, 1)):
        assert sr._sub_status(open_d, end_d)[0] == "expired"


def test_report_date_boundary_half_open(client):
    """날짜 경계는 '>= start AND < end+1day'(half-open) — BETWEEN 양끝 포함 아님."""
    mock_conn, mock_cur = _mock_db()
    _setup_report(mock_cur)
    _run(client, mock_conn, "/portal/api/report?subject_code=HST&period=3m")
    for sql in _access_sqls(mock_cur):
        assert "al.accessed_at >= %s" in sql
        assert "al.accessed_at < %s + interval '1 day'" in sql
        assert "between" not in sql


# ═════════════════════════════════════════════════════════════════
# 5. [Low] period allowlist
# ═════════════════════════════════════════════════════════════════
def test_norm_report_period_allowlist():
    assert sr._norm_report_period("1m") == "1m"
    assert sr._norm_report_period("all") == "all"
    assert sr._norm_report_period("bogus") == "3m"     # 조용한 전체확장 차단
    assert sr._norm_report_period("") == "3m"


def test_bad_period_falls_back_not_all(client):
    """period=bad 요청 시 전체(무필터)가 아니라 3m(기본)으로 처리 — 날짜 필터가 살아있다."""
    mock_conn, mock_cur = _mock_db()
    _setup_report(mock_cur)
    resp = _run(client, mock_conn, "/portal/api/report?subject_code=HST&period=zzz")
    assert resp.status_code == 200
    assert resp.get_json()["period"] == "3m"
    # 날짜 필터가 적용됐는지(=전체가 아님): access_logs 쿼리에 날짜 경계 존재
    assert all("accessed_at >= %s" in sql for sql in _access_sqls(mock_cur))


# ═════════════════════════════════════════════════════════════════
# 2R 재검증 반영 — is_special 좌석 정합 / 소진율 분자=분모 / top_slides LEFT JOIN
# ═════════════════════════════════════════════════════════════════

# ── 2R#1: 특별계정 승격 시 subject_code=NULL (좌석 비점유, active_seat_count 같은 집합) ──
def test_special_promote_nulls_subject_code():
    """특별계정 승격 경로(기존 user)가 subject_code=NULL(+position NULL)로 정리한다."""
    import inspect
    n = " ".join(inspect.getsource(sr.api_special_accounts_create).split()).lower()
    assert "is_special = true" in n
    assert "subject_code = null" in n          # 좌석 비점유로 정리
    assert "position = null" in n


def test_p3_user_aggregation_has_no_is_special_filter(client):
    """P3 users 집계(등록·구성원)에 is_special 제외절이 없다 — 특별계정은 subject_code=NULL 로 자연 제외.
    → active_seat_count(is_special 절 없음)와 '글자까지 같은 집합'(§0)."""
    mock_conn, mock_cur = _mock_db()
    _setup_report(mock_cur)
    _run(client, mock_conn, "/portal/api/report?subject_code=HST")
    user_sqls = [_norm(c.args[0]) for c in mock_cur.execute.call_args_list
                 if "from users u" in _norm(c.args[0])]
    assert user_sqls
    for sql in user_sqls:
        assert "is_special" not in sql


def test_special_cleanup_migration_idempotent():
    """기존 특별계정 정리 마이그레이션: 멱등·트랜잭션·subject_code=NULL."""
    import os
    p = os.path.join(os.path.dirname(__file__), "..", "db", "special_subject_code_cleanup_migration.sql")
    sql = " ".join(open(p, encoding="utf-8").read().lower().split())
    assert "begin;" in sql and "commit;" in sql
    assert "set subject_code = null" in sql
    assert "coalesce(is_special, false) = true" in sql


# ── 2R#2: 소진율 분자(active_users)도 분모(max_seats)와 같은 접근창 집합(기준 A) ──
def test_active_users_restricted_to_window_codes(client):
    """구독은 HST·PATH지만 접근창 열린 건 HST뿐 → 구성원/활성(분자)이 window_codes(['HST'])만 본다(PATH 제외)."""
    mock_conn, mock_cur = _mock_db()
    _setup_report(mock_cur, subjects=(("HST", "조직학"), ("PATH", "병리학")),
                  window_rows=(("HST", 150),), members=(8, 3, 1))
    _run(client, mock_conn, "/portal/api/report?subject_code=all")
    msql = [(_norm(c.args[0]), c.args[1]) for c in mock_cur.execute.call_args_list
            if "filter (where u.status=" in _norm(c.args[0])][0]
    assert ["HST"] in msql[1]                   # 분자 대상 = window_codes
    flat = []
    for x in msql[1]:
        flat.extend(x) if isinstance(x, list) else flat.append(x)
    assert "PATH" not in flat                   # 만료(접근창 닫힘) 과목은 분자에서 제외


def test_expired_window_excludes_both_numerator_and_denominator(client):
    """접근창 열린 구독 0(전부 만료/미래) → active_users·max_seats 둘 다 0, util 0(집계 제외).
    분자 쿼리(members)도 실행되지 않아 '유령 active'가 0%로 왜곡되지 않는다(기준 A 검증)."""
    mock_conn, mock_cur = _mock_db()
    _setup_report(mock_cur, window_rows=(), total_views=50, monthly=(), top=(), ai_q=0, ai_monthly=())
    resp = _run(client, mock_conn, "/portal/api/report?subject_code=HST")
    d = resp.get_json()
    assert d["active_users"] == 0 and d["max_seats"] == 0 and d["util_pct"] == 0
    assert not any("filter (where u.status=" in _norm(c.args[0])
                   for c in mock_cur.execute.call_args_list)   # 분자 쿼리 skip


# ── 2R#4: top_slides LEFT JOIN + 제목 폴백(표시용 조인이 집계를 떨구지 않게) ──
def test_top_slides_left_join_with_title_fallback(client):
    mock_conn, mock_cur = _mock_db()
    _setup_report(mock_cur, top=(("SA-HST-001", "소장", "H&E", 90),
                                 ("SA-HST-099", "SA-HST-099", None, 5)))   # slide row 없음 → id 폴백
    resp = _run(client, mock_conn, "/portal/api/report?subject_code=HST")
    d = resp.get_json()
    top_sql = [_norm(c.args[0]) for c in mock_cur.execute.call_args_list
               if "left join slides s" in _norm(c.args[0])][0]
    assert "group by al.slide_id" in top_sql
    assert "coalesce(s.title_ko, al.slide_id)" in top_sql
    assert "SA-HST-099" in [t["id"] for t in d["top_slides"]]   # 깨진 참조도 집계에 포함


# ═════════════════════════════════════════════════════════════════
# 3R 재검증 반영 — P3 소진율 분모 과목별 권위 row 정규화(겹치는 구독 §0 정합)
# ═════════════════════════════════════════════════════════════════
def test_seat_denominator_distinct_on_subject(client):
    """분모(max_seats)는 과목별 권위 row 1개(DISTINCT ON + subscription_end DESC)로 정규화 — 중복 합산 금지."""
    mock_conn, mock_cur = _mock_db()
    _setup_report(mock_cur, window_rows=(("HST", 150),))   # DB(DISTINCT ON)가 과목당 1행 반환
    _run(client, mock_conn, "/portal/api/report?subject_code=HST")
    seat_sql = [_norm(c.args[0]) for c in mock_cur.execute.call_args_list
                if "from subscriptions" in _norm(c.args[0]) and "access_open_date" in _norm(c.args[0])][0]
    assert "distinct on (subject_code)" in seat_sql
    assert "order by subject_code, subscription_end desc" in seat_sql


def test_seat_denominator_reuses_auth_gate_ordering():
    """P3 분모 정규화가 인증 게이트(active_window_subscription)와 같은 행 선택 규칙(subscription_end DESC) 재사용(§0)."""
    import inspect
    from auth.auth import active_window_subscription
    gate = " ".join(inspect.getsource(active_window_subscription).split()).lower()
    assert "order by subscription_end desc" in gate                 # 게이트: 과목당 DESC LIMIT 1
    p3 = " ".join(inspect.getsource(sr._portal_report_data).split()).lower()
    assert "distinct on (subject_code)" in p3                       # P3 분모: 과목별 권위 row
    assert "order by subject_code, subscription_end desc" in p3     # 동일 DESC 규칙


def test_seat_denominator_not_double_counted(client):
    """권위 row 1개(150) → 분모 150(겹치는 구독이 300으로 중복 합산되지 않음). util=active/150."""
    mock_conn, mock_cur = _mock_db()
    _setup_report(mock_cur, window_rows=(("HST", 150),), members=(30, 0, 0))
    resp = _run(client, mock_conn, "/portal/api/report?subject_code=HST")
    d = resp.get_json()
    assert d["max_seats"] == 150
    assert d["util_pct"] == 20      # round(30/150*100) — 300 합산이면 10%로 왜곡됐을 것
