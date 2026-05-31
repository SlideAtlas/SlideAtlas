-- SlideAtlas S5-3 슬라이드 배포 상태 스키마
-- 실행: EC2 Instance Connect 접속 후
--   psql -h slideatlas-db.c94iwikwox6l.ap-northeast-2.rds.amazonaws.com \
--        -U slideatlas_admin -d slideatlas -p 5432 -f db/slides_deploy_schema.sql
-- 멱등 실행 가능 (IF NOT EXISTS). 실행은 CEO 승인 후.

BEGIN;

-- 배포 상태 컬럼 추가 (§15-3 deploy_status)
ALTER TABLE slides ADD COLUMN IF NOT EXISTS deploy_status VARCHAR(20) NOT NULL DEFAULT 'qc_pending';
-- qc_pending | deployed | rejected  (revoked → qc_pending 복귀)

-- 반려 사유 (검수자 보고)
ALTER TABLE slides ADD COLUMN IF NOT EXISTS reject_reason TEXT;

-- 기존 is_public=TRUE 슬라이드를 deployed로 마이그레이션
UPDATE slides SET deploy_status = 'deployed' WHERE is_public = TRUE AND deploy_status = 'qc_pending';

CREATE INDEX IF NOT EXISTS idx_slides_deploy ON slides(deploy_status);
CREATE INDEX IF NOT EXISTS idx_slides_conv   ON slides(conversion_status);

COMMIT;
