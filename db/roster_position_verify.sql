-- db/roster_position_verify.sql
-- roster_position_migration.sql 실행 후 검증용. psql에서 \i 또는 -f로 실행.

-- [1] 컬럼이 실제로 추가됐는지 (1행 반환 = 성공)
SELECT column_name, data_type, character_maximum_length, is_nullable
FROM information_schema.columns
WHERE table_name = 'institution_rosters' AND column_name = 'position';

-- [2] 코멘트 확인
SELECT col_description('institution_rosters'::regclass,
       (SELECT ordinal_position FROM information_schema.columns
        WHERE table_name='institution_rosters' AND column_name='position')) AS position_comment;

-- [3] ★ 기존 roster 행의 position 백필 필요 여부 점검
--     subject 행(= __ADMIN__ 아님)인데 position이 NULL인 게 있으면 백필 대상.
--     (이게 NULL이면 그 사용자 가입 시 users.position이 NULL → §21 LMS 권한 분기 깨짐.)
SELECT
  CASE WHEN subject_code = '__ADMIN__' THEN '__ADMIN__(NULL 정상)' ELSE 'subject(NULL이면 백필 필요)' END AS row_kind,
  position,
  COUNT(*) AS cnt
FROM institution_rosters
GROUP BY row_kind, position
ORDER BY row_kind, position;

-- [3-요약] 백필이 필요한 subject 행 개수 (0이면 OK)
SELECT COUNT(*) AS subject_rows_missing_position
FROM institution_rosters
WHERE subject_code <> '__ADMIN__' AND position IS NULL;
