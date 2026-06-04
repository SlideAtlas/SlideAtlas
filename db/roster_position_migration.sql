-- db/roster_position_migration.sql
-- institution_rosters에 position(지위) 컬럼 추가 — 2단계 B(가입 모델 재구성) 선행 블로커
-- 멱등(IF NOT EXISTS)·트랜잭션(BEGIN/COMMIT). 실행은 CEO가 EC2 Instance Connect에서 직접 (§12·§20).
--
-- 모델(v3.3, CEO 확정):
--   · position의 단일 출처 = 과목(subject) roster 행. (겸직 우선순위 규칙 없음)
--   · subject 행:    position ∈ {교수, 조교, 학생}  (이용자 명단 xlsx '지위' 열에서 적재)
--   · __ADMIN__ 행:  position = NULL  (운영 전용 계정, 좌석 0·콘텐츠 비소비)
--   · 행정직원 = subject 행 없는 admin-only 계정으로 표현 → position NULL
--   · 가입(register) 트랙1이 subject 행의 position을 캡처해 users.position에 복사(§6-4).

BEGIN;

ALTER TABLE institution_rosters
  ADD COLUMN IF NOT EXISTS position VARCHAR(20);

COMMENT ON COLUMN institution_rosters.position IS
  '지위(교수/조교/학생). subject 행에만 채움. __ADMIN__ 행은 NULL. 가입 시 users.position의 출처(§6-4 트랙1).';

COMMIT;
