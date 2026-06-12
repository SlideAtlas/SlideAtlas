-- SlideAtlas — slides.overview_levels 컬럼 추가 (COG 파이프라인 1단계)
--
-- ★ 실행 주체: CEO가 EC2 Instance Connect 접속 후 psql 로 직접 실행(§20 — AI/SSH 실행 금지).
--   psql -h slideatlas-db.c94iwikwox6l.ap-northeast-2.rds.amazonaws.com \
--        -U slideatlas_admin -d slideatlas -p 5432 -f db/slides_overview_levels_migration.sql
--   멱등(IF NOT EXISTS)·트랜잭션. 이 파일은 작성만 됨 — 코드 배포와 별개로 CEO가 실행한다.
--
-- 목적: ConversionResult.overview_levels(생성된 COG 오버뷰 레벨 수)를 전용 컬럼에 보관.
--   타일서버가 매 요청 조회하는 운영 데이터라 conversion_log(자유텍스트)에 묻으면 파싱 비용이
--   발생 → overview_levels 만 conversion_log 합본의 예외로 전용 컬럼화(§4-4 'DZI 레벨 수').
--   (failure_reason 은 사람이 읽는 실패 사유라 conversion_log 합본 유지.)

BEGIN;

-- nullable 로 시작(기존 행은 변환 전이라 NULL — 변환 완료 시 채워짐). 기본값 없음(임의값 금지 정신).
ALTER TABLE slides ADD COLUMN IF NOT EXISTS overview_levels INT;

COMMIT;
