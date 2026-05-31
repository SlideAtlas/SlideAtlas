-- SlideAtlas S5-5/S5-6 이용 리포트·특별 계정 스키마
-- 실행: EC2 Instance Connect 접속 후
--   psql -h slideatlas-db.c94iwikwox6l.ap-northeast-2.rds.amazonaws.com \
--        -U slideatlas_admin -d slideatlas -p 5432 -f db/reports_special_schema.sql
-- 멱등 실행 가능 (IF NOT EXISTS / ADD COLUMN IF NOT EXISTS). 실행은 CEO 승인 후.

BEGIN;

-- ─────────────────────────────────────────────
-- users 테이블: 특별 계정 + 과목 축 컬럼 추가
-- ─────────────────────────────────────────────
-- 과목별 좌석 관리용 (institution_id + subject_code 조합으로 좌석 카운터)
ALTER TABLE users ADD COLUMN IF NOT EXISTS subject_code      VARCHAR(10);

-- 특별 계정 필드
ALTER TABLE users ADD COLUMN IF NOT EXISTS special_expires_at  DATE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS special_review_at   DATE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS special_purpose     VARCHAR(50);
-- '자문위원'|'검수자'|'데모'|'공급사 평가'|'기타'

-- 발급 추적
ALTER TABLE users ADD COLUMN IF NOT EXISTS special_created_by  INT REFERENCES admin_users(id);

-- ─────────────────────────────────────────────
-- chat_logs  (AI 튜터 질문 로그 — 이용 리포트용)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_logs (
  id          SERIAL       PRIMARY KEY,
  user_id     INT          REFERENCES users(id) ON DELETE SET NULL,
  institution_id VARCHAR(20),           -- 접수 시 캡처 (users 탈퇴 후에도 집계 유지)
  slide_id    VARCHAR(50),
  tab         VARCHAR(20),              -- 'guide'|'qa'|'quiz'
  subject_code VARCHAR(10),
  created_at  TIMESTAMP    DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_logs_user_id      ON chat_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_logs_institution  ON chat_logs(institution_id);
CREATE INDEX IF NOT EXISTS idx_chat_logs_created_at   ON chat_logs(created_at);

-- ─────────────────────────────────────────────
-- access_logs: institution_id 캡처 컬럼 (집계 최적화)
-- ─────────────────────────────────────────────
ALTER TABLE access_logs ADD COLUMN IF NOT EXISTS institution_id VARCHAR(20);

CREATE INDEX IF NOT EXISTS idx_access_logs_institution ON access_logs(institution_id);

COMMIT;
