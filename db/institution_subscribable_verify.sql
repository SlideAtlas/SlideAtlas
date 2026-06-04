-- db/institution_subscribable_verify.sql
-- institution_subscribable_migration.sql 실행 후 검증용. psql에서 \i 또는 -f로 실행.

-- [1] 컬럼이 실제로 추가됐는지 (1행 반환 = 성공)
SELECT column_name, data_type, column_default, is_nullable
FROM information_schema.columns
WHERE table_name = 'institutions' AND column_name = 'is_subscribable';

-- [2] 코멘트 확인
SELECT col_description('institutions'::regclass,
       (SELECT ordinal_position FROM information_schema.columns
        WHERE table_name='institutions' AND column_name='is_subscribable')) AS is_subscribable_comment;

-- [3] 현재 is_subscribable 분포 (TRUE/FALSE 집계)
--     마이그레이션 직후엔 DEFAULT TRUE라 전부 TRUE. CEO가 비고객 기관을 FALSE 처리한 뒤 다시 확인.
SELECT is_subscribable, COUNT(*) AS cnt
FROM institutions
GROUP BY is_subscribable
ORDER BY is_subscribable;

-- [4] 기관별 노출 여부 — 가입 드롭다운에 무엇이 보일지 직접 점검(고객 학교만 TRUE여야 함)
--     SA·공급사·Mahidol 등 비고객이 TRUE로 남아 있으면 FALSE 처리 대상.
SELECT id, name_ko, is_subscribable
FROM institutions
ORDER BY is_subscribable DESC, name_ko;
