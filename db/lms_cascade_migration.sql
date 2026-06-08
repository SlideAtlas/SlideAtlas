-- =====================================================================
-- lms_cascade_migration.sql
-- 수업(course) 계통 FK 4개에 ON DELETE CASCADE 보장 (멱등)
--
-- 【목적】
--   수업(버킷) 삭제 시 그 수업에 딸린 '계통 내부' 자원이 함께 정리되도록
--   아래 4개 FK 를 ON DELETE CASCADE 로 만든다(이미 그렇다면 재생성으로 no-op):
--     · course_weeks.course_id            -> courses(id)
--     · course_week_slides.course_week_id -> course_weeks(id)
--     · course_assistants.course_id       -> courses(id)
--     · course_enrollments.course_id      -> courses(id)
--   효과: DELETE FROM courses ... 시 주차·배치 슬라이드 목록·조교 위임·수강 등록이
--   DB 차원에서 자동 정리(앱의 명시 DELETE 와 정합, 고아행 방지).
--
-- 【★ 의도적 제외 — 절대 CASCADE 추가 금지(이번 범위 밖, 별건 부채)】
--   course 계통은 '바깥 물리 자원'(slides, users)을 가리키는 FK 에 CASCADE 를 걸지 않는다.
--   슬라이드/계정의 영구 삭제 정책은 별도 결정 사항이므로 기본(RESTRICT/NO ACTION) 유지:
--     · course_week_slides.slide_id -> slides(id)    (배치 제거가 슬라이드 원본을 지우면 안 됨)
--     · course_enrollments.user_id  -> users(id)     (수강 정리가 계정을 지우면 안 됨)
--     · course_assistants.user_id   -> users(id)     (위임 정리가 계정을 지우면 안 됨)
--   이 3개 FK 는 본 파일에서 일절 건드리지 않는다.
--
-- 【현행(before) 요약】
--   db/schema.sql 이 course_weeks/course_week_slides/course_assistants 를
--   ON DELETE 절 없이(=NO ACTION) 먼저 생성했고, 라이브 RDS 에 이미 존재해
--   db/lms_and_viewer_role_migration.sql 의 CREATE TABLE IF NOT EXISTS(... ON DELETE CASCADE)
--   가 skip 되었다. 따라서 라이브의 이 3개 FK 는 비-CASCADE 일 가능성이 높다.
--   course_enrollments 는 lms 마이그레이션이 신규 생성(이미 CASCADE)했으나, 마이그레이션
--   적용 여부에 무관하게 본 파일이 멱등으로 CASCADE 를 재보장한다.
--
-- ⚠ RDS 적용은 CEO 가 EC2 psql 에서 직접 수동 실행한다(코드 작업자는 작성만, §12·§19·§20).
--   RDS 는 VPC 프라이빗 — 외부/로컬 접속 불가, EC2 Instance Connect 만 가능.
--
-- 【멱등성】 각 FK 마다 (1) 현재 걸린 동일 (테이블,컬럼→부모) FK 제약을 이름과 무관하게
--   모두 찾아 DROP → (2) 결정적 이름으로 ON DELETE CASCADE FK 재생성. 여러 번 실행해도
--   같은 상태로 수렴(재실행 시 자기가 만든 제약을 DROP 후 동일 재생성 = no-op).
--   대상 테이블이 아직 없으면(to_regclass NULL) 해당 블록은 조용히 skip.
-- 【트랜잭션】 BEGIN/COMMIT 로 감싸 중간 실패 시 전체 ROLLBACK.
-- =====================================================================

BEGIN;

-- ── 1. course_weeks.course_id -> courses(id)  : ON DELETE CASCADE ──────
DO $$
DECLARE r record;
BEGIN
  IF to_regclass('public.course_weeks') IS NULL OR to_regclass('public.courses') IS NULL THEN
    RAISE NOTICE 'skip course_weeks.course_id (table missing)';
  ELSE
    FOR r IN
      SELECT con.conname
        FROM pg_constraint con
        JOIN pg_attribute a
          ON a.attrelid = con.conrelid AND a.attnum = ANY(con.conkey)
       WHERE con.contype = 'f'
         AND con.conrelid = 'public.course_weeks'::regclass
         AND con.confrelid = 'public.courses'::regclass
         AND a.attname = 'course_id'
         AND array_length(con.conkey, 1) = 1
    LOOP
      EXECUTE format('ALTER TABLE public.course_weeks DROP CONSTRAINT %I', r.conname);
    END LOOP;
    ALTER TABLE public.course_weeks DROP CONSTRAINT IF EXISTS course_weeks_course_id_fkey;
    ALTER TABLE public.course_weeks
      ADD CONSTRAINT course_weeks_course_id_fkey
      FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE;
  END IF;
END $$;

-- ── 2. course_week_slides.course_week_id -> course_weeks(id) : CASCADE ──
DO $$
DECLARE r record;
BEGIN
  IF to_regclass('public.course_week_slides') IS NULL OR to_regclass('public.course_weeks') IS NULL THEN
    RAISE NOTICE 'skip course_week_slides.course_week_id (table missing)';
  ELSE
    FOR r IN
      SELECT con.conname
        FROM pg_constraint con
        JOIN pg_attribute a
          ON a.attrelid = con.conrelid AND a.attnum = ANY(con.conkey)
       WHERE con.contype = 'f'
         AND con.conrelid = 'public.course_week_slides'::regclass
         AND con.confrelid = 'public.course_weeks'::regclass
         AND a.attname = 'course_week_id'
         AND array_length(con.conkey, 1) = 1
    LOOP
      EXECUTE format('ALTER TABLE public.course_week_slides DROP CONSTRAINT %I', r.conname);
    END LOOP;
    ALTER TABLE public.course_week_slides DROP CONSTRAINT IF EXISTS course_week_slides_course_week_id_fkey;
    ALTER TABLE public.course_week_slides
      ADD CONSTRAINT course_week_slides_course_week_id_fkey
      FOREIGN KEY (course_week_id) REFERENCES public.course_weeks(id) ON DELETE CASCADE;
  END IF;
END $$;

-- ── 3. course_assistants.course_id -> courses(id) : ON DELETE CASCADE ──
DO $$
DECLARE r record;
BEGIN
  IF to_regclass('public.course_assistants') IS NULL OR to_regclass('public.courses') IS NULL THEN
    RAISE NOTICE 'skip course_assistants.course_id (table missing)';
  ELSE
    FOR r IN
      SELECT con.conname
        FROM pg_constraint con
        JOIN pg_attribute a
          ON a.attrelid = con.conrelid AND a.attnum = ANY(con.conkey)
       WHERE con.contype = 'f'
         AND con.conrelid = 'public.course_assistants'::regclass
         AND con.confrelid = 'public.courses'::regclass
         AND a.attname = 'course_id'
         AND array_length(con.conkey, 1) = 1
    LOOP
      EXECUTE format('ALTER TABLE public.course_assistants DROP CONSTRAINT %I', r.conname);
    END LOOP;
    ALTER TABLE public.course_assistants DROP CONSTRAINT IF EXISTS course_assistants_course_id_fkey;
    ALTER TABLE public.course_assistants
      ADD CONSTRAINT course_assistants_course_id_fkey
      FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE;
  END IF;
END $$;

-- ── 4. course_enrollments.course_id -> courses(id) : ON DELETE CASCADE ──
DO $$
DECLARE r record;
BEGIN
  IF to_regclass('public.course_enrollments') IS NULL OR to_regclass('public.courses') IS NULL THEN
    RAISE NOTICE 'skip course_enrollments.course_id (table missing)';
  ELSE
    FOR r IN
      SELECT con.conname
        FROM pg_constraint con
        JOIN pg_attribute a
          ON a.attrelid = con.conrelid AND a.attnum = ANY(con.conkey)
       WHERE con.contype = 'f'
         AND con.conrelid = 'public.course_enrollments'::regclass
         AND con.confrelid = 'public.courses'::regclass
         AND a.attname = 'course_id'
         AND array_length(con.conkey, 1) = 1
    LOOP
      EXECUTE format('ALTER TABLE public.course_enrollments DROP CONSTRAINT %I', r.conname);
    END LOOP;
    ALTER TABLE public.course_enrollments DROP CONSTRAINT IF EXISTS course_enrollments_course_id_fkey;
    ALTER TABLE public.course_enrollments
      ADD CONSTRAINT course_enrollments_course_id_fkey
      FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE;
  END IF;
END $$;

COMMIT;

-- =====================================================================
-- 적용 (CEO 가 EC2 에서 직접):
--   psql "$DATABASE_URL" -f db/lms_cascade_migration.sql
--   (또는 EC2 Instance Connect 후: psql -h <RDS endpoint> -U slideatlas_admin -d slideatlas -f db/lms_cascade_migration.sql)
--
-- 적용 후 확인 (참고용 — course 계통 4개는 CASCADE 'c', 제외 3개는 NO ACTION 'a'):
--   SELECT con.conname,
--          rel.relname            AS child_table,
--          att.attname            AS fk_column,
--          fr.relname             AS parent_table,
--          con.confdeltype        AS on_delete   -- c=CASCADE, a=NO ACTION, r=RESTRICT
--     FROM pg_constraint con
--     JOIN pg_class rel ON rel.oid = con.conrelid
--     JOIN pg_class fr  ON fr.oid  = con.confrelid
--     JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = ANY(con.conkey)
--    WHERE con.contype = 'f'
--      AND rel.relname IN ('course_weeks','course_week_slides','course_assistants','course_enrollments')
--    ORDER BY rel.relname, att.attname;
--   기대값:
--     course_assistants.course_id        -> courses        : c (CASCADE)
--     course_assistants.user_id          -> users          : a (NO ACTION, 의도적 제외)
--     course_enrollments.course_id       -> courses        : c (CASCADE)
--     course_enrollments.user_id         -> users          : a (NO ACTION, 의도적 제외)
--     course_week_slides.course_week_id  -> course_weeks    : c (CASCADE)
--     course_week_slides.slide_id        -> slides          : a (NO ACTION, 의도적 제외)
--     course_weeks.course_id             -> courses         : c (CASCADE)
-- =====================================================================
