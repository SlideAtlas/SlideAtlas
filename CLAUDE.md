# CLAUDE.md — SlideAtlas 프로젝트 메모리 v2.8

> 이 파일은 Claude Code 세션 시작 시 반드시 읽어야 하는 프로젝트 컨텍스트 파일입니다.
> 모든 에이전트(오케스트레이터, 개발, QA)는 이 파일을 기준으로 작업합니다.

---

## 1. 프로젝트 개요

**제품명**: SlideAtlas
**운영사**: 아틀라스랩 주식회사 (Atlas Lab Co., Ltd.)
**대표**: 김보람 (Boram Kim)
**URL**: slideatlas.onrender.com / slide-atlas.net (공식 도메인, 2025.05 확정)
**도메인**: atlaslab.co.kr (가비아)
**이메일**: boram@atlaslab.co.kr

**한 줄 정의**: 의과대학·치과대학·수의대·한의대·약대·간호대를 대상으로 한 디지털 병리/조직학 WSI(Whole Slide Image) 구독 SaaS 플랫폼.

**핵심 비즈니스 모델**: 오프라인 슬라이드 납품(보람바이오텍, 20년 의대 납품 이력) 네트워크를 디지털 구독 SaaS로 전환. 연 400만원 구독료, 장비 불필요(WinMedic 등 경쟁사 대비 차별점).

**경쟁 구도**: WinMedic(스캐너+플랫폼 수직통합, 장비 수천만원) vs SlideAtlas(콘텐츠 구독 SaaS 연400만원, 장비 불필요) = 장비판매 vs Netflix

---

## 2. 버전별 개발 로드맵

### v1.0 — 한국 런칭 (2026년 9월 목표)
- **타겟**: 국내 지방의대·수의대·약대·한의대·보건대
- **콘텐츠**: 아틀라스랩이 직접 라이선스 계약한 컬렉션만 제공 (교수 업로드 없음)
- **AI 튜터**: 슬라이드 메타데이터 + `knowledge_base` JSON → Claude API (VectorDB 없음)
- **구독 플랜**: 조직학 베이스 플랜 → 병리·기생충 모듈 추가 방식, 기관당 연 400~900만원
- **모바일**: 반응형 웹 (OpenSeadragon 터치 기본 지원 + CSS 미디어쿼리)
- **마일스톤**: 9월 가을학기 2~3개교 구독 확보 → 초창패 추경 신청

### v1.5 — 콘텐츠 확장·국내 안착 (2026년 말)
- **콘텐츠**: 병리·기생충 모듈, Mahidol 열대의학 컬렉션 라이선스
- **AI 튜터**: 자문 교수 1인 영입 → knowledge_base JSON 검수·보완
- **영업**: 국내 10~15개교 확보, 매출 레퍼런스 구축

### v1.5M — 모바일 PWA 출시 (2027년 1분기)
- **방향**: 네이티브 앱 아님. PWA(Progressive Web App) — 브라우저에서 설치, 앱스토어 불필요
- **핵심 기능**: WSI 뷰어 터치 최적화 (핀치줌·스와이프 패닝), 태블릿 레이아웃 별도 설계, 홈화면 추가 설치
- **개발 기간**: 2~3개월 (v1.5 안착 후 착수)
- **설계 원칙**: v1.0 웹앱을 PWA 전환 고려한 구조로 미리 설계 → 나중에 뜯어고치지 않음
- **앱스토어**: PWA는 심사 불필요. 의료 교육 앱 심사 이슈 회피 가능.

### v2.0 — 글로벌 플랫폼 (2027년 이후)
- **콘텐츠**: Liverpool 열대의학, 아마존·아프리카 기생충학 특수 컬렉션
- **교수 업로드**: 강의노트·PPT 업로드 기능 오픈, 조회수 기반 로열티
- **AI 튜터**: Vector DB (multilingual-e5) + RAG + 다국어 출력
- **구조**: 유튜브식 콘텐츠 마켓플레이스, Fleet Learning 구조

### v2.x — 네이티브 앱 (2027년 Q3~Q4 목표)
- **방향**: React Native 또는 Flutter — 기술 스택은 그때 팀 구성 보고 결정
- **PWA 대비 핵심 추가 기능**:
  - 고배율 타일 렌더링 성능 향상 (브라우저 한계 탈피)
  - 오프라인 캐시 — 자주 보는 슬라이드 로컬 저장 (실습실 환경 대응)
  - Apple Pencil / S펜 마킹 — 슬라이드 위 직접 필기·표시
  - 푸시 알림 — 퀴즈 알림, 새 슬라이드 업로드 등
- **개발 전제**: 투자 유치 후 전문 모바일 개발팀 구성
- **데이터 활용**: PWA 사용 패턴 데이터(어떤 기능을 모바일에서 쓰는지) → 네이티브 앱 스펙으로 직접 활용

> **설계 원칙**: v2.0 기능(VectorDB, 교수 업로드, 다국어, 로열티 정산)은 v1.0 범위에서 제외.
> 단, 코드 모듈 경계는 처음부터 v2.0 확장을 고려해 설계한다.
> PWA 전환을 고려해 v1.0부터 프론트엔드 구조를 잡는다.
> 네이티브 앱 기술 스택(React Native / Flutter)은 투자 유치 후 팀 구성 시점에 결정한다.

---

## 3. 현재 기술 스택

| 구분 | 내용 |
|------|------|
| 백엔드 | Python Flask |
| 뷰어 | OpenSeadragon |
| 배포 | Render Starter ($7/월) |
| 저장소 | AWS S3 (ap-northeast-2, 버킷: slideatlas-slides) |
| 타일서버 | AWS EC2 t3.medium (slideatlas-tileserver, ec2-13-209-99-51.ap-northeast-2) — 동적 워터마킹 처리 포함 (~$40/월) |
| 타일엔진 | titiler + 커스텀 타일서버 (~/tileserver/main.py, rasterio 기반) |
| 파이프라인 | SVS/DCM/TIFF → COG TIFF → S3 → titiler |
| 데이터 관리 | slides.json + institutions.json → **RDS PostgreSQL (slideatlas-db, ap-northeast-2c) 구축 완료, 마이그레이션 진행 중** |
| AI 연동 | Claude API (/api/chat), 구조가이드/질문하기/퀴즈 탭 |
| 버전 관리 | GitHub (SlideAtlas/SlideAtlas) |

---

## 4. 슬라이드 변환 파이프라인 (핵심 인프라)

### 4-1. 설계 원칙

**문제**: SVS/DCM → COG TIFF 변환 시 MPP·오버뷰 레벨이 파일마다 달라 줌인/줌아웃 오작동 발생.
**해결**: 변환 스펙을 완전히 고정. 어떤 파일이 들어오든 출력은 항상 동일한 COG TIFF 스펙.

**고정 변환 스펙 (모든 슬라이드 공통)**
```
타일: 256×256 px
압축: JPEG Q=85
오버뷰: 7레벨 고정 (2, 4, 8, 16, 32, 64, 128)
MPP: 원본에서 추출, 없으면 0.5 기본값, DB에 저장
좌표계: 픽셀 기준, 북서쪽 원점
BigTIFF: 파일 크기 4GB 초과 시 자동 적용
```

### 4-2. 파이프라인 실행 순서

관리자가 파일 업로드 → S3 임시 버킷 → EC2 워커 자동 트리거 → 순차 실행:

```
① extract_meta()      → MPP, 해상도, 포맷, 스캐너 정보 추출·검증
② convert_cog()       → COG TIFF 변환 (표준 스펙 고정)
③ extract_minimap()   → 최저 오버뷰 레벨에서 minimap.png 추출 → S3
④ extract_thumbnail() → MPP 기준 20x 해당 오버뷰에서 thumbnail.jpg 추출 → S3
⑤ generate_kb_json()  → Claude API 호출로 knowledge_base JSON 자동 생성
⑥ run_qc()           → 타일 응답·흰타일 비율·줌 레벨 정합성 검증
⑦ update_db()        → status = ready, 전체 메타데이터 DB INSERT
```

**지원 입력 포맷**: SVS, TIFF, DCM, NDPI, VSI

**미니맵 구현 원칙**: 뷰어 코드에서 미니맵을 그리지 않는다. 파이프라인에서 `minimap.png`를 미리 생성해 S3에 저장하고, OpenSeadragon은 해당 이미지를 불러오기만 한다. 이것이 일관된 미니맵의 유일한 해결책.

**썸네일 구현 원칙**: 20x 배율에 해당하는 COG 오버뷰 레벨을 MPP 기반으로 계산해 400×300 px JPEG 추출. 슬라이드 목록 카드에 자동 표시.

### 4-3. 모듈 구조 (SQS/Lambda 이식성 보장)

미래에 SQS 큐 또는 Lambda로 전환할 때 **엔진 코드 수정 없이** 트리거 어댑터만 교체 가능하도록 설계.

```
pipeline/
├── models.py              # ConversionJob, ConversionResult (데이터 계약, 절대 변경 금지)
├── trigger_adapter.py     # 트리거별 파싱 (v1.0: HTTP / v1.5: SQS / v2.0: Lambda)
├── conversion_engine.py   # 변환 엔진 (핵심 로직, 트리거 무관하게 동일 작동)
└── storage_adapter.py     # S3 이동, RDS 업데이트, 상태 갱신
```

**데이터 계약 (전 버전 공통, 변경 금지)**
```python
@dataclass
class ConversionJob:
    slide_id: str           # 'HS-PATH-004'
    s3_input_key: str       # 'incoming/HS-PATH-004.svs'
    institution_id: str
    original_format: str    # 'SVS', 'DCM', 'TIFF'

@dataclass
class ConversionResult:
    slide_id: str
    status: str             # 'ready' | 'failed'
    s3_cog_key: str         # 'slides/HS-PATH-004/HS-PATH-004.tiff'
    mpp: float
    width: int
    height: int
    qc_passed: bool
    error_log: str | None
```

**마이그레이션 규칙**
- v1.0 → v1.5: `trigger_adapter.py`만 교체 (SQS 파서 추가). 엔진 코드 무변경.
- v1.5 → v2.0: `trigger_adapter.py`만 교체 (Lambda 이벤트 파서). 엔진 코드 무변경.
- 변환 스펙 변경 시: `conversion_engine.py`만 수정. 트리거 코드 무변경.

### 4-4. QC 자동 검증 항목

| 항목 | 기준 | 실패 시 |
|------|------|---------|
| 타일 HTTP 응답 | 저·중·고배율 3레벨 모두 200 | status = failed |
| 흰 타일 비율 | 샘플 타일 흰색 픽셀 < 95% | status = failed |
| DZI 레벨 수 | 원본 해상도 기반 예상값과 일치 | status = failed |
| MPP 범위 | 0.1 ~ 1.0 μm/px | 경고 로그, 계속 진행 |
| 최소 해상도 | 5,000 px 이상 | status = failed |

### 4-5. 상태 머신

```
pending → converting → qc_check → ready
                    ↘            ↘          ↘
                     failed       failed     ready_no_mpp
```

| 상태 | 의미 | 관리자 페이지 표시 |
|------|------|-------------------|
| pending | 업로드 완료, 변환 대기 | 🟡 대기 중 |
| converting | COG 변환 진행 중 | 🔵 변환 중 |
| qc_check | QC 검증 중 | 🔵 검증 중 |
| ready | 정상 서빙 가능 | 🟢 정상 |
| ready_no_mpp | MPP 없음, 배율 기능 제외 서빙 | 🟠 MPP 없음 (경고) |
| failed | 변환/QC 실패 | 🔴 실패 + 로그 |

**ready_no_mpp 처리 원칙**
- 슬라이드 열람 자체는 가능 (타일 서빙 정상)
- 뷰어에서 배율 버튼(10x/20x/40x) 비활성화
- "배율 정보 없음" 안내 표시
- 관리자 페이지에서 MPP 수동 입력 후 재처리 가능
- 기본값(0.5)으로 임의 처리하지 않는다 — 배율 오류가 교육적으로 더 위험

**MPP 확보 전략 (장기)**
- 공급사 계약 시 MPP 포함 요구사항 명시 (Motic 등 상업용 스캐너는 자동 포함)
- MPP 없는 파일 수령 시: 유리슬라이드 원본 재수령 → 뷰웍스 유료 스캐닝 서비스 활용 검토
- 자체 스캐너 도입 시 "스캐닝 서비스 제공"이 공급사 유치 레버리지가 될 수 있음

관리자 페이지에서 각 슬라이드의 현재 상태를 실시간 모니터링. 실패 시 `conversion_log` 컬럼에 오류 내용 보존.

---

## 5. 슬라이드 메타데이터 입력 방식

### 5-1. 배치 업로드 (100장 이상)
엑셀 파일(.xlsx)과 슬라이드 파일을 함께 업로드. 엑셀 컬럼:

```
slide_id | title_ko | title_en | organ | stain | species | subject_code | description
```

- `slide_id`는 파일명에서 자동 파싱 (`HS-HST-001.svs` → `HS-HST-001`)
- Happy Science 등 공급사에 파일명 규칙 사전 합의 필수
- 엑셀 파싱 → DB 일괄 INSERT → 변환 파이프라인 자동 시작

### 5-2. 개별 추가 (1~2장)
관리자 페이지에서 파일 업로드 후 메타데이터 직접 입력 폼 제공.

### 5-3. knowledge_base JSON 자동 생성
메타데이터 입력 완료 후 `generate_kb_json()`이 Claude API를 호출해 자동 생성:

```json
{
  "key_structures": ["villus", "Lieberkuhn crypt", "goblet cell"],
  "exam_points": ["villus height ratio", "cell distribution pattern"],
  "common_confusions": ["jejunum vs ileum — Peyer's patches 유무로 구분"]
}
```

이 JSON이 AI 튜터의 컨텍스트로 사용됨. 교수 자문 없이도 의대 국가고시 수준 답변 가능.

---

## 6. 슬라이드 ID 체계

형식: `{기관코드}-{과목코드}-{순번}`

**설계 원칙**: 기관코드·과목코드는 코드에 하드코딩하지 않는다. 모두 DB 테이블로 관리하여 관리자 페이지에서 개발자 개입 없이 추가 가능.

**기관코드** → `institutions.id` 컬럼이 곧 기관코드 (관리자 페이지에서 추가)
- SA: SlideAtlas 자체
- HS: Happy Science
- YU: 연세대학교
- SNU: 서울대학교
- KU: 고려대학교
- MU: Mahidol University
- AJOU: 아주대학교
- *(신규 기관 계약 시 /admin에서 추가 → 즉시 사용 가능)*

**과목코드** → `subject_codes` 테이블로 관리 (관리자 페이지에서 행 추가)
- HST: 조직학 (Histology)
- PATH: 병리학 (Pathology)
- PARA: 기생충학 (Parasitology)
- ANAT: 해부학 (Anatomy)
- EMBRY: 발생학 (Embryology)
- *(신규 과목 추가 시 /admin에서 행 추가 → 즉시 사용 가능)*

**순번**: 기관+과목 조합별 독립 카운터 (자동 채번)
```sql
SELECT COUNT(*) + 1 FROM slides
WHERE institution_id = 'MU' AND subject_code = 'HST'
-- → MU-HST-001, MU-HST-002 순으로 자동 생성
```

**기관코드 자동 제안**: 관리자가 기관명 입력 시 ICAO식으로 자동 제안, 충돌 시 숫자 suffix 추가
```
"Liverpool School of Tropical Medicine" → "LSTM" 제안
충돌 시 → "LSTM2" 자동 변형 후 확인 요청
```

예시: `HS-HST-001`, `MU-PARA-003`, `LSTM-PARA-001`

---

## 7. DB 스키마 (v1.0 기준)

```sql
CREATE TABLE subject_codes (
  code VARCHAR(10) PRIMARY KEY,  -- 'HST', 'PATH', 'PARA'
  name_ko VARCHAR(50),           -- '조직학'
  name_en VARCHAR(50),           -- 'Histology'
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE institutions (
  id VARCHAR(20) PRIMARY KEY,
  name_ko VARCHAR(100),
  name_en VARCHAR(100),
  domain VARCHAR(100),
  subscription_plan VARCHAR(20),
  subscription_start DATE,
  subscription_end DATE,
  max_users INT,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  institution_id VARCHAR(20) REFERENCES institutions(id),
  email VARCHAR(200) UNIQUE NOT NULL,
  password_hash VARCHAR(255),
  role VARCHAR(20) DEFAULT 'student',
  status VARCHAR(20) DEFAULT 'active',     -- 'active' | 'pending_verification' (JWT 인증 추가)
  is_special BOOLEAN DEFAULT FALSE,        -- 구독 만료 무관 접근 허용 계정 (JWT 인증 추가)
  last_login TIMESTAMP,
  session_token VARCHAR(255),
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE slides (
  id VARCHAR(50) PRIMARY KEY,
  institution_id VARCHAR(20),
  subject_code VARCHAR(20),
  title_ko VARCHAR(200),
  title_en VARCHAR(200),
  description TEXT,
  s3_key VARCHAR(500),
  s3_minimap_key VARCHAR(500),       -- 미니맵 PNG S3 경로
  s3_thumbnail_key VARCHAR(500),     -- 썸네일 JPG S3 경로
  mpp FLOAT,
  width INT,
  height INT,
  stain VARCHAR(50),
  organ VARCHAR(100),
  species VARCHAR(50) DEFAULT 'human',
  license_source VARCHAR(100),
  original_format VARCHAR(20),       -- 원본 포맷 (SVS/DCM/TIFF)
  conversion_status VARCHAR(20) DEFAULT 'pending',  -- pending/converting/qc_check/ready/ready_no_mpp/failed
  conversion_log TEXT,
  qc_passed_at TIMESTAMP,
  is_public BOOLEAN DEFAULT FALSE,
  knowledge_base JSONB,              -- AI 튜터용 구조화 데이터
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE plan_slide_access (
  plan VARCHAR(20),
  subject_code VARCHAR(20),
  PRIMARY KEY (plan, subject_code)
);

CREATE TABLE access_logs (
  id SERIAL PRIMARY KEY,
  user_id INT REFERENCES users(id),
  slide_id VARCHAR(50) REFERENCES slides(id),
  accessed_at TIMESTAMP DEFAULT NOW(),
  session_id VARCHAR(100)
);

CREATE TABLE courses (
  id SERIAL PRIMARY KEY,
  institution_id VARCHAR(20) REFERENCES institutions(id),
  professor_user_id INT REFERENCES users(id),
  title VARCHAR(200),
  semester VARCHAR(20),
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE course_weeks (
  id SERIAL PRIMARY KEY,
  course_id INT REFERENCES courses(id),
  week_number INT,
  title VARCHAR(200)
);

CREATE TABLE course_week_slides (
  course_week_id INT REFERENCES course_weeks(id),
  slide_id VARCHAR(50) REFERENCES slides(id),
  display_order INT,
  PRIMARY KEY (course_week_id, slide_id)
);

CREATE TABLE course_assistants (
  course_id INT REFERENCES courses(id),
  user_id INT REFERENCES users(id),
  PRIMARY KEY (course_id, user_id)
);

-- JWT 인증 추가 테이블 (db/auth_schema.sql) ──────────────────────

CREATE TABLE institution_rosters (    -- 기관 명단 화이트리스트 (users와 별개)
  id SERIAL PRIMARY KEY,
  institution_id VARCHAR(20) REFERENCES institutions(id) ON DELETE CASCADE,
  email VARCHAR(200) NOT NULL,
  name VARCHAR(100),
  role VARCHAR(20) NOT NULL DEFAULT 'student',  -- 'student' | 'professor' | 'ta'
  is_verified BOOLEAN DEFAULT FALSE,
  added_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(institution_id, email)
);

CREATE TABLE email_verifications (    -- 이메일 인증코드 (가입 시 발급, 10분 TTL)
  id SERIAL PRIMARY KEY,
  user_id INT REFERENCES users(id) ON DELETE CASCADE,
  code VARCHAR(6) NOT NULL,
  created_at TIMESTAMP DEFAULT NOW(),
  expires_at TIMESTAMP NOT NULL,
  consumed BOOLEAN DEFAULT FALSE,
  attempt_count INT DEFAULT 0          -- 5회 초과 시 코드 폐기
);
```

> 회원가입은 institution_rosters에 (institution_id+email+role)이 등록된 경우만 허용.
> 가입 시 users.status='pending_verification' → 이메일 인증 완료 시 'active'.
> 마이그레이션: `db/auth_schema.sql` (멱등, 트랜잭션 BEGIN/COMMIT). 실행은 CEO 판단.

---

## 8. 보안 아키텍처

- **Presigned URL / 타일 접근 토큰**: TTL 5분, HMAC-SHA256 서명. 뷰어 페이지 로드 시 `generate_tile_token(user_id, institution_id, slide_id)` 발급 → 모든 타일/DZI URL에 `?t=` 포함. 검증 실패 시 401. S3 버킷 퍼블릭 접근 전면 차단.
- **동적 워터마킹**: v1.0 런칭 시 포함. 사용자 ID·기관명을 타일마다 투명하게 삽입 (Pillow, 투명도 15~20%, 대각선 반복 패턴). Happy Science 등 라이선스 콘텐츠 유출 시 추적 가능.
- **브라우저 캐시 완전 차단**: 타일/DZI/인증 응답 헤더에 `Cache-Control: no-store` 적용. 고객 로컬에 타일 파일 저장 불가.
- **서버사이드 캐시**: EC2 메모리 캐시로 동일 유저·동일 타일 재처리 방지 (보안 위험 없음, 서버에만 존재)
- **동시접속 제어**: 새 기기 로그인 시 기존 session_token 무효화 (기관 해약 아닌 세션 종료만)
- **도메인 기반 자가인증**: 기관 이메일 도메인 검증 + 6개월 재인증
- **멀티테넌시**: institution_id 기반 Row Level 격리. 모든 슬라이드/타일/DZI 라우트에 `@login_required` + institution_id 검사 적용.
- **라이선스 격리**: is_public=FALSE 슬라이드는 어떤 경로로도 직접 URL 접근 불가. `_slide_access_allowed()`에서 is_public 플래그 검사.
- **CSRF 방어**: 더블서밋 쿠키 패턴. `@login_required` POST/PUT/DELETE/PATCH에서 `X-CSRF-Token` 헤더와 `csrf_token` 쿠키를 `secrets.compare_digest`로 대조.
- **계정 잠금**: 24시간 내 비밀번호 오류+인증코드 오류 합산 10회 누적 시 `users.status='locked'`. `locked_at` 컬럼 기준 24시간 경과 시 자동 해제. 잠금 메시지: "보안상 계정이 잠겼습니다. 과 사무실에 문의하세요".
- **이메일 인증코드 재발송**: `POST /api/auth/resend-code`. 1분 쿨다운, 24시간 최대 5회 제한. locked/suspended 계정 차단. 동시 요청 경쟁조건은 `SELECT ... FOR UPDATE`로 방어.
- **구독 만료 매 요청 검사**: `_authenticate()`에서 매 요청마다 `institutions.subscription_end` 확인. 만료 시 SUBSCRIPTION_EXPIRED (401) 반환. is_special 계정 예외.
- **SESSION_REVOKED (401)**: 타 기기 로그인으로 기존 session_token이 무효화된 경우. 프론트는 "다른 기기에서 로그인되었습니다" 안내.
- **TOKEN_INVALID (401)**: 쿠키 없음·JWT 만료·수동 삭제·유저 미조회 등 세션 자체가 없는 경우. 프론트는 로그인 페이지로 리다이렉트.
- **TILE_TOKEN_INVALID (401)**: 타일 접근 토큰(TTL 5분) 검증 실패. 로그인 세션과 무관하므로 인터셉터가 SESSION_REVOKED·SUBSCRIPTION_EXPIRED로 오판하지 않도록 구분.
- **/api/chat 탈옥 방어**: 클라이언트가 전송하는 `system` 파라미터를 무시하고 서버 측 고정 가드레일만 사용.

---

## 9. 관리자 포털 구조

### 슈퍼관리자 (/admin)
- 기관 추가/수정/삭제, 계약 상태/구독 플랜/만료일 관리
- 기관 관리자 이메일 등록/변경
- 슬라이드 관리: 파일 업로드(엑셀 배치 or 개별) → 파이프라인 자동 시작
- **파이프라인 모니터링**: 슬라이드별 conversion_status 실시간 표시 (converting/qc_check/ready/failed + 로그)
- 전체 현황 대시보드

### 기관 관리자 (/portal)
- 계약 체결 후 슈퍼관리자가 기관 관리자 이메일 등록
- 학생 명단: xlsx/csv 업로드(이름+이메일) → DB 등록
- 개별 학생 추가/삭제, 라이선스 현황 표시 (사용 중 N / 전체 N)
- 삭제 시 즉시 접근 차단 + 라이선스 반환

### 라이선스 모델
- 구독 = 기관당 활성 계정 수 라이선스
- 명단 삭제 → 즉시 접근 차단 + 라이선스 1 반환
- 신입생 추가 → 라이선스 1 소비

---

## 10. AI 튜터 구조 (v1.0)

**원칙**: VectorDB 없이 `knowledge_base` JSON + 슬라이드 메타데이터만으로 Claude API 호출.

```python
system_prompt = f"""
당신은 SlideAtlas의 조직학/병리학 AI 튜터입니다.
슬라이드: {slide.title_ko} ({slide.organ}, {slide.stain})
핵심 구조: {knowledge_base['key_structures']}
시험 포인트: {knowledge_base['exam_points']}
혼동 주의: {knowledge_base['common_confusions']}
SlideAtlas 무관 질문에는 답변하지 마세요.
"""
```

**v2.0에서 RAG로 전환 시**: `system_prompt`에 Vector DB 검색 결과를 추가하는 것만으로 업그레이드 완료. 나머지 코드 변경 없음.

---

## 11. 콘텐츠 현황

| 공급사 | 상태 | 수량 | 비고 |
|--------|------|------|------|
| Happy Science (Linda Li) | 계약 진행 중 | 조직학 133종+ | 최우선 파트너, 5월 신향 미팅 |
| TCGA 오픈소스 | 사용 중 | 일부 | MVP용 |
| 3DHISTECH 샘플 | 사용 중 | 1종 (소장 H&E) | MVP용 |
| Vic Science (Joy Xu) | 응답 대기 | - | RFP-002 발송 완료 |
| Hongye (Lily Zhao) | 응답 대기 | - | RFP-002 발송 완료 |

**주의**: 외부 문서에 중국 제조사명 미기재 원칙 (공급망 보호).

**파일명 규칙 합의 필요**: Happy Science 미팅 시 `HS-HST-001.svs` 형식 파일명 규칙 확정 요청. 메타데이터 엑셀 컬럼 양식도 사전 공유.

---

## 12. QA 거버넌스 — 3단계 검증 구조

### 12-1. 전체 워크플로우

```
Claude Code 내부
├── Lead Developer 에이전트  → 구현 (Flask + AWS RDS 코드 작성)
└── QA 에이전트 (레드팀)    → 내부 핑퐁 검증 (섹션당 max 3회)
         ↓ 내부 QA 통과
Codex 외부 검증             → 엣지케이스 이중검증
         ↓ Codex 통과
CEO (보람) 최종 승인        → 다음 섹션으로
```

### 12-2. 에이전트 역할 정의

**Lead Developer (개발 에이전트)**
- 역할: Flask 웹앱 + AWS RDS PostgreSQL 인프라 코드 작성
- 성향: 기능 구현 중심, 빠른 프로토타이핑
- 제약: 인프라 변경(RDS, EC2, S3)은 반드시 CEO 승인 후 실행

**Senior QA Engineer (내부 검증 에이전트 — 레드팀)**
- 역할: 개발 에이전트 결과물을 해커 관점으로 공격, 예외 상황 발굴
- 성향: 극도로 보수적, 타협 없는 보안 및 상용화 품질 요구
- 권한: 5대 체크리스트 중 하나라도 미통과 시 무조건 반려

**Codex (외부 이중검증)**
- 역할: 섹션 완료 후 Claude Code 외부에서 엣지케이스 교차검증
- 투입 시점: 섹션별 내부 QA 통과 직후
- 포커스: Claude Code가 놓친 경계값·레이스컨디션·보안 사각지대

### 12-3. 섹션별 Codex 검증 포커스

| 섹션 완료 | Codex 검증 포커스 |
|------|------|
| 파이프라인 구축 | MPP 없음·포맷 오류·S3 업로드 실패 각 경로 처리 |
| JWT 인증 | 토큰 만료 경계값, 동시 로그인 레이스 컨디션 |
| 동적 워터마킹 | 타일 경계 픽셀 텍스트 잘림, 고배율/저배율 가시성 |
| 기관 접근제어 | URL 조작으로 타 기관 슬라이드 접근 가능 여부 |
| 포털 명단 관리 | 동일 이메일 중복 등록, 삭제 직후 세션 유지 여부 |
| 전체 QA | CLAUDE.md 5대 체크리스트 전항목 최종 점검 |

### 12-4. QA 5대 무조건 체크리스트 (하나라도 미통과 시 Reject)

**① 보안 & 멀티테넌시**
- YU 계정으로 SNU 슬라이드 URL 조작 접근 차단 확인
- JWT 토큰 변조 공격 방어
- session_token 1기기 동시접속 제어
- 타일 접근 토큰 TTL 5분 (`generate_tile_token`, `verify_tile_token`) 작동 확인
- 브라우저 캐시 no-store 헤더 적용 확인 (타일/DZI 응답 포함)
- 계정 잠금 (24h/10회 임계값) 작동 및 자동 해제 확인
- 인증코드 재발송 쿨다운(1분) 및 일일 한도(24h 5회) 제한 확인
- CSRF 더블서밋 검증 (POST/PUT/DELETE 요청 X-CSRF-Token 헤더 대조) 작동 확인
- subscription_end 만료 시 매 요청 접근 차단 확인 (is_special 계정 예외)
- /api/chat 탈옥 방어: 클라이언트 system 파라미터 무시, 서버 측 가드레일 작동 확인

**② 파이프라인 안전성**
- COG TIFF 처리 시 파일 전체 메모리 로드 금지 (스트리밍 강제)
- QC 실패·ready_no_mpp 슬라이드가 ready 상태로 전환되지 않는지 확인
- 미니맵·썸네일 S3 경로가 DB에 정확히 저장되는지 확인
- ready_no_mpp 슬라이드에서 배율 버튼 비활성화 확인

**③ 비즈니스 로직**
- subscription_end 경과 사용자 접근 차단 및 결제 유도 팝업
- /api/chat 탈옥 질문 시 방어벽 작동

**④ DB 마이그레이션 안전성**
- 마이그레이션 스크립트 트랜잭션 처리
- 중간 에러 시 전면 Rollback

**⑤ 라이선스 격리**
- is_public=FALSE 슬라이드 비구독 기관 노출 차단
- Happy Science 라이선스 콘텐츠 외부 유출 경로 차단

### 12-5. 워크플로우 통제 규칙

- **내부 핑퐁 max 3회**: Dev ↔ QA 한 이슈당 최대 3회. 초과 시 즉시 중단 → CEO 판단 대기
- **Codex 검증 후 CEO 승인**: Codex 통과 없이 다음 섹션 진행 금지
- **인프라 변경 금지**: RDS, EC2, S3 설정 변경은 CEO 명시적 승인 없이 절대 실행 불가
- **토큰 절약**: 반복 수정 시 전체 재작성보다 diff 기반 수정 우선

---

## 13. 개발 원칙 & 주의사항

- **AWS 자격증명**: nohup 컨텍스트에서 인라인 `$(aws configure get ...)` 치환 실패 → 환경변수 먼저 export 후 실행
- **Windows SCP**: PEM 권한 설정은 비관리자 PowerShell에서 icacls 처리
- **한국어 PDF**: reportlab/weasyprint 한글 폰트 임베딩 한계 → Adobe Illustrator 직접 작업
- **중국어 문서**: Node.js docx 패키지, SimSun TextRun 별도 분리 필요
- **COG 변환 배치**: SVS 1장당 5~15분, 133장 = 최대 30시간 → EC2에서 밤새 배치 실행
- **매출 우선 원칙**: 정부지원(초창패 등)보다 9월 매출 데이터 확보가 최우선
- **모듈 경계 원칙**: `ConversionJob` / `ConversionResult` 데이터 계약은 어떤 이유로도 변경 금지

---

## 14. 주요 외부 연락처

- Happy Science: Linda Li / info@ihappysci.com / WhatsApp +86 188 3816 1683
- Vic Science: Joy Xu / joy@vicscience.com
- Hongye: Lily Zhao / Lianhonglianli@163.com
- 성원애드피아: 명함 인쇄 (아르미 울트라화이트 310g 양면)

---

## 19. 인프라 접속 정보

### RDS PostgreSQL

| 항목 | 값 |
|------|------|
| 엔드포인트 | slideatlas-db.c94iwikwox6l.ap-northeast-2.rds.amazonaws.com |
| DB명 | slideatlas |
| 유저 | slideatlas_admin |
| 포트 | 5432 |
| 리전/AZ | ap-northeast-2 / ap-northeast-2c |

**접속 방법**: EC2 Instance Connect → psql (로컬 psql 설치 불필요)

```bash
# EC2에서 RDS 접속
psql -h slideatlas-db.c94iwikwox6l.ap-northeast-2.rds.amazonaws.com \
     -U slideatlas_admin \
     -d slideatlas \
     -p 5432

# DDL 스크립트 실행
psql -h slideatlas-db.c94iwikwox6l.ap-northeast-2.rds.amazonaws.com \
     -U slideatlas_admin \
     -d slideatlas \
     -p 5432 \
     -f db/schema.sql
```

**보안 원칙**: RDS Security Group은 EC2 인스턴스 IP만 인바운드 허용. 로컬 PC에서 직접 접속 불가 (VPC 내부 전용).

### EC2 SSH 접속 (Windows)

| 항목 | 값 |
|------|------|
| PEM 파일 경로 | C:\Users\아무개\slideatlas-key.pem |
| 접속 명령어 | ssh -i "C:\Users\아무개\slideatlas-key.pem" ubuntu@ec2-13-209-99-51.ap-northeast-2.compute.amazonaws.com |
| PowerShell 종류 | 반드시 비관리자 PowerShell 사용 |

**주의**: 관리자 PowerShell에서 실행하면 "계정 이름과 보안 식별자 사이에 매핑이 이루어지지 않았습니다" 오류 발생.
외장하드(E:) 경로 직접 사용 불가 — 반드시 C:\Users\아무개\ 경로 사용.

---

*최종 업데이트: 2026-05-30 v2.8 | 변경 내용: JWT 인증 보안 결함 수정 2회차 완료 (타일토큰 TTL, CSRF 검증, 계정잠금, 재발송, 구독만료 매요청 검사, 탈옥방어) | 다음 업데이트: 포털 명단 관리 구현 완료 시점*
