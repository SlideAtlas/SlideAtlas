-- =====================================================================
-- organs_taxonomy_migration.sql
-- organ 통제어휘 정규화 (§18 D28) — v1.5 HST↔PATH normal-abnormal 연동 앵커(§2·§7)
--
-- ⚠ RDS 적용은 CEO가 EC2 Instance Connect에서 직접 실행한다. 실행 전 백업/확인 필수.
--   (RDS는 VPC 프라이빗 — 외부/로컬 접속 불가, EC2 Instance Connect만 가능. §12·§19·§20)
-- ⚠ 코드 작업자(Claude Code 등)는 이 파일을 작성만 한다. 실행 금지(§12).
--
-- 실행: EC2 Instance Connect 접속 후
--   psql -h slideatlas-db.c94iwikwox6l.ap-northeast-2.rds.amazonaws.com \
--        -U slideatlas_admin -d slideatlas -p 5432 -f db/organs_taxonomy_migration.sql
--   실행 후 검증: -f db/organs_taxonomy_verify.sql
--
-- 멱등(IF NOT EXISTS / ON CONFLICT DO NOTHING) + 트랜잭션(BEGIN/COMMIT). 중간 에러 전면 ROLLBACK(§12-4).
--
-- 배경(§2·§7·§18 D28):
--   v1.5 normal-abnormal 연동은 '같은 장기, 다른 상태'가 본질 → 연결 앵커 = organ.
--   따라서 v1.0에서 organ 을 자유텍스트가 아닌 통제어휘(organs 참조 테이블 + slides.organ_code)로
--   정규화한다. 138종 HST 를 정규 organ_code 로 적재하기 위한 어휘 마스터를 깐다.
--
-- 동작:
--   1) organs 마스터 테이블 생성(멱등).
--   2) 표준 조직학 장기 스타터 시드 INSERT(계통별, organ_code=영문 스네이크). ON CONFLICT DO NOTHING.
--   3) slides.organ_code 컬럼 추가(nullable, organs FK). 기존 organ 자유텍스트는 표시/대조용 유지(v1.5 정리).
--   4) 기존 행 백필: 확실히 매핑되는 organ 자유텍스트만 organ_code 채움. 불가분은 NULL 유지(임의 매핑 금지).
--
-- 범위 외(이번 마이그레이션 불포함, v1.5 D29):
--   subject_codes.is_active 추가 안 함 / slide_links 테이블 안 만듦 / 배치 xlsx 메타 적재 안 만듦.
-- =====================================================================

BEGIN;

-- ── 1. organs 마스터 테이블 (멱등) ───────────────────────────────────
-- ★ 계통 컬럼명은 organ_system — 코드 전반의 'organ AS system' 별칭(slides.organ→프론트 key 'system')과
--   충돌을 피하기 위함. organs.organ_system(소화기/순환기 등)과 slides 표시용 system 은 별개 축.
CREATE TABLE IF NOT EXISTS organs (
  organ_code    VARCHAR(20)  PRIMARY KEY,   -- 영문 스네이크 (esophagus, lymph_node …)
  name_ko       VARCHAR(100) NOT NULL,      -- 한국어 표시명 (식도, 림프절 …)
  name_en       VARCHAR(100),               -- 영문 표시명
  organ_system  VARCHAR(40),                -- 계통 (소화기/순환기/호흡기 …)
  display_order INT          DEFAULT 0,     -- 드롭다운 정렬
  is_active     BOOLEAN      DEFAULT TRUE,   -- 비활성 organ 숨김
  created_at    TIMESTAMP    DEFAULT NOW()
);

-- ── 2. 표준 조직학 장기 스타터 시드 (계통별) ─────────────────────────
-- ★ 출발점 — CEO 가 138종 실제 목록과 대조·확정. 추가 organ 은 단순 INSERT(마이그레이션 재실행 불요).
INSERT INTO organs (organ_code, name_ko, name_en, organ_system, display_order) VALUES
  -- 소화기
  ('esophagus',        '식도',      'Esophagus',         '소화기',   10),
  ('stomach',          '위',        'Stomach',           '소화기',   20),
  ('duodenum',         '십이지장',  'Duodenum',          '소화기',   30),
  ('jejunum',          '공장(소장)','Jejunum',           '소화기',   40),
  ('ileum',            '회장(소장)','Ileum',             '소화기',   50),
  ('colon',            '대장',      'Colon',             '소화기',   60),
  ('liver',            '간',        'Liver',             '소화기',   70),
  ('pancreas',         '췌장',      'Pancreas',          '소화기',   80),
  ('gallbladder',      '담낭',      'Gallbladder',       '소화기',   90),
  ('salivary_gland',   '침샘',      'Salivary gland',    '소화기',  100),
  ('tongue',           '혀',        'Tongue',            '소화기',  110),
  -- 순환기
  ('heart',            '심장',      'Heart',             '순환기',  200),
  ('artery',           '동맥',      'Artery',            '순환기',  210),
  ('vein',             '정맥',      'Vein',              '순환기',  220),
  -- 호흡기
  ('trachea',          '기관',      'Trachea',           '호흡기',  300),
  ('lung',             '폐',        'Lung',              '호흡기',  310),
  -- 비뇨기
  ('kidney',           '신장',      'Kidney',            '비뇨기',  400),
  ('urinary_bladder',  '방광',      'Urinary bladder',   '비뇨기',  410),
  ('ureter',           '요관',      'Ureter',            '비뇨기',  420),
  -- 생식기
  ('testis',           '고환',      'Testis',            '생식기',  500),
  ('epididymis',       '부고환',    'Epididymis',        '생식기',  510),
  ('ovary',            '난소',      'Ovary',             '생식기',  520),
  ('uterus',           '자궁',      'Uterus',            '생식기',  530),
  ('uterine_tube',     '자궁관',    'Uterine tube',      '생식기',  540),
  ('prostate',         '전립선',    'Prostate',          '생식기',  550),
  -- 내분비
  ('thyroid',          '갑상선',    'Thyroid',           '내분비',  600),
  ('parathyroid',      '부갑상선',  'Parathyroid',       '내분비',  610),
  ('adrenal_gland',    '부신',      'Adrenal gland',     '내분비',  620),
  ('pituitary',        '뇌하수체',  'Pituitary',         '내분비',  630),
  -- 림프면역
  ('lymph_node',       '림프절',    'Lymph node',        '림프면역', 700),
  ('spleen',           '비장',      'Spleen',            '림프면역', 710),
  ('thymus',           '흉선',      'Thymus',            '림프면역', 720),
  ('tonsil',           '편도',      'Tonsil',            '림프면역', 730),
  -- 조혈
  ('bone_marrow',      '골수',      'Bone marrow',       '조혈',    800),
  -- 신경
  ('cerebrum',         '대뇌',      'Cerebrum',          '신경',    900),
  ('cerebellum',       '소뇌',      'Cerebellum',        '신경',    910),
  ('spinal_cord',      '척수',      'Spinal cord',       '신경',    920),
  ('peripheral_nerve', '말초신경',  'Peripheral nerve',  '신경',    930),
  ('ganglion',         '신경절',    'Ganglion',          '신경',    940),
  -- 피부
  ('skin',             '피부',      'Skin',              '피부',   1000),
  -- 근골격
  ('skeletal_muscle',  '골격근',    'Skeletal muscle',   '근골격',  1100),
  ('smooth_muscle',    '평활근',    'Smooth muscle',     '근골격',  1110),
  ('bone',             '뼈',        'Bone',              '근골격',  1120),
  ('cartilage',        '연골',      'Cartilage',         '근골격',  1130),
  -- 감각기
  ('eye',              '눈',        'Eye',               '감각기',  1200),
  ('ear',              '귀',        'Ear',               '감각기',  1210)
ON CONFLICT (organ_code) DO NOTHING;

-- ── 3. slides.organ_code 컬럼 추가 (nullable, organs FK) ─────────────
ALTER TABLE slides ADD COLUMN IF NOT EXISTS organ_code VARCHAR(20) REFERENCES organs(organ_code);
CREATE INDEX IF NOT EXISTS idx_slides_organ_code ON slides(organ_code);

-- ── 4. 기존 행 백필 (확실히 매핑되는 것만, 임의 매핑 금지) ────────────
--   기존 organ 자유텍스트가 name_ko 또는 organ_code 와 정확히 일치하는 경우에만 채운다.
--   (현 DB 는 D24 잔재 위주라 매핑 거의 없을 수 있음 — 그게 정상. 불가분은 NULL 유지.)
UPDATE slides s
   SET organ_code = o.organ_code
  FROM organs o
 WHERE s.organ_code IS NULL
   AND s.organ IS NOT NULL
   AND ( btrim(s.organ) = o.name_ko
      OR lower(btrim(s.organ)) = o.organ_code
      OR lower(btrim(s.organ)) = lower(o.name_en) );

COMMIT;

-- 검증(실행 후 db/organs_taxonomy_verify.sql 실행 — 아래는 빠른 확인용):
--   SELECT COUNT(*) FROM organs;                                  -- 시드 적재 수
--   SELECT COUNT(*) FROM slides WHERE organ IS NOT NULL AND organ_code IS NULL;  -- 미매핑 잔량
