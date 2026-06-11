-- ============================================================================
-- portal_perf_indexes.sql — 포털 명단/인증 경로 성능 인덱스 (단계1)
-- ----------------------------------------------------------------------------
-- 목적:
--   GET /portal/api/roster 단일 요청이 RDS 다왕복(인증+포털게이트+명단)을 도는데,
--   1순위 병목이 (a) lower(email) 함수형 조인이 인덱스를 못 타고(평문 email 인덱스만 존재)
--   매번 seq scan + hash join 으로 돌고, (b) _authenticate 의 구독 만료 상관 서브쿼리가
--   (institution_id, subject_code, status) 복합 인덱스 없이 도는 것이다.
--   본 파일은 그 두 경로가 인덱스를 타도록 '인덱스만' 추가한다.
--
-- 각 인덱스가 줄이는 쿼리:
--   1) idx_users_lower_email
--        · _is_institution_admin (server_render.py): JOIN users u ON lower(u.email)=lower(r.email)
--        · _has_admin_roster     (auth/decorators.py): 동일 lower(email) 조인
--        · _sync_member / 포털 명단 동기화 등 lower(email) 매칭 경로
--   2) idx_rosters_lower_email
--        · 위 조인의 institution_rosters 쪽 lower(email) — 양쪽이 함수형 인덱스를 타야 조인이 인덱스화
--   3) idx_sub_inst_subj_status
--        · _authenticate 의 구독 만료 상관 서브쿼리
--            (SELECT MAX(subscription_end) FROM subscriptions
--               WHERE institution_id=? AND subject_code=? AND status='active'
--                 AND access_open_date<=? AND subscription_end>=?)
--          (부차적이나 매 요청 평가되므로 같이 커버)
--
-- 적용:
--   · ★ 실행은 CEO 가 EC2 → RDS psql 로 직접 한다(§12·§20). AI/앱은 RDS 변경 금지.
--   · CREATE INDEX 잠금은 짧으나(테이블 짧은 ACCESS SHARE 경합) 운영 중 실행 시 주의.
--     무중단이 필요하면 CONCURRENTLY 를 고려하되 — CONCURRENTLY 는 트랜잭션 블록 안에서
--     실행할 수 없으므로 본 파일의 BEGIN/COMMIT 와 함께 쓸 수 없다. 짧은 점검창에 일반
--     CREATE INDEX 로 실행하는 것을 기본으로 하고, 무중단 필요 시 아래 'CONCURRENTLY 변형'
--     주석을 참고해 트랜잭션 밖에서 개별 실행한다.
--   · 모두 IF NOT EXISTS — 멱등(재실행 안전). 0건/이미 존재 시 no-op.
--
-- ★ 인덱스만 추가한다. 기존 인덱스/제약/컬럼 DROP·변경 없음.
-- ============================================================================

BEGIN;

-- 1) users(lower(email)) 함수형 인덱스 — admin roster 조인 + lower(email) 매칭 경로
CREATE INDEX IF NOT EXISTS idx_users_lower_email
    ON users (lower(email));

-- 2) institution_rosters(lower(email)) 함수형 인덱스 — 위 조인의 roster 쪽
CREATE INDEX IF NOT EXISTS idx_rosters_lower_email
    ON institution_rosters (lower(email));

-- 3) subscriptions(institution_id, subject_code, status) 복합 인덱스
--    — _authenticate 구독 만료 상관 서브쿼리 커버(부차적)
CREATE INDEX IF NOT EXISTS idx_sub_inst_subj_status
    ON subscriptions (institution_id, subject_code, status);

COMMIT;

-- ----------------------------------------------------------------------------
-- (참고) 무중단이 꼭 필요할 때의 CONCURRENTLY 변형 — 트랜잭션 밖에서 '개별' 실행할 것.
--   BEGIN/COMMIT 없이 한 줄씩:
--     CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_lower_email        ON users (lower(email));
--     CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_rosters_lower_email      ON institution_rosters (lower(email));
--     CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sub_inst_subj_status     ON subscriptions (institution_id, subject_code, status);
--   ※ CONCURRENTLY 는 더 오래 걸리고 실패 시 INVALID 인덱스를 남길 수 있다(REINDEX/DROP 후 재시도).
-- ----------------------------------------------------------------------------
