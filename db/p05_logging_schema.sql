-- SlideAtlas P0.5 로깅 스키마 — 이용 리포트 데이터 소스(access_logs) 과목 축 보강
-- 실행: EC2 Instance Connect 접속 후
--   psql -h slideatlas-db.c94iwikwox6l.ap-northeast-2.rds.amazonaws.com \
--        -U slideatlas_admin -d slideatlas -p 5432 -f db/p05_logging_schema.sql
-- 멱등 실행 가능 (ADD COLUMN IF NOT EXISTS). 실행은 CEO 승인 후(§12 — 코드 작업자 RDS 직접 변경 금지).
--
-- 목적:
--   뷰어 진입 열람 로그(access_logs)에 과목 축(subject_code) 기록 컬럼 추가(§15-7 과목별 집계).
--   institution_id는 reports_special_schema.sql에서도 추가하나, 본 스크립트 단독 실행만으로도
--   이용 리포트 집계에 필요한 컬럼이 모두 보장되도록 함께 멱등 추가한다.
--   (chat_logs는 reports_special_schema.sql에 subject_code 포함 — 추가 변경 없음.)

BEGIN;

ALTER TABLE access_logs ADD COLUMN IF NOT EXISTS institution_id VARCHAR(20);
ALTER TABLE access_logs ADD COLUMN IF NOT EXISTS subject_code   VARCHAR(10);

CREATE INDEX IF NOT EXISTS idx_access_logs_institution ON access_logs(institution_id);
CREATE INDEX IF NOT EXISTS idx_access_logs_subject     ON access_logs(subject_code);

COMMIT;
