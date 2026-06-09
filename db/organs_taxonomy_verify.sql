-- db/organs_taxonomy_verify.sql
-- organs_taxonomy_migration.sql 실행 후 검증용. psql에서 \i 또는 -f로 실행.
-- (읽기 전용 — 쓰기 없음. §12)

-- [1] organs 테이블이 실제로 생성됐는지 (1행 반환 = 성공)
SELECT table_name
FROM information_schema.tables
WHERE table_name = 'organs';

-- [2] organs 컬럼 구조 확인 (organ_code PK / name_ko NOT NULL / organ_system 등)
SELECT column_name, data_type, character_maximum_length, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'organs'
ORDER BY ordinal_position;

-- [3] slides.organ_code 컬럼이 추가됐는지 + FK 확인 (1행 반환 = 성공)
SELECT column_name, data_type, character_maximum_length, is_nullable
FROM information_schema.columns
WHERE table_name = 'slides' AND column_name = 'organ_code';

-- [4] slides.organ_code → organs(organ_code) FK 제약 존재 확인
SELECT tc.constraint_name, kcu.column_name, ccu.table_name AS ref_table, ccu.column_name AS ref_column
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage ccu
  ON tc.constraint_name = ccu.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_name = 'slides'
  AND kcu.column_name = 'organ_code';

-- [5] 시드 적재 수 (스타터 세트 기준 46건 — CEO 추가 시 증가)
SELECT COUNT(*) AS organ_count FROM organs;

-- [6] 계통별 organ 분포 (계통 누락/오타 점검)
SELECT organ_system, COUNT(*) AS cnt
FROM organs
GROUP BY organ_system
ORDER BY MIN(display_order);

-- [7] ★ 미매핑 잔량 — organ 자유텍스트는 있으나 organ_code 가 NULL인 행
--     (불가분 자유텍스트는 NULL 유지가 정상. 138종 적재 후 이 값이 0 에 수렴해야 함.)
SELECT COUNT(*) AS unmapped_slides
FROM slides
WHERE organ IS NOT NULL AND organ_code IS NULL;

-- [8] 미매핑 실제 organ 값 목록 (백필/시드 보강 대상 식별용)
SELECT organ, COUNT(*) AS cnt
FROM slides
WHERE organ IS NOT NULL AND organ_code IS NULL
GROUP BY organ
ORDER BY COUNT(*) DESC;
