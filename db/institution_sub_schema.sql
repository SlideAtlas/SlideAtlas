-- SlideAtlas S5-2 기관 구독 스키마
-- 실행: EC2 Instance Connect 접속 후
--   psql -h slideatlas-db.c94iwikwox6l.ap-northeast-2.rds.amazonaws.com \
--        -U slideatlas_admin -d slideatlas -p 5432 -f db/institution_sub_schema.sql
-- 멱등 실행 가능 (IF NOT EXISTS / DO $$). 실행은 CEO 승인 후.

BEGIN;

-- 기관 관리자 연락처 (JSONB, 최대 5명)
ALTER TABLE institutions ADD COLUMN IF NOT EXISTS admin_contacts JSONB DEFAULT '[]';

-- 구독: 기관 × 과목 단위
CREATE TABLE IF NOT EXISTS subscriptions (
  id               SERIAL       PRIMARY KEY,
  institution_id   VARCHAR(20)  NOT NULL REFERENCES institutions(id) ON DELETE RESTRICT,
  subject_code     VARCHAR(10)  NOT NULL REFERENCES subject_codes(code),
  plan             VARCHAR(20)  NOT NULL,  -- 'department'|'standard'|'campus'|'institution'|'custom'
  max_seats        INT          NOT NULL,
  start_term       VARCHAR(10)  NOT NULL,  -- '2026-fall' | '2027-spring'
  term_count       INT          NOT NULL DEFAULT 1,
  access_open_date DATE         NOT NULL,
  subscription_end DATE         NOT NULL,
  fee              INT,
  payment_method   VARCHAR(20)  DEFAULT '학기 선불',
  status           VARCHAR(20)  NOT NULL DEFAULT 'active',
  created_at       TIMESTAMP    DEFAULT NOW(),
  UNIQUE(institution_id, subject_code, start_term)
);

CREATE INDEX IF NOT EXISTS idx_sub_inst    ON subscriptions(institution_id);
CREATE INDEX IF NOT EXISTS idx_sub_end     ON subscriptions(subscription_end);

-- 구독 갱신·변경 이력
CREATE TABLE IF NOT EXISTS subscription_history (
  id              SERIAL      PRIMARY KEY,
  subscription_id INT         NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
  event           VARCHAR(20) NOT NULL,  -- 'initial'|'renewal'|'change'
  plan            VARCHAR(20),
  max_seats       INT,
  start_term      VARCHAR(10),
  term_count      INT,
  fee             INT,
  note            TEXT,
  created_by      INT         REFERENCES admin_users(id),
  created_at      TIMESTAMP   DEFAULT NOW()
);

-- 콘텐츠 접근권: 기관 × 과목 (좌석 플랜과 직교)
CREATE TABLE IF NOT EXISTS institution_subject_access (
  institution_id VARCHAR(20) NOT NULL REFERENCES institutions(id) ON DELETE CASCADE,
  subject_code   VARCHAR(10) NOT NULL REFERENCES subject_codes(code),
  granted        BOOLEAN     NOT NULL DEFAULT TRUE,
  PRIMARY KEY (institution_id, subject_code)
);

COMMIT;
