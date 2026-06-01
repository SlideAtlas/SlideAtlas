-- SlideAtlas 어드민 계정 보안 강화 스키마 — 외부검증(Codex#2 / Gemini#1·#4) 반영
-- 실행 방법 (EC2 Instance Connect 접속 후):
--
--   psql -h slideatlas-db.c94iwikwox6l.ap-northeast-2.rds.amazonaws.com \
--        -U slideatlas_admin -d slideatlas -p 5432 -f db/admin_security_schema.sql
--
-- 멱등 실행 가능 (ADD COLUMN IF NOT EXISTS). DROP·기존 컬럼 변경 없음.
-- 실행은 CEO 승인 후. ⚠ 이 마이그레이션은 신 코드 병합·배포 전에 실행돼야 한다
--   (신 코드가 admin_users.session_token 등을 SELECT하므로 — 기존 auth_schema.sql 패턴 동일).
--
-- 목적:
--   ① session_token        : 어드민 세션도 매 요청 DB 대조(탈취·재로그인 시 즉시 무효화, Codex#2).
--   ② failed_attempts      : 어드민 로그인 무차별 대입 차단 카운터 (Gemini#1 Critical).
--   ③ failed_window_start  : 카운팅 윈도우 시작 시각(24h).
--   ④ locked_at            : 잠금 시각 (NULL=미잠금). locked_at + 24h 경과 시 자동 해제.

BEGIN;

ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS session_token       VARCHAR(255);
ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS failed_attempts     INT       DEFAULT 0;
ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS failed_window_start TIMESTAMP NULL;
ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS locked_at           TIMESTAMP NULL;

COMMIT;
