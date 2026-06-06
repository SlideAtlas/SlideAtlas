-- SlideAtlas — 특별계정 subject_code 정리 (Codex 2R#1 §0 좌석 정합)
-- 실행: EC2 Instance Connect 접속 후
--   psql -h slideatlas-db.c94iwikwox6l.ap-northeast-2.rds.amazonaws.com \
--        -U slideatlas_admin -d slideatlas -p 5432 -f db/special_subject_code_cleanup_migration.sql
-- 멱등·트랜잭션. 실행은 CEO 승인 후(§12 — 코드 작업자 RDS 직접 변경 금지).
--
-- 배경(CEO 결정):
--   특별계정(is_special=TRUE)은 좌석을 점유하지 않는다. 그런데 active_seat_count(auth/auth.py)는
--   status='active' AND subject_code=X 로 세므로, 특별계정이 subject_code 를 가진 채 active 면
--   좌석(P2)에 잡히고 P3 active_users 와 어긋난다(§0 위반).
--   승격 코드는 이제 subject_code=NULL(+position NULL)로 정리하지만, '코드 수정 이전에 만들어진
--   기존 특별계정'에 subject_code 가 남아있을 수 있어 본 마이그레이션으로 일괄 정리한다.
--   (작업자는 라이브 RDS 조회 권한이 없어(§12·§20) 잔존 건수 확인 불가 → 멱등 정리로 양쪽 분기 안전 커버.
--    잔존 0건이면 UPDATE 0 rows 로 no-op.)
--
-- 좌석/접근 영향:
--   특별계정 접근은 단일 게이트(_slide_access_allowed)가 is_special 분기로 별도 판정(§15-8)하므로
--   subject_code 를 비워도 특별계정의 슬라이드 열람에는 영향이 없다(좌석 카운트에서만 빠진다).

BEGIN;

UPDATE users
   SET subject_code = NULL,
       position     = NULL
 WHERE COALESCE(is_special, FALSE) = TRUE
   AND subject_code IS NOT NULL;

COMMIT;

-- 검증(실행 후 0건이어야 정상):
--   SELECT COUNT(*) FROM users WHERE COALESCE(is_special,FALSE)=TRUE AND subject_code IS NOT NULL;
