"""
단계1(포털 명단 성능) — 중복 admin roster 조회 제거(g 요청 스코프 캐시) 검증.

CLAUDE.md §8(매 요청 DB 권위)·§9(포털 게이트)·§13-2(인증 반환 shape·판정 의미 불변).
검증 포인트:
  1. 캐시 hit  — 같은 요청에서 _authenticate 가 g._admin_roster_cache 를 적재하면
                 _is_institution_admin 이 재조회 없이 재사용(한 요청 내 admin roster 조회 1회).
  2. 캐시 miss — 키(user_id/institution_id) 불일치 또는 캐시 부재면 기존 쿼리로 폴백해 정상 판정.
  3. ★ 의미 불변 — admin-only 구독 면제는 통과 그대로, __ADMIN__ roster 회수 시 면제 사라져
                 SUBSCRIPTION_EXPIRED 차단(회수 즉시 반영). 캐시가 회수를 가리지 않는다.
  4. 누수 방지 — 캐시는 요청 스코프(g) 한정 — 요청 간 누수 없음(다음 요청은 재조회).

DB 는 mock. _authenticate 는 decode_token 만 패치하고 fetchone 시퀀스로 구동한다.
"""
import os
import contextlib
from unittest.mock import MagicMock, patch

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest")
os.environ.setdefault("GMAIL_USER", "test@gmail.com")
os.environ.setdefault("GMAIL_APP_PW", "test-app-pw")
os.environ.setdefault("ADMIN_SECRET_KEY", "test-admin-secret-for-pytest")

import pytest
import server_render as sr
import auth.decorators as dec
from server_render import app
from auth.decorators import COOKIE_NAME


def _mk_conn(fetchone=None):
    """fetchone.side_effect 로 구동되는 mock conn/cur (with conn.cursor() 컨텍스트 지원)."""
    cur = MagicMock()
    if fetchone is not None:
        cur.fetchone.side_effect = list(fetchone)
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    return conn, cur


# _authenticate 메인쿼리 행 shape(8): (session_token, status, subject_code, special_expires_at,
#                                      role, is_special, institution_id, subscription_end)
def _main_row(subject_code=None, role="admin", is_special=False, inst="CNU",
              sub_end=None, status="active", session="sess", special_exp=None):
    return (session, status, subject_code, special_exp, role, is_special, inst, sub_end)


@contextlib.contextmanager
def _run_authenticate(fetchone, cookie="tok", sub="5", session="sess"):
    """request 컨텍스트(정상 pop 보장)에서 _authenticate 를 구동하고 (반환값, g, cur) 을 yield.

    contextmanager 라 with 블록을 벗어나면 요청 컨텍스트가 깔끔히 pop 된다(요청 간 누수 없음).
    """
    conn, cur = _mk_conn(fetchone=fetchone)
    payload = {"sub": sub, "session_token": session}
    with app.test_request_context('/', headers={'Cookie': f'{COOKIE_NAME}={cookie}'}):
        from flask import g
        with patch("auth.decorators.decode_token", return_value=payload), \
             patch("server_render.get_db_conn", return_value=conn), \
             patch("server_render.release_db_conn"):
            err = dec._authenticate()
            yield err, g, cur


# ─────────────────────────────────────────────
# 1. 캐시 hit — 한 요청 내 admin roster 조회 1회(dedup)
# ─────────────────────────────────────────────
def test_cache_hit_dedups_admin_query_within_request():
    """admin-only 인증 후 _is_institution_admin 이 캐시 재사용 → 추가 DB 쿼리 0."""
    # fetchone: ① _authenticate 메인쿼리 ② _has_admin_roster(존재→(1,))
    with _run_authenticate([_main_row(role="admin", subject_code=None, inst="CNU"), (1,)]) as (err, g, cur):
        assert err is None                                   # 인증 통과(admin-only 면제)
        assert g._admin_roster_cache == ("5", "CNU", True)   # 캐시 적재됨
        n_before = cur.execute.call_count                    # = 2 (메인 + has_admin)
        # 같은 요청에서 포털 게이트가 동일 사실을 다시 묻는다 → 캐시 hit, execute 증가 없음
        assert sr._is_institution_admin("5", "CNU") is True
        assert cur.execute.call_count == n_before            # 재조회 없음(중복 제거)


# ─────────────────────────────────────────────
# 2. 캐시 miss 폴백 — 정상 판정 유지
# ─────────────────────────────────────────────
def test_cache_miss_other_institution_falls_back_to_query():
    """캐시는 본인 기관(CNU)인데 다른 기관(SNU) 인자로 호출 → 폴백 쿼리로 정상 판정."""
    conn, cur = _mk_conn(fetchone=[(1,)])    # 폴백 쿼리 결과: admin 행 존재
    with app.test_request_context('/'):
        from flask import g
        g.user_id = "5"
        g.institution_id = "CNU"
        g._admin_roster_cache = ("5", "CNU", True)
        with patch("server_render.get_db_conn", return_value=conn), \
             patch("server_render.release_db_conn"):
            assert sr._is_institution_admin("5", "SNU") is True   # 다른 기관 → 폴백
            assert cur.execute.called                              # 실제 쿼리 수행


def test_cache_miss_other_user_falls_back_to_query():
    """캐시 user(5)와 다른 user(9) 인자 → 폴백 쿼리(캐시 오용 방지)."""
    conn, cur = _mk_conn(fetchone=[None])    # 폴백: admin 행 없음 → False
    with app.test_request_context('/'):
        from flask import g
        g.user_id = "5"
        g.institution_id = "CNU"
        g._admin_roster_cache = ("5", "CNU", True)
        with patch("server_render.get_db_conn", return_value=conn), \
             patch("server_render.release_db_conn"):
            assert sr._is_institution_admin("9", "CNU") is False
            assert cur.execute.called


def test_no_cache_falls_back_to_query():
    """g 에 캐시가 없으면(일반 경로) 기존대로 쿼리해서 판정."""
    conn, cur = _mk_conn(fetchone=[(1,)])
    with app.test_request_context('/'):
        from flask import g
        g.user_id = "5"
        g.institution_id = "CNU"
        assert not hasattr(g, "_admin_roster_cache")
        with patch("server_render.get_db_conn", return_value=conn), \
             patch("server_render.release_db_conn"):
            assert sr._is_institution_admin("5", "CNU") is True
            assert cur.execute.called


# ─────────────────────────────────────────────
# 3. ★ 의미 불변 — 면제 통과 / 회수 시 차단(회수 즉시 반영)
# ─────────────────────────────────────────────
def test_admin_only_exemption_unchanged_pass():
    """admin-only(subject_code NULL) + __ADMIN__ 행 존재 → 구독 없어도(sub_end=None) 인증 통과."""
    with _run_authenticate([_main_row(role="admin", subject_code=None, sub_end=None), (1,)]) as (err, g, _cur):
        assert err is None                       # 구독 만료 면제(기존과 동일)
        assert g.role == "admin"
        assert g._admin_roster_cache[2] is True


def test_admin_roster_revoked_blocks_like_normal_user():
    """__ADMIN__ roster 회수(_has_admin_roster=None) → 면제 사라져 SUBSCRIPTION_EXPIRED 차단."""
    # 메인쿼리 admin-only + 구독 없음(sub_end=None), has_admin 조회 결과 None(회수)
    with _run_authenticate([_main_row(role="admin", subject_code=None, sub_end=None), None]) as (err, g, _cur):
        assert err is not None and err[0] == "SUBSCRIPTION_EXPIRED"   # 일반 사용자처럼 차단
        assert g._admin_roster_cache == ("5", "CNU", False)          # 캐시가 회수를 가리지 않음(False 적재)


def test_authenticate_return_shape_unchanged():
    """§13-2: 성공=None, 실패=(코드,메시지) 2-튜플 shape 불변."""
    # 성공 케이스
    with _run_authenticate([_main_row(role="admin", subject_code=None), (1,)]) as (err_ok, _g, _c):
        assert err_ok is None
    # 실패 케이스(회수)
    with _run_authenticate([_main_row(role="admin", subject_code=None, sub_end=None), None]) as (err_bad, _g2, _c2):
        assert isinstance(err_bad, tuple) and len(err_bad) == 2
        assert err_bad[0] == "SUBSCRIPTION_EXPIRED"


# ─────────────────────────────────────────────
# 4. 누수 방지 — 캐시는 요청 스코프(g) 한정
# ─────────────────────────────────────────────
def test_cache_does_not_leak_across_requests():
    """앞 요청에서 적재한 캐시가 다음 요청에는 보이지 않는다(g 요청 스코프)."""
    # 요청 A: admin-only 인증 → 캐시 적재 (with 종료 시 컨텍스트 pop)
    with _run_authenticate([_main_row(role="admin", subject_code=None), (1,)], sub="5") as (errA, gA, _cA):
        assert errA is None and gA._admin_roster_cache == ("5", "CNU", True)
    # 요청 B(새 컨텍스트): g 는 새로 시작 — 이전 캐시 없음 → 재조회 경로
    conn, cur = _mk_conn(fetchone=[None])   # B의 user 는 admin 행 없음(폴백 시 False)
    with app.test_request_context('/'):
        from flask import g as gB
        gB.user_id = "9"
        gB.institution_id = "SNU"
        assert not hasattr(gB, "_admin_roster_cache")   # 누수 없음(새 요청은 깨끗)
        with patch("server_render.get_db_conn", return_value=conn), \
             patch("server_render.release_db_conn"):
            # 앞 요청 user5/CNU 캐시가 쓰이지 않고 실제 쿼리로 판정
            assert sr._is_institution_admin("9", "SNU") is False
            assert cur.execute.called
