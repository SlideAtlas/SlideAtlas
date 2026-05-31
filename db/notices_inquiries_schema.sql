-- SlideAtlas S5-7/S5-8 공지 관리·1:1 문의 스키마
-- 실행: EC2 Instance Connect 접속 후
--   psql -h slideatlas-db.c94iwikwox6l.ap-northeast-2.rds.amazonaws.com \
--        -U slideatlas_admin -d slideatlas -p 5432 -f db/notices_inquiries_schema.sql
-- 그리고 reports_special_schema.sql 도 아직 미실행이라면 먼저 실행:
--   psql ... -f db/reports_special_schema.sql
-- 멱등 실행 가능 (CREATE TABLE IF NOT EXISTS). 실행은 CEO 승인 후.

BEGIN;

-- ─────────────────────────────────────────────
-- announcements  (랜딩 공지 — 소프트 삭제/보관함)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS announcements (
  id            SERIAL       PRIMARY KEY,
  title         VARCHAR(200) NOT NULL,
  body          TEXT,
  is_published  BOOLEAN      NOT NULL DEFAULT FALSE,
  display_order INT          NOT NULL DEFAULT 0,
  -- 게시 중인 항목의 표시 순서(1~5). 숨김 항목은 0.
  is_archived   BOOLEAN      NOT NULL DEFAULT FALSE,
  -- TRUE = 소프트 삭제(보관함). 랜딩·관리 active 목록에서 제외.
  archived_at   TIMESTAMP,
  created_by    INT          REFERENCES admin_users(id),
  updated_by    INT          REFERENCES admin_users(id),
  created_at    TIMESTAMP    DEFAULT NOW(),
  updated_at    TIMESTAMP    DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ann_active
    ON announcements(is_published, is_archived, display_order);

-- ─────────────────────────────────────────────
-- inquiries  (어드민 1:1 문의 — 로그인 사용자 → 어드민)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS inquiries (
  id             SERIAL       PRIMARY KEY,
  user_id        INT          REFERENCES users(id) ON DELETE SET NULL,
  institution_id VARCHAR(20)  REFERENCES institutions(id) ON DELETE SET NULL,
  title          VARCHAR(200),
  body           TEXT,
  user_email     VARCHAR(200),   -- 접수 시 캡처 (탈퇴 후에도 이메일 보존)
  user_name      VARCHAR(100),   -- 접수 시 캡처 (roster 이름)
  status         VARCHAR(20)  NOT NULL DEFAULT 'open',
  -- 'open' | 'answered'
  created_at     TIMESTAMP    DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_inq_status      ON inquiries(status);
CREATE INDEX IF NOT EXISTS idx_inq_institution ON inquiries(institution_id);
CREATE INDEX IF NOT EXISTS idx_inq_created     ON inquiries(created_at);

-- ─────────────────────────────────────────────
-- inquiry_replies  (답변 — SES 발송 기록 포함)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS inquiry_replies (
  id           SERIAL      PRIMARY KEY,
  inquiry_id   INT         NOT NULL REFERENCES inquiries(id) ON DELETE CASCADE,
  body         TEXT        NOT NULL,
  created_by   INT         REFERENCES admin_users(id),
  sent_via_ses BOOLEAN     NOT NULL DEFAULT FALSE,
  created_at   TIMESTAMP   DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reply_inquiry ON inquiry_replies(inquiry_id);

COMMIT;
