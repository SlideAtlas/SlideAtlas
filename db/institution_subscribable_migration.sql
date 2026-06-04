-- db/institution_subscribable_migration.sql
-- institutions에 is_subscribable(가입 드롭다운 노출 여부) 컬럼 추가 — §18 D18 (출시 전 필수)
-- 멱등(IF NOT EXISTS)·트랜잭션(BEGIN/COMMIT). 실행은 CEO가 EC2 Instance Connect에서 직접 (§12·§20).
--
-- 배경(§6-1·§18 D18):
--   institutions 테이블에 구독 고객 학교 + 콘텐츠 소유자(SA) + 공급사·미판매 파트너(Mahidol 등)가
--   혼재한다. 공개 엔드포인트 GET /api/institutions가 셋을 모두 가입 드롭다운에 노출하므로,
--   is_subscribable 플래그로 가입 가능한 '고객 학교'만 노출하도록 한정한다.
--   (v1.5에서 suppliers 테이블 분리 + slides.license_source FK화로 구조 정리 — 본 마이그레이션은 출시 전 최소 조치.)
--
-- ★ 데이터 판단(어느 기관을 FALSE로 둘지)은 본 마이그레이션에 넣지 않는다.
--   DEFAULT TRUE로 추가만 하고, SA·공급사·Mahidol 등 비고객 기관의 FALSE 처리는
--   CEO가 라이브 데이터를 확인하며 별도 UPDATE로 수행한다(아래 예시 참고, 실제 id는 데이터로 확정).
--     예) UPDATE institutions SET is_subscribable = FALSE WHERE id IN ('SA', ...);

BEGIN;

ALTER TABLE institutions
  ADD COLUMN IF NOT EXISTS is_subscribable BOOLEAN DEFAULT TRUE;

COMMENT ON COLUMN institutions.is_subscribable IS
  '가입 드롭다운 노출 여부. 고객 학교 TRUE, 콘텐츠 소유자(SA)·공급사·미판매 파트너 FALSE.';

COMMIT;
