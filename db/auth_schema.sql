-- SlideAtlas JWT 인증 마이그레이션 (db/schema.sql 이후 실행)
-- 실행 방법 (EC2 Instance Connect 접속 후):
--
--   psql -h slideatlas-db.c94iwikwox6l.ap-northeast-2.rds.amazonaws.com \
--        -U slideatlas_admin -d slideatlas -p 5432 -f db/auth_schema.sql
--
-- 멱등 실행 가능 (IF NOT EXISTS). 실행은 CEO 판단 후 진행.

BEGIN;

-- ─────────────────────────────────────────────
-- users 테이블 컬럼 추가 (기존 rows는 'active' 기본값)
-- ─────────────────────────────────────────────
ALTER TABLE users ADD COLUMN IF NOT EXISTS status     VARCHAR(20) DEFAULT 'active';
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_special BOOLEAN     DEFAULT FALSE;

-- ─────────────────────────────────────────────
-- 기관 명단 화이트리스트 (users와 별개)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS institution_rosters (
  id              SERIAL       PRIMARY KEY,
  institution_id  VARCHAR(20)  REFERENCES institutions(id) ON DELETE CASCADE,
  email           VARCHAR(200) NOT NULL,
  name            VARCHAR(100),
  role            VARCHAR(20)  NOT NULL DEFAULT 'student',  -- 'student', 'professor', 'ta'
  is_verified     BOOLEAN      DEFAULT FALSE,
  added_at        TIMESTAMP    DEFAULT NOW(),
  UNIQUE(institution_id, email)
);

-- ─────────────────────────────────────────────
-- 이메일 인증코드
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS email_verifications (
  id            SERIAL      PRIMARY KEY,
  user_id       INT         REFERENCES users(id) ON DELETE CASCADE,
  code          VARCHAR(6)  NOT NULL,
  created_at    TIMESTAMP   DEFAULT NOW(),
  expires_at    TIMESTAMP   NOT NULL,
  consumed      BOOLEAN     DEFAULT FALSE,
  attempt_count INT         DEFAULT 0
);

-- ─────────────────────────────────────────────
-- 인덱스
-- ─────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_institution_rosters_email ON institution_rosters(email);
CREATE INDEX IF NOT EXISTS idx_email_verifications_user_id ON email_verifications(user_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_session_token ON users(session_token);

COMMIT;
