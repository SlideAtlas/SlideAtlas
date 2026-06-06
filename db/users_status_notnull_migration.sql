-- SlideAtlas — users.status NOT NULL 제약 (Codex Med#2 §0 단일판정식 근본 해결)
-- 실행: EC2 Instance Connect 접속 후
--   psql -h slideatlas-db.c94iwikwox6l.ap-northeast-2.rds.amazonaws.com \
--        -U slideatlas_admin -d slideatlas -p 5432 -f db/users_status_notnull_migration.sql
-- 멱등·트랜잭션. 실행은 CEO 승인 후(§12 — 코드 작업자 RDS 직접 변경 금지).
--
-- 배경(§0 단일판정식):
--   '활성 사용자'는 active_seat_count(auth/auth.py)가 status='active'(NULL 제외)로 센다.
--   리포트(P3)·좌석(P2)이 같은 기준을 쓰려면 status 가 NULL 이면 안 된다(NULL=활성 오판 위험).
--   앱 레이어는 이미 status='active' 로 통일(COALESCE 제거, server_render.py P3) 했고,
--   본 마이그레이션은 DB 차원에서 NULL 유입을 영구 차단해 단일판정식을 보장한다.
--
-- 동작:
--   1) 기존 NULL status 행을 'pending_verification'(가입 기본값)으로 백필.
--   2) 컬럼 DEFAULT 를 'pending_verification' 로 (재)설정.
--   3) NOT NULL 제약 부여.
--   (이미 NOT NULL 이면 3)은 무변경 — SET NOT NULL 은 멱등.)

BEGIN;

-- 1) NULL 백필 (가입 직후 기본 상태로 간주)
UPDATE users SET status = 'pending_verification' WHERE status IS NULL;

-- 2) DEFAULT 재설정(스키마 정의와 일치 보장)
ALTER TABLE users ALTER COLUMN status SET DEFAULT 'pending_verification';

-- 3) NOT NULL 제약 (멱등 — 이미 NOT NULL 이어도 안전)
ALTER TABLE users ALTER COLUMN status SET NOT NULL;

COMMIT;

-- 검증(실행 후 0건이어야 정상):
--   SELECT COUNT(*) FROM users WHERE status IS NULL;
