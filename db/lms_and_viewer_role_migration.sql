-- =====================================================================
-- lms_and_viewer_role_migration.sql
-- 교수 수업 페이지(LMS) v1.0 정식 범위 + role 'student'→'viewer' 정정
--
-- ⚠ RDS 적용은 CEO가 EC2 venv에서 직접 실행한다. 실행 전 백업/확인 필수.
--   (RDS는 VPC 프라이빗 — 외부/로컬 접속 불가, EC2 Instance Connect만 가능. §12·§19·§20)
-- ⚠ 코드 작업자(Claude Code 등)는 이 파일을 작성만 한다. 실행 금지(§12).
--
-- 멱등(IF NOT EXISTS) + 트랜잭션(BEGIN/COMMIT). 중간 에러 시 전면 ROLLBACK.
-- 참조: CLAUDE.md §6-4(가입 두 트랙) · §7(스키마) · §8(접근 게이트) · §21(LMS 상세)
-- =====================================================================

BEGIN;

-- ── 1. users.position 컬럼 추가 (교수/조교/학생/행정직원) ──────────────
ALTER TABLE users ADD COLUMN IF NOT EXISTS position VARCHAR(20);

-- ── 2. role 값 정정: 기존 'student' → 'viewer' ───────────────────────
UPDATE users SET role = 'viewer' WHERE role = 'student';
UPDATE institution_rosters SET role = 'viewer' WHERE role = 'student';

-- ── 3. role 기본값을 'viewer'로 변경 ─────────────────────────────────
ALTER TABLE users ALTER COLUMN role SET DEFAULT 'viewer';
ALTER TABLE institution_rosters ALTER COLUMN role SET DEFAULT 'viewer';

-- ── 4. LMS 테이블 6개 (멱등 생성) ────────────────────────────────────
-- 수업(course)은 슬라이드 접근 게이트가 아니라 학습 경로/커리큘럼이다(§8 단일 게이트 유지).

CREATE TABLE IF NOT EXISTS courses (
  id SERIAL PRIMARY KEY,
  institution_id VARCHAR(20) REFERENCES institutions(id),
  subject_code VARCHAR(10) REFERENCES subject_codes(code),
  professor_user_id INT REFERENCES users(id),
  title VARCHAR(200), semester VARCHAR(20),
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS course_weeks (
  id SERIAL PRIMARY KEY,
  course_id INT REFERENCES courses(id) ON DELETE CASCADE,
  week_number INT, title VARCHAR(200), empty_reason TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS course_week_slides (
  id SERIAL PRIMARY KEY,
  course_week_id INT REFERENCES course_weeks(id) ON DELETE CASCADE,
  slide_id VARCHAR(50) REFERENCES slides(id), display_order INT
);

CREATE TABLE IF NOT EXISTS course_assistants (
  course_id INT REFERENCES courses(id) ON DELETE CASCADE,
  user_id INT REFERENCES users(id), PRIMARY KEY (course_id, user_id)
);

CREATE TABLE IF NOT EXISTS course_enrollments (
  course_id INT REFERENCES courses(id) ON DELETE CASCADE,
  user_id INT REFERENCES users(id), enrolled_at TIMESTAMP DEFAULT NOW(),
  PRIMARY KEY (course_id, user_id)
);

CREATE TABLE IF NOT EXISTS favorites (
  user_id INT REFERENCES users(id),
  slide_id VARCHAR(50) REFERENCES slides(id),
  created_at TIMESTAMP DEFAULT NOW(), PRIMARY KEY (user_id, slide_id)
);

COMMIT;

-- =====================================================================
-- 실행 후 확인 (참고용 SELECT — CEO가 EC2에서 직접):
--   SELECT COUNT(*) FROM users WHERE role = 'student';              -- 0 이어야 함
--   SELECT COUNT(*) FROM institution_rosters WHERE role='student';  -- 0 이어야 함
--   \d users   -- position 컬럼·role DEFAULT 'viewer' 확인
--   \dt courses course_weeks course_week_slides course_assistants course_enrollments favorites
-- =====================================================================
