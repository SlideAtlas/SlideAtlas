-- SlideAtlas 슈퍼관리자 계정 스키마 (S5-1)
-- 실행 방법 (EC2 Instance Connect 접속 후):
--
--   psql -h slideatlas-db.c94iwikwox6l.ap-northeast-2.rds.amazonaws.com \
--        -U slideatlas_admin -d slideatlas -p 5432 -f db/admin_schema.sql
--
-- 멱등 실행 가능 (IF NOT EXISTS). 실행은 CEO 승인 후.
-- 학생 users 테이블과 완전 분리된 별도 관리자 계정 체계.

BEGIN;

-- ─────────────────────────────────────────────
-- admin_users  (슈퍼관리자 / 스태프 계정)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS admin_users (
  id            SERIAL       PRIMARY KEY,
  email         VARCHAR(200) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  role          VARCHAR(20)  NOT NULL DEFAULT 'staff',
  -- 'super_admin' : 운영 전체 권한 (기관·슬라이드·접근제어·리포트·특별계정 + 공지·문의)
  -- 'staff'       : 공지 관리 + 1:1 문의 응대만
  name          VARCHAR(100),
  status        VARCHAR(20)  NOT NULL DEFAULT 'active',
  -- 'active' | 'suspended'
  last_login    TIMESTAMP,
  created_by    INT          REFERENCES admin_users(id),
  -- NULL = 최초 슈퍼관리자 (seed_admin.py로 생성)
  -- staff 계정 발급은 super_admin만 가능 (API 레벨에서 super_admin_required로 강제)
  created_at    TIMESTAMP    DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admin_users_email ON admin_users(email);

COMMIT;
