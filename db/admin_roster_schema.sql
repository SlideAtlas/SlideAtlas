-- SlideAtlas 기관 관리자 명단(roster) 스키마 — §9 기관 관리자 포털 / §18 D12·D15
-- 실행: EC2 Instance Connect 접속 후
--   psql -h slideatlas-db.c94iwikwox6l.ap-northeast-2.rds.amazonaws.com \
--        -U slideatlas_admin -d slideatlas -p 5432 -f db/admin_roster_schema.sql
-- 멱등 실행 가능. 실행은 CEO 승인 후(§12 — 코드 작업자는 RDS 직접 변경 금지).
--
-- 목적:
--   ① institution_rosters.position(관리자 지위, 표시용) 컬럼 추가 — role(시스템 권한)과 별개.
--   ② institution_rosters.subject_code 컬럼 보장 — register()가 참조(기존 배포 정합성 보정).
--   ③ UNIQUE 키를 (institution_id, subject_code, email)로 정식화(D12) —
--      같은 이메일이 관리자 행(subject_code='__ADMIN__')과 과목 행('HST' 등)으로
--      충돌 없이 공존하기 위함(§9).
--
-- ⚠ 실행 전 점검: 신 UNIQUE 위반 가능성(동일 institution_id+subject_code+email 중복행) 0건 확인.
--   SELECT institution_id, subject_code, email, COUNT(*)
--     FROM institution_rosters GROUP BY 1,2,3 HAVING COUNT(*) > 1;

BEGIN;

-- ① 관리자 지위(표시용). 권한과 무관: 조교여도 포털 접근 가능(role='admin'이 결정).
ALTER TABLE institution_rosters ADD COLUMN IF NOT EXISTS position VARCHAR(50);

-- ② 과목 축 컬럼 보장(관리자 행은 센티넬 '__ADMIN__').
ALTER TABLE institution_rosters ADD COLUMN IF NOT EXISTS subject_code VARCHAR(10);

-- ③ UNIQUE 키 정식화: (institution_id, email) → (institution_id, subject_code, email).
DO $$
BEGIN
  -- 구 제약(자동 명명 규칙: <table>_<cols>_key) 존재 시 제거.
  IF EXISTS (
    SELECT 1 FROM pg_constraint
     WHERE conname = 'institution_rosters_institution_id_email_key'
  ) THEN
    ALTER TABLE institution_rosters
      DROP CONSTRAINT institution_rosters_institution_id_email_key;
  END IF;

  -- 신 제약 부재 시 추가.
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
     WHERE conname = 'institution_rosters_inst_subj_email_key'
  ) THEN
    ALTER TABLE institution_rosters
      ADD CONSTRAINT institution_rosters_inst_subj_email_key
      UNIQUE (institution_id, subject_code, email);
  END IF;
END $$;

COMMIT;
