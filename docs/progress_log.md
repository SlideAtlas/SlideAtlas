# SlideAtlas 슈퍼관리자 구현 진행 로그

---

## S5-1 — admin_users 2단계 권한 + 어드민 인증 ✅ 완료

**완료일**: 2026-05-30 이전  
**내용**:
- `admin_users` 테이블 RDS 생성 (`db/admin_schema.sql`)
- `boram@atlaslab.co.kr` super_admin 시드 (`db/seed_admin.py`)
- `admin_required` / `super_admin_required` / `admin_csrf_required` 데코레이터 구현
- staff → 운영 API 403, 비로그인 → 401 동작 확인
- 학생 JWT 인증과 완전 분리
- 어드민 로그인·로그아웃·대시보드 라우트 + 템플릿 (`base.html`, `dashboard.html`, `login.html`)

---

## S5-2 — 기관 관리 ✅ 완료

**완료일**: 2026-05-30  
**DB 마이그레이션 실행 결과** (`db/institution_sub_schema.sql`):
```
BEGIN
ALTER TABLE       ← institutions.admin_contacts JSONB 컬럼 추가
CREATE TABLE      ← subscriptions
CREATE INDEX      ← idx_sub_inst
CREATE INDEX      ← idx_sub_end
CREATE TABLE      ← subscription_history
CREATE TABLE      ← institution_subject_access
COMMIT
```
모두 성공. RDS에서 테이블 3개 + 컬럼 1개 확인 완료.

**구현 파일**:
- `db/institution_sub_schema.sql` — 마이그레이션 SQL (멱등)
- `server_render.py` — 기관 관리 라우트 7개 추가 (`/admin/institutions`, `/admin/api/institutions` CRUD + 구독 추가·갱신)
- `templates/admin/institutions.html` — 기관 목록·추가/수정 모달·갱신 모달

**주요 설계**:
- 학기 모델: Python `calendar.monthrange` 윤년 자동 처리 / JS `Date(y,2,0)` 미러
- 구독 상태: 구독중/오픈예정(D-60이내)/대기/만료
- 기관코드: 관리자 수동 입력 (영문·숫자·하이픈), 중복 체크 서버측
- `institution_subject_access` 구독 등록 시 자동 삽입 (ON CONFLICT DO NOTHING)
- `subscription_history` initial/renewal 이벤트 자동 기록
- `institution_rosters` 미존재 시 used_seats=0 폴백 처리

---

## S5-3 — 슬라이드 관리 ✅ 완료

**완료일**: 2026-05-30  
**구현 파일**:
- `server_render.py` — 슬라이드 관리 라우트 추가
- `templates/admin/slides.html` — 슬라이드 목록 + 상태 칩 필터 + 배치 QC + 검수 모달 + 반려 모달 + 로그 모달 + 개별 추가 모달 + MPP 재처리

**DB 마이그레이션 실행 결과** (`db/slides_deploy_schema.sql`):
```
BEGIN
ALTER TABLE   ← slides.deploy_status VARCHAR(20) DEFAULT 'qc_pending'
ALTER TABLE   ← slides.reject_reason TEXT
UPDATE 4      ← 기존 is_public=TRUE → deploy_status='deployed' 마이그레이션
CREATE INDEX  ← idx_slides_deploy
CREATE INDEX  ← idx_slides_conv
COMMIT
```

**구현 파일**:
- `db/slides_deploy_schema.sql` — 마이그레이션 SQL (멱등)
- `server_render.py` — 슬라이드 관리 라우트 9개 추가, `_slide_access_allowed`·`get_slide_institution`·`load_slides`·viewer 라우트 deploy_status 기반으로 수정
- `templates/admin/slides.html` — 슬라이드 목록 + 상태 칩 + 배치 QC + 검수/반려/로그/개별추가 모달

**주요 설계**:
- 변환 상태(자동) × 배포 상태(사람) 2축 독립 표시
- 배포 대기(ready+qc_pending) 슬라이드만 배포/반려 가능; 배포 중인 슬라이드는 철회 가능
- ready_no_mpp: MPP 인라인 입력 → `conversion_status='pending'` 재처리 트리거
- 검수(KB) 모달: knowledge_base JSON 편집 후 배포 원클릭 또는 저장만 분리
- 반려 사유 DB 저장 (reject_reason), 학생 비노출 보장
- 배치 QC: 체크박스 다중선택 → 일괄 배포/반려
- `_slide_access_allowed`: is_public → deploy_status='deployed' 기반으로 전환 (보안 강화)

---

## S5-4 — 접근 제어 ✅ 완료

**완료일**: 2026-05-31  
**DB 마이그레이션**: 없음 (CREATE 없이 기존 테이블 활용)
- `subject_codes` — 기존 5개 과목 코드 사용
- `institution_subject_access` — S5-2에서 이미 생성됨

**미실행 ALTER 사항 (CEO 보고)**:
- `subject_codes.is_active BOOLEAN DEFAULT FALSE` 컬럼은 v1.0에서 코드 파생으로 대체
- 두 번째 모듈(PATH/PARA) 출시 시점에 ALTER TABLE로 추가 예정
- 파일: `db/access_module_schema.sql` (미실행)

**구현 파일**:
- `server_render.py` — 접근 제어 라우트 3개 추가 (`/admin/access`, `/admin/api/access/modules`, `/admin/api/access/matrix`)
- `templates/admin/access.html` — 콘텐츠 모듈 레지스트리 + 기관×모듈 매트릭스

**주요 설계**:
- v1.0 `_ACTIVE_SUBJECTS = frozenset({'HST'})` 코드 상수로 활성 모듈 관리
- 모듈 레지스트리: subject_codes + deploy_status='deployed' 슬라이드 수 집계
- 기관×모듈 매트릭스: institution_subject_access 읽기 전용 표시 (모든 토글 lock 처리)
- HST: 전 기관 `locked=True, granted=True` (자동 부여, 끄기 불가)
- PATH/PARA: 현재 모두 `locked=True, granted=False` (미리보기 — 출시 후 토글 활성화)
