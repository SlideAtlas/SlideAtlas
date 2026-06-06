# CLAUDE.md — SlideAtlas 프로젝트 메모리 v3.12

> 세션 시작 시 반드시 읽는 프로젝트 컨텍스트. 모든 에이전트(오케스트레이터·개발·QA)의 기준 문서.
>
> **골격**: 구독·좌석·만료·접근·집계가 모두 (기관 × 과목) 단위로 독립(§0). v1.0(HST 단일)은 그 구조의 특수 케이스일 뿐. 슬라이드 접근은 **단일 게이트(`_slide_access_allowed`) 기반 과목 구독 격리**(`SA`는 소유자 표시일 뿐 공용/기본제공 아님, §6-1·§8). 온보딩은 **구독 선행**(없으면 가입·인증 거부, §6-3). 만료·가입은 **접근창(`access_open_date<=today<=subscription_end`, KST)·fail-closed**(§8·§16). 미룬 항목은 **§18 기술부채**에 집결. 버전별 변경 이력은 문서 끝 참조.

---

## 0. 단일 진실 원칙 (v3.0 신설 — 최상위 규칙)

다음을 **모든 섹션·코드·QA에 우선하는 상위 규칙**으로 둔다.

1. **구독의 단위는 (기관 × 과목)**, 진실의 원천은 `subscriptions` 테이블. 좌석(max_seats)·만료(subscription_end)·접근권·집계·정원검사는 **전부 과목별 독립**.
2. **`institutions`의 옛 구독 컬럼(subscription_plan/start/end, max_users)은 deprecated** — 인증·좌석·만료 경로 **참조 금지**(죽은 컬럼, v1.5 정리 §18).
3. **`users.subject_code`는 "어느 과목 명단인가"이며 가입 시 반드시 채워진다**(roster의 (institution_id, subject_code, email) 매칭 캡처). 단 **계정 단위는 이메일 — 한 이메일 = users 1계정, 과목 접근은 roster 행으로 표현**(v3.2, §6-2). `users.email`은 전역 UNIQUE. (다과목 한계는 §18 D12.)
4. **v1.0이 HST 단일인 것은 데이터의 우연이지 구조의 전제가 아니다.** 코드는 항상 과목 축을 일급으로 다루며 "과목 하나니까"라는 단축을 두지 않는다.
5. 충돌하는 옛 서술/코드 발견 시 **이 문서가 우선**, 코드를 이 문서에 맞춘다.

---

## 1. 프로젝트 개요

**제품**: SlideAtlas | **운영사**: 아틀라스랩(Atlas Lab Co., Ltd.) | **대표**: 김보람 | **URL**: slideatlas.onrender.com / slide-atlas.net(공식) | **도메인**: atlaslab.co.kr(가비아) | **이메일**: boram@atlaslab.co.kr

**한 줄 정의**: 의·치·수의·한의·약·간호대 대상 디지털 병리/조직학 WSI(Whole Slide Image) 구독 SaaS.

**비즈니스 모델**: 오프라인 슬라이드 납품(보람바이오텍 20년 이력) 네트워크를 디지털 구독 SaaS로 전환. **좌석 플랜 기반 학기 단위 구독**, 장비 불필요(경쟁사 대비 차별점).

**경쟁 구도**: WinMedic(스캐너+플랫폼 수직통합, 장비 수천만원) vs SlideAtlas(콘텐츠 SaaS, 장비 불필요) = 장비판매 vs Netflix. 실제 프레임은 "유리슬라이드 1회 구매(₩18M+) 대체"(무료 디지털 사이트 아님).

---

## 2. 버전별 개발 로드맵

### v1.0 — 한국 런칭 (2026년 9월 목표)
- **타겟**: 국내 지방의대·수의대·약대·한의대·보건대. **콘텐츠**: 아틀라스랩 직접 라이선스만(교수 업로드 없음). **AI 튜터**: 슬라이드 메타데이터 + `knowledge_base` JSON → Claude API(VectorDB 없음).
- **모듈**: **조직학(HST) 단일**(*판매 과목 하나뿐*, 코드·구독은 다과목 일급 §0). 병리·기생충 v1.5+. **구독**: (기관×과목) 단위, 좌석 플랜 × 학기(§16).
- **LMS**(수업 개설·주차 배치·수강·즐겨찾기): **v1.0 정식 범위·핵심 과금 차별점**(한국어+국가고시+교수 커리큘럼, §21). **모바일**: 반응형 웹. **마일스톤**: 9월 가을 2~3개교 → 초창패 추경.

### v1.5 — 콘텐츠 확장·국내 안착 (2026년 말)
- 병리·기생충 모듈 활성, Mahidol 라이선스 / 자문 교수 1인→kb 검수 / 10~15개교 / §18 부채 정리(옛 구독 컬럼 DROP 등).

### v1.5M — 모바일 PWA (2027 Q1)
- PWA(앱스토어 불필요). WSI 터치 최적화, 태블릿 레이아웃, 홈화면 추가.

### v2.0 — 글로벌 플랫폼 (2027+)
- Liverpool 등 특수 컬렉션, 교수 업로드+로열티, Vector DB(multilingual-e5)+RAG 다국어, 콘텐츠 마켓플레이스.

### v2.x — 네이티브 앱 (2027 Q3~Q4)
- React Native/Flutter. 고배율 렌더링·오프라인 캐시·펜 마킹·푸시. 투자 유치 후.

> **설계 원칙**: v2.0 기능(VectorDB·교수 업로드·다국어·로열티)은 v1.0 제외하나, 모듈 경계·프론트 구조는 v2.0/PWA 확장 고려해 v1.0부터 설계.

---

## 3. 현재 기술 스택

| 구분 | 내용 |
|------|------|
| 백엔드 | Python Flask (server_render.py + auth/ 패키지 + templates/) |
| 뷰어 | OpenSeadragon |
| 배포 | Render Starter($7/월, 임시 개발). 9월 정식 런칭은 EC2 — §18 D16 |
| 저장소 | AWS S3 (ap-northeast-2, 버킷: slideatlas-slides) |
| 타일서버 | AWS EC2 t3.medium (slideatlas-tileserver, EIP 3.34.35.58) — 동적 워터마킹 (~$40/월) |
| 타일엔진 | titiler + 커스텀 타일서버 (~/tileserver/main.py, rasterio) |
| 파이프라인 | SVS/DCM/TIFF/NDPI/VSI → COG TIFF → S3 → titiler |
| 데이터 관리 | RDS PostgreSQL (slideatlas-db, ap-northeast-2c), 마이그레이션 진행 중 |
| AI 연동 | Claude API (/api/chat) — 구조가이드/질문하기/퀴즈 탭 |
| 버전 관리 | GitHub (SlideAtlas/SlideAtlas) |

---

## 4. 슬라이드 변환 파이프라인 (핵심 인프라)

### 4-1. 설계 원칙
변환 스펙을 완전히 고정 — 어떤 입력이든 출력은 항상 동일한 COG TIFF.

**고정 변환 스펙 (모든 슬라이드 공통)**
```
타일: 256×256 px / 압축: JPEG Q=85 / 오버뷰: 7레벨 고정 (2,4,8,16,32,64,128)
MPP: 원본에서 추출 (없으면 ready_no_mpp, 임의 기본값 금지), DB 저장
좌표계: 픽셀 기준, 북서쪽 원점 / BigTIFF: 4GB 초과 시 자동
```

### 4-2. 파이프라인 실행 순서
관리자 업로드 → S3 임시 버킷 → EC2 워커 자동 트리거 → 순차 실행:
```
① extract_meta() → MPP·해상도·포맷·스캐너 추출·검증
② convert_cog() → COG TIFF 변환(표준 스펙 고정)
③ extract_minimap() → 최저 오버뷰 minimap.png → S3
④ extract_thumbnail() → 20x 오버뷰 thumbnail.jpg(400×300) → S3
⑤ generate_kb_json() → Claude API로 kb JSON 초안 생성
⑥ run_qc() → 타일 응답·흰타일 비율·줌 정합성 검증
⑦ update_db() → status 갱신, 메타데이터 DB INSERT
```
**미니맵/썸네일 원칙**: 파이프라인이 미리 생성해 S3 저장, OpenSeadragon은 불러오기만.

> ⚠ **현황(QA)**: 현재 thumbnail은 openslide 동적 생성이라 "S3 사전 생성" 원칙과 불일치, /minimap 라우트 미구현(③④ 미구현 → §18 D7).

### 4-3. 모듈 구조 (SQS/Lambda 이식성 보장)
```
pipeline/
├── models.py            # ConversionJob, ConversionResult (데이터 계약, 변경 금지)
├── trigger_adapter.py   # 트리거별 파싱 (v1.0 HTTP / v1.5 SQS / v2.0 Lambda)
├── conversion_engine.py # 변환 엔진 (트리거 무관 동일)
└── storage_adapter.py   # S3 이동·RDS 업데이트·상태 갱신
```
`ConversionJob`/`ConversionResult` 데이터 계약은 변경 금지. 마이그레이션 시 `trigger_adapter.py`만 교체, 엔진 무변경.

### 4-4. QC 자동 검증 항목
| 항목 | 기준 | 실패 시 |
|------|------|---------|
| 타일 HTTP 응답 | 저·중·고 3레벨 모두 200 | failed |
| 흰 타일 비율 | 샘플 타일 흰색 < 95% | failed |
| DZI 레벨 수 | 예상값 일치 | failed |
| MPP 범위 | 0.1~1.0 μm/px | 경고, 계속 |
| 최소 해상도 | 5,000 px 이상 | failed |

### 4-5. 변환(파이프라인) 상태 머신
```
pending → converting → qc_check → ready
                    ↘ failed   ↘ failed  ↘ ready_no_mpp
```
| 상태 | 의미 | 어드민 표시 |
|------|------|-------------------|
| pending | 업로드 완료, 변환 대기 | 🟡 대기 |
| converting | COG 변환 중 | 🔵 변환 중 |
| qc_check | 자동 QC 검증 중 | 🔵 검증 중 |
| ready | 변환·자동QC 통과 | 🟢 변환완료 |
| ready_no_mpp | MPP 없음, 배율 비활성 서빙 | 🟠 MPP 없음 |
| failed | 변환/QC 실패 | 🔴 실패 + 로그 |

**ready_no_mpp 원칙**: 열람 가능(타일 정상)하나 배율 버튼 비활성·"배율 정보 없음" 표시. 어드민에서 **MPP 수동 입력 후 재처리(Retry)**. 임의 기본값(0.5) 금지(배율 오류가 교육적으로 더 위험).

> ⚠ **변환 상태(자동) ⊥ 배포 상태(사람 결정).** `ready`여도 자동 공개 안 됨 — 사람의 교육 QC(배포 결정)가 별도로 얹힘(§5-4·§15-3). 노출 게이트는 `deploy_status=='deployed'`만 사용, `conversion_status`는 게이트에 안 씀.

---

## 5. 슬라이드 메타데이터 & 지식베이스(kb)

### 5-1. 배치 업로드 (100장 이상)
엑셀(.xlsx)+슬라이드 파일 동반. 컬럼:
```
slide_id | title_ko | title_en | organ | stain | species | subject_code | description
```
- `slide_id`는 파일명 자동 파싱(규칙 사전 합의). `subject_code`=슬라이드 소속 과목. **MPP 입력 안 함 — 변환 시 자동 추출.**

### 5-2. 개별 추가 (1~2장)
파일(SVS/TIFF/NDPI/DCM/VSI)+메타데이터 폼. **기관코드 SA 고정(§6)**, 과목 선택→ID 자동 채번. **MPP 입력칸 없음**. 공급원은 `license_source`→뷰어 푸터 자동 표기.

### 5-3. knowledge_base JSON 자동 생성
`generate_kb_json()`이 Claude API로 자동 초안 생성. 필드: `key_structures`(예: villus, Lieberkuhn crypt) / `exam_points`(시험 포인트) / `common_confusions`(예: jejunum vs ileum) / `ko_observation_points`(한국어 관찰 순서·키워드). 마지막이 무료 사이트 대비 핵심 차별점.

### 5-4. kb 검수 = QC 단계 게이트 (중요)
kb 검수·보완은 **업로드 시점이 아니라 배포(QC) 단계**에서:
```
업로드(파일+메타) → 자동 변환 + kb 초안 → 배포 대기
   → (소수) 어드민 "검수" 모달 보완 후 배포
   → (대량 134장) kb 초안 엑셀 내보내기 → 검수자 일괄 보완 → 일괄 반영(엑셀) → 일괄 배포
```
검수는 학생 노출 직전 게이트. `deploy_status`(§15-3)로 관리.

---

## 6. 슬라이드 ID 체계 & 사용자–과목 매칭

### 6-1. 슬라이드 ID
형식: `{기관코드}-{과목코드}-{순번}`. **v1.0 채번 원칙**: 아틀라스랩은 **라이선스 후 스캔 주체**(제작자 아님)이므로 v1.0 모든 콘텐츠는 **기관코드 `SA`로 단일 채번**(공급사는 ID에 안 넣음).
- 공급원·저작권은 ID가 아니라 **`slides.license_source`**에 기록. acknowledgement 요구 시 **푸터에 "Provided by ___" 자동 표기**.
- **공급사는 institutions에 안 넣음** — license_source로만 관리(대부분 비공개, acknowledgement 필요 시만 푸터 노출 §18 D18). (율린 `YL` 폐기, `YU`는 연세대 예약.)

> ★ **`SA`는 "콘텐츠 소유자(아틀라스랩 라이선스·스캔)" 표시일 뿐, "전 기관 공용"·"기본 제공"이 아니다.** `institution_id='SA'`는 채번·소유 표시이며 **접근 격리 기준이 아니다** — 각 슬라이드는 **그 과목(`slide.subject_code`) 구독 기관의 그 과목 좌석 사용자에게만** 노출(§8 단일 게이트). **HST도 첫 런칭 과목일 뿐 기본 제공 아님**(어떤 기관은 PARA만 구독).

**과목코드** → `subject_codes` 테이블 관리(하드코딩 금지): HST 조직학 / PATH 병리학 / PARA 기생충학 / ANAT 해부학 / EMBRY 발생학. **순번**: 기관+과목 조합별 독립 카운터(예: `SA-HST-001`).

> 향후 교수 업로드(v2.0)·고객 자체 콘텐츠 생기면 기관코드 다축 채번 재도입.

### 6-2. 사용자–과목 매칭 (v3.0/v3.2 확정 — 핵심)
- **회원가입은 `institution_rosters`에 (institution_id, subject_code, email)이 등록된 경우만 허용.** register·verify_email 시 `users.subject_code`를 반드시 채운다(매칭 키 = roster의 (institution_id, subject_code, email)).
- **★ 이메일당 users 1계정 (v3.2 — CEO·외부검증 확정).** 옛 "과목별 user 독립 생성" 폐기. 현행: **한 이메일 = users 1계정, 과목 접근은 `institution_rosters` 행으로 표현**, `users.email` **전역 UNIQUE**. register는 동일 이메일 재가입을 `EMAIL_EXISTS`로 거부, verify/login은 이메일 단일 키로 식별. (DB 차원 전역 UNIQUE는 별도 마이그레이션, 현재 앱 레이어 강제. 다과목 한계 §18 D12.)
- ⚠ **회귀 주의**: 옛 코드가 subject_code 미채번→전 사용자 NULL→과목별 만료/좌석 검사 무력화. v3.0 이후 반드시 채번, NULL 폴백 **제거됨**(§13-2).

### 6-3. 온보딩 순서 원칙 (v3.1 — CEO 확정)
**구독 계약·입금 전에는 학생을 받지 않는다.** 코드가 강제하는 순서:
```
① 구독 계약·입금 → ② access/subscriptions 생성(어드민, 기관×과목 접근창·좌석)
→ ③ institution_rosters 등록(이름+이메일+과목 명단) → ④ register → verify_email
```
- **가입·인증 시 (institution_id, subject_code) 접근창 내 active 구독 없으면 거부**(`SUBSCRIPTION_INACTIVE` 403). 접근창 = `access_open_date<=today<=subscription_end`(KST); 미래 학기 구독이 미리 active여도 창 전엔 불가(§8·§16). 옛 "구독 없으면 정원 무제한" 로직 **제거**(Codex #4).

### 6-4. 가입·역할 모델 — 두 트랙(position·role 자동부여, v3.3)
가입 시 **두 명단을 순차 대조**해 `position`·`role`을 **자동 부여**(가입자는 입력 안 함). **폼 = 기관 드롭다운 + 이메일 + 비번 + 비번확인 (이름 입력 없음, 표시명 = roster.name)**.
- **트랙1 (이용자 roster)**: (기관, 이메일) 매칭 → `position` 캡처(교수/조교/학생/행정직원) → `role='viewer'`. **트랙2 (`__ADMIN__` 행)**: 매칭 시 `role='admin'`(포털 접근). **겸직**: 둘 다 매칭이면 position=실제 지위, role='admin'.
- **role 두 값** `viewer`/`admin`. **기능 권한 분기는 role이 아니라 `position` 기반**(예: 수업 개설=position∈{교수,조교}); role은 포털 접근만 가른다(§21). §6-2 "이메일당 1계정" 유지.

> **position의 단일 출처 = 과목(subject) roster 행(v3.4 CEO 확정).** 가입 시 트랙1 매칭 subject 행의 position을 `users.position`에 복사. **subject 행 없는 계정(admin-only)은 position=NULL**(운영 전용, 좌석 0). **행정직원은 admin-only로 표현**(콘텐츠 비소비 관리자 회피책 §18 D17). 겸직이어도 position은 subject 행에서(**겸직 우선순위 없음**). `__ADMIN__` 행 position은 NULL.

---

## 7. DB 스키마 (v1.0 기준)

> **단일 진실(§0)**: 구독·좌석·만료·접근은 `subscriptions`(기관×과목)가 원천. `institutions`의 subscription_*/max_users는 **deprecated**, 코드 미참조(§18).

```sql
-- subject_codes: code VARCHAR(10) PK('HST'..), name_ko, name_en, is_active DEFAULT FALSE(모듈 활성, v1.0은 HST만 TRUE), created_at

CREATE TABLE institutions (
  id VARCHAR(20) PRIMARY KEY,     -- 기관코드
  name_ko VARCHAR(100), name_en VARCHAR(100), university VARCHAR(100), college VARCHAR(100), domain VARCHAR(100),  -- name_ko="충남대 의과대학", domain=이메일 자가인증
  -- ⚠ DEPRECATED (v3.0): 아래 4개는 옛 "기관 단위 구독" 잔재. 인증/좌석/만료 참조 금지, v1.5 DROP(§18).
  subscription_plan VARCHAR(20), subscription_start DATE, subscription_end DATE, max_users INT, created_at TIMESTAMP DEFAULT NOW()
);

-- 구독: 기관 × 과목 단위 (좌석·학기·구독료 독립) ── 단일 진실 원천(§0)
CREATE TABLE subscriptions (
  id SERIAL PRIMARY KEY, institution_id VARCHAR(20) REFERENCES institutions(id), subject_code VARCHAR(10) REFERENCES subject_codes(code),
  plan VARCHAR(20),                -- department|standard|campus|institution|custom
  max_seats INT,                   -- 정원 검사 기준(플랜 기본값 또는 특수계약 직접 지정)
  start_term VARCHAR(10), term_count INT,  -- '2026-fall' 학기 식별자 / 구독 학기 수
  access_open_date DATE,           -- 학기 시작 -30일(자동)
  subscription_end DATE,           -- 마지막 학기 종료일(자동). 만료 검사 기준.
  fee INT, payment_method VARCHAR(20), status VARCHAR(20) DEFAULT 'active', created_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(institution_id, subject_code, start_term)
);

-- subscription_history(갱신/변경 이력, 누적 보존): subscription_id→subscriptions, event(initial|renewal|change), plan, max_seats, start_term, term_count, fee, note, created_by→admin_users, created_at(모두 id SERIAL PK)
-- institution_subject_access(콘텐츠 접근권, 기관×과목, 좌석과 직교): PK(institution_id→inst, subject_code→subject_codes), granted DEFAULT TRUE

CREATE TABLE users (
  id SERIAL PRIMARY KEY, institution_id VARCHAR(20) REFERENCES institutions(id), email VARCHAR(200) NOT NULL, password_hash VARCHAR(255),
  subject_code VARCHAR(10),         -- ★ 어느 과목 명단인지(과목별 좌석 카운터). 가입 시 필수 채번(§6-2).
  role VARCHAR(20) DEFAULT 'viewer',  -- ★ v3.3: viewer|admin (§21). role과 position은 별개 축.
  position VARCHAR(20),               -- ★ v3.3: 교수/조교/학생/행정직원. 기능 권한 분기 근거(§21). 가입 시 roster 캡처.
  status VARCHAR(20) DEFAULT 'pending_verification', -- active|pending_verification|locked
  is_special BOOLEAN DEFAULT FALSE,  -- 구독 만료 무관 접근(§15-8)
  special_expires_at DATE, special_review_at DATE,  -- 만료일(NULL=무기한 비권장)·재검토/사전알림
  last_login TIMESTAMP, locked_at TIMESTAMP, failed_attempts INT DEFAULT 0, failed_window_start TIMESTAMP,  -- 계정 잠금 카운터(§8, 24h)
  session_token VARCHAR(255), created_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(institution_id, subject_code, email)
  -- ★ v3.2 정책(§6-2): 계정 단위=이메일(1계정). DB 차원 email 전역 UNIQUE는 별도 마이그레이션, 현재 앱 레이어 강제.
);

CREATE TABLE slides (
  id VARCHAR(50) PRIMARY KEY,        -- 'SA-HST-001'
  institution_id VARCHAR(20),        -- v1.0은 항상 'SA'
  subject_code VARCHAR(20), title_ko VARCHAR(200), title_en VARCHAR(200), description TEXT,
  s3_key VARCHAR(500), s3_minimap_key VARCHAR(500), s3_thumbnail_key VARCHAR(500),
  mpp FLOAT, width INT, height INT, stain VARCHAR(50), organ VARCHAR(100), species VARCHAR(50) DEFAULT 'human',
  license_source VARCHAR(100),       -- 공급원(푸터 표기) 예: 'Provided by Yulin'
  original_format VARCHAR(20),
  conversion_status VARCHAR(20) DEFAULT 'pending', -- §4-5
  deploy_status VARCHAR(20) DEFAULT 'qc_pending',  -- §15-3: qc_pending|deployed|rejected
  reject_reason TEXT, conversion_log TEXT, qc_passed_at TIMESTAMP,
  knowledge_base JSONB, created_at TIMESTAMP DEFAULT NOW()
);

-- 어드민 계정: 2단계 권한 (학생 JWT와 완전 분리)
CREATE TABLE admin_users (
  id SERIAL PRIMARY KEY, email VARCHAR(200) UNIQUE NOT NULL, password_hash VARCHAR(255) NOT NULL, name VARCHAR(100),
  role VARCHAR(20) NOT NULL,         -- super_admin|staff
  is_active BOOLEAN DEFAULT TRUE, last_login_at TIMESTAMP,
  session_token VARCHAR(255),        -- v3.2: 매 요청 DB 대조(탈취·재로그인 무효, Codex#2)
  failed_attempts INT DEFAULT 0, failed_window_start TIMESTAMP, locked_at TIMESTAMP,  -- v3.2: 무차별 대입 차단(24h·+24h 자동 해제)
  updated_at TIMESTAMP DEFAULT NOW(), created_at TIMESTAMP DEFAULT NOW()
);
-- ⚠ 위 4개(session_token·failed_attempts·failed_window_start·locked_at)는 db/admin_security_schema.sql(멱등)로 추가, 병합 전 RDS 실행 필수.

-- (간결 표기: 모든 id SERIAL PK·created_at DEFAULT NOW())
-- announcements(랜딩 공지·소프트 삭제): title, body, is_published(최대 5 노출), display_order, is_archived·archived_at(보관함), created_by·updated_by→admin_users, updated_at
-- inquiries(1:1 문의, 기관 자동 첨부): user_id→users, institution_id→inst(ON DELETE SET NULL, 익명 NULL), title, body, user_email, user_name, status DEFAULT 'open'(open|answered)
--   ⚠ privacy_agreed 컬럼 부재 → 개인정보 동의 저장 공백, 출시 전 필수(§18 D1).
-- inquiry_replies: inquiry_id→inquiries, body, created_by→admin_users(감사 추적), sent_via_ses DEFAULT TRUE
-- access_logs: user_id→users, slide_id→slides, institution_id, accessed_at, session_id

-- 기관 명단 화이트리스트 / 이메일 인증 (JWT 인증)
CREATE TABLE institution_rosters (
  id SERIAL PRIMARY KEY, institution_id VARCHAR(20) REFERENCES institutions(id) ON DELETE CASCADE,
  subject_code VARCHAR(10),            -- ★ 과목별 명단. users.subject_code 출처(§6-2).
  email VARCHAR(200) NOT NULL, name VARCHAR(100), role VARCHAR(20) NOT NULL DEFAULT 'viewer',  -- role: viewer|admin
  position VARCHAR(20),                -- ★ v3.4: 지위(교수/조교/학생). subject 행에만, __ADMIN__ 행 NULL. users.position 출처(§6-4).
  is_verified BOOLEAN DEFAULT FALSE, added_at TIMESTAMP DEFAULT NOW(), UNIQUE(institution_id, subject_code, email)
);
-- email_verifications: user_id→users(CASCADE), code VARCHAR(6), created_at, expires_at NOT NULL, consumed DEFAULT FALSE, attempt_count INT

-- ── 교수 수업 페이지(LMS) — v1.0 정식 범위 (§21). 수업은 접근 게이트가 아니라 학습 경로(접근은 §8 단일 게이트).
-- (간결 표기: 컬럼·FK·PK 동일, 모든 id SERIAL PK·created_at DEFAULT NOW())
-- courses: institution_id→inst, subject_code→subject_codes(수업은 특정 과목 안에서만), professor_user_id→users, title, semester
-- course_weeks: course_id→courses(CASCADE), week_number, title, empty_reason(빈 주차 사유)
-- course_week_slides: course_week_id→course_weeks(CASCADE), slide_id→slides, display_order (주차 내 중복 허용)
-- course_assistants: PK(course_id→courses CASCADE, user_id→users) (수업별 조교 위임)
-- course_enrollments: PK(course_id→courses CASCADE, user_id→users), enrolled_at (자유 등록·승인 불필요·다대다, 과목 구독과 별개 축)
-- favorites: PK(user_id→users, slide_id→slides), created_at (개인 북마크, 수업 무관)
```

> 회원가입 규칙은 §6-2(roster 매칭·subject_code 캡처·pending→active). 마이그레이션은 멱등·트랜잭션, 실행은 CEO 판단.

---

## 8. 보안 아키텍처

- **타일 접근 토큰**: TTL 5분, HMAC-SHA256. 뷰어 로드 시 `generate_tile_token(user_id, institution_id, slide_id)` 발급 → 타일/DZI URL `?t=`. `verify_tile_token`은 user_id·institution_id·slide_id·exp **모두 대조**, 실패 401. S3 퍼블릭 차단.
  - **무중단 재발급 (v3.1)**: `GET /api/tile-token?slide=`가 **단일 게이트 통과 시에만** 새 토큰 발급(접근권 없으면 거부). 뷰어는 4분마다 선제 갱신 + 타일 로드 실패 시 재발급 후 재그리기. `TILE_TOKEN_INVALID`는 로그인과 무관 → **강제 `/login` 리다이렉트 금지**(`window.refreshTileToken()` 처리).
  - **인증 2단계 분리 (v3.2 — Gemini#1 DoS 방어)**: 권한 검사(`_slide_access_allowed`+구독·세션 DB 조회)는 **저빈도 발급 경로**(`/viewer/<id>`, `GET /api/tile-token`)에만. **고빈도 타일 스트리밍 경로**(`/dzi/<id>.dzi`, `/dzi/.../<col>_<row>.jpeg`, `/thumbnail/<id>`, `/ec2tile/<path>`)는 `@tile_token_required`로 **DB 조회 없이** 서명 JWT 복호화+HMAC tile_token 검증만(타일마다 구독·기관 JOIN 도는 RDS 고갈/DoS 차단). 권한 회수는 토큰 TTL(≤5분) 후 발급 게이트에서 반영(허용 지연). 발급 경로 DB 권위 검증은 유지.
- **동적 워터마킹**: v1.0 포함. 사용자 ID·기관명 타일마다 투명 삽입(Pillow, 15~20%, 대각선). **특별 계정도 동일**(유출 추적). **브라우저 캐시 차단**: 타일/DZI/인증 `Cache-Control: no-store`. **서버 캐시**: EC2 메모리(보안 위험 없음).
- **동시접속 제어**: 새 기기 로그인 시 기존 session_token 무효화(세션 종료, 해약 아님). **도메인 자가인증**: 기관 이메일 도메인 검증 + 6개월 재인증.
- **멀티테넌시**: `institution_id`는 **user·access_logs·subscriptions·roster 등 사용자/운영 데이터 격리**에만 쓴다. ⚠ **슬라이드 접근 격리에는 안 씀** — "슬라이드 기관==사용자 기관" 화석은 v3.1에서 전 경로 제거(단일 게이트로 대체).
- **슬라이드 접근 단일 게이트 (v3.1 — `_slide_access_allowed`)**: 모든 슬라이드/타일/DZI/썸네일/뷰어/목록 경로 통과. 일반 사용자는 **전부(AND)** 충족 시에만 접근:
  1. `deploy_status == 'deployed'`
  2. `g.subject_code == slide.subject_code` (사용자가 등록된 과목 == 슬라이드 과목)
  3. 사용자 기관이 그 과목 접근권 보유: `institution_subject_access.granted=TRUE` **또는** (institution_id, subject_code) 접근창 내 active 구독
  → 하나라도 불충족이면 403. **"deploy_status만 맞으면 공용 허용" 완화 절대 금지(§0-4).** `institution_id`(='SA')는 게이트에 안 씀.
  - **is_special**: `deploy_status=='rejected'`만 차단(qc_pending/deployed 허용), **institution·subject 축 정책상 우회**(§15-8), 단 만료(special_expires_at)는 집행.
  - **수업(course)은 접근 게이트가 아니다** — 접근은 오직 과목 구독. 수업 미등록이어도 구독 과목 슬라이드 전체 열람 가능(§21).
- **라이선스 격리**: deploy_status != 'deployed'는 어떤 경로로도 직접 URL 접근 불가. **특별계정도 rejected 차단**(§15-8, CEO).
- **CSRF 방어**: 더블서밋 쿠키. POST/PUT/DELETE/PATCH에서 `X-CSRF-Token` 헤더와 `csrf_token` 쿠키를 `compare_digest` 대조. **모든 인증 fetch는 interceptor.js로 토큰 자동 주입**(viewer.html 포함 — QA 회귀 H1 교훈).
- **계정 잠금**: 24h 내 비번+인증코드 오류 10회→'locked', `locked_at`+24h 자동 해제. **인증코드 재발송**: 1분 쿨다운, 24h 최대 5회, 경쟁조건 `SELECT ... FOR UPDATE`.
- **구독 만료 매 요청 검사 (v3.1 — 접근창 집행, fail-closed)**: `_authenticate()`·`login()`이 매 요청 **(institution_id, subject_code) 매칭 + 접근창 열린(`access_open_date<=today<=subscription_end`, KST) active 구독** 존재를 확인(옛 `institutions.subscription_end` 참조 금지).
  - **매칭 구독 없으면(NULL) 차단 = fail-closed**(옛 `is not None` 가드 제거 FAIL1). **미래 학기 active여도 access_open_date 전엔 통과 금지**(#3).
  - `is_special`은 만료 면제, **단 `special_expires_at < today`면 차단**(NULL=무기한 통과, 비권장)(#5).
  - **role·is_special·institution_id는 DB 권위**(v3.2): `_authenticate()`가 매 요청 DB 재조회→`g` 적재(JWT payload 신뢰 금지 — 강등/해제 즉시 반영).
  - **admin 구독 면제는 'roster 결합'**(v3.2): `__ADMIN__` roster 행 존재 시에만 유효(`_has_admin_roster`); 회수 시 면제 사라져 일반 사용자처럼 차단(role 강등 없이).
- **어드민 세션 시크릿 fail-closed (v3.1)**: `ADMIN_SECRET_KEY` 누락 시 **폴백 없이 기동 실패**(RuntimeError) — 어드민 세션 쿠키 위조 차단(§18 D3, #6).
- **어드민 세션 DB 대조·잠금 (v3.2)**: 로그인 성공 시 `admin_users.session_token` 회전(DB+Flask) → **매 요청 `_get_admin_user`가 DB와 `compare_digest` 대조**(탈취·재로그인 무효). `/admin/login`에 학생과 동일 잠금(24h·10회→`locked_at` 자동 해제); **잠금 시 `session_token=NULL` 회전으로 기존 세션 즉시 무효화** + 매 요청 `locked_at` 검사 차단.
- **401 코드 구분**: SESSION_REVOKED(타 기기) / TOKEN_INVALID(세션 없음) / TILE_TOKEN_INVALID(타일토큰 실패, 로그인 무관 — **리다이렉트 금지, 뷰어 JS 재발급**) / SUBSCRIPTION_EXPIRED. interceptor.js가 4종 구분 처리.
- **문의 답변 발송 (v3.1)**: 메일 **성공 시에만** `status='answered'`(실패 시 open 유지+경고). Subject/To **헤더 주입 거부**(개행 제거), 제목·본문 **HTML escaping**(2-2#3).
- **리포트 XLSX 수식 주입 방어 (v3.1)**: 셀 값이 `=+-@`로 시작 시 `'` 프리픽스 무력화(2-2#4, §18 D9). 어드민 화면 문자열은 `escH()`(2-2#5).
- **/api/chat 탈옥 방어**: 클라이언트 `system` 파라미터 무시, 서버 고정 가드레일만.
- **어드민 인증**: `admin_users` 이메일+비번(bcrypt). staff는 super_admin이 발급·비활성화. 매 요청 status='active' DB 확인. 권한 게이트는 §15-2(API 레벨, UI 숨김 아님).

---

## 9. 기관 관리자 포털 (/portal)

**기관 관리자(admin) 계정 모델 (v3.2)**
- **저장**: 별도 테이블 없이 `institution_rosters`에 **센티넬 `subject_code='__ADMIN__'`(`ADMIN_ROSTER_SUBJECT`), `role='admin'`** 행. 같은 이메일이 `__ADMIN__` 행과 과목 학생 행으로 공존(겸직). role(포털 접근)·position(표시용)은 별개.
- **로그인·식별**: 관리자도 **학생과 동일 JWT 인증**(register·verify-email·login), 별도 경로 없음. `users.role='admin'`으로 식별, 관리자 등록은 과목·구독·좌석 게이트 면제로 가입·인증 통과(슬라이드 접근은 단일 게이트가 과목 좌석으로 판정 §8). **단 구독 만료 면제는 `__ADMIN__` 행 존재와 결합**(`_has_admin_roster`) — 회수 시 면제·포털 접근 소멸(Codex#2).
- **등록 플로우(닫힘)**: ① super_admin이 기관 추가/수정 시 `admin_contacts`(≤5명) 입력 → ② `_upsert_admin_roster`가 `__ADMIN__`·`role='admin'` 행 등록(동일 트랜잭션) + 커밋 후 **포털 초대 메일**(`_send_portal_invite_email`, 헤더 주입 방어) → ③ 관리자 회원가입→인증 → ④ `/portal`(`_is_institution_admin`이 `__ADMIN__` 행 존재로 판정, role 단독 우회 없음). 관리자 제거 = `__ADMIN__` 행만 DELETE(포털 권한만 회수, users 계정·과목 행 불가침).
- **이용자 명단: (이름+지위+과목+이메일) xlsx/csv 업로드** → `institution_rosters`. 학생·조교·교수 모두 등록. 지위(position)=학생/조교/교수/행정직원(role과 별개 §21); 명단 행 role 'viewer' 고정. 과목(subject_code)=좌석 카운터(과목별 독립, 여러 과목 가능). 컬럼 순서 이름|지위|과목|이메일, 인라인 편집 시 지위·과목 드롭다운.
- 개별 추가/삭제, 과목별 라이선스 현황(활성 N/max_seats N), 삭제 시 즉시 차단+좌석 반환.
- **이용 리포트**: 과목별 활성/좌석 소진율·총 열람·AI 질문수·Top N·로그인 추세·마지막 활동. 과목별 산출 후 기관 롤업(§15-7).

**포털 P1 — 명단 관리 (✅ 구현, v3.8)**
- 라우트: `GET/POST/DELETE /portal/api/roster` + `POST /portal/api/roster/upload`(xlsx/csv). 화면 `templates/portal.html`(interceptor.js CSRF 자동주입, esc() XSS 방어).
- **게이트**: 상태변경은 `@login_required`(CSRF) + `_portal_guard`(=`_is_institution_admin`, `__ADMIN__` 행 존재 단일 기준, role 단독 우회 불가). **scope는 `g.institution_id` 강제** — body의 institution_id 미참조(IDOR 불가).
- **과목 allowlist**: `_subscribed_subjects` = 구독 행 보유 과목만(status 무관). 미래학기=접근창 닫힘은 분기 C 안전망.
- **★ sync(`_sync_member`) — D17 해결**: 명단 추가/업로드 시 동일 이메일 기존 user의 `position`·`subject_code` 동기화, 판정식은 register와 공통 헬퍼(`active_window_subscription`/`active_seat_count`)로 단일화(§0).
  · A(admin-only+접근창 열림+좌석 여유)→NULL→과목 전환(구독행 FOR UPDATE; 좌석부족 skip-and-report). B(다른 과목 active)→보류(D12). C(접근창 닫힘)→admin-only 유지(fail-closed). D(user 없음)→roster 행만 추가. **role은 어떤 경로도 UPDATE 안 함**(겸직 보존).
- **제거 회수(`_remove_member`)**: 과목 행 삭제 시 그게 user의 현재 active 과목이면 `subject_code`·`position` NULL 회수(좌석 1석 반환 + 단일 게이트가 접근 자동 차단). 계정·role 불변. `__ADMIN__` 행은 포털 제거 불가(읽기전용).
- **일괄 업로드**: 단일 트랜잭션, 예상된 거절(좌석/다과목/형식/중복) skip-and-report(부분 성공), 예기치 못한 에러만 전면 롤백, 행별 outcome. 이메일 정규식·지위/과목 allowlist·중복 dedup·인코딩 폴백·행수 상한(2000)·content-length(5MB).

**포털 P2 — 구독 플랜 (✅ 구현, v3.12, 읽기 전용)**
- 라우트(전부 `@login_required`+`_portal_guard`, GET): `GET /portal/api/plans`(구독 카드+좌석현황) / `GET /portal/api/plans/slides?subject_code=`(과목 배포 슬라이드 메타) / `GET /portal/api/plans/slides/export?subject_code=&format=xlsx|csv`(내보내기). 화면 `templates/portal.html` `#panel-plan`(P1과 동일 standalone+interceptor.js, esc() XSS).
- **슈퍼관리자 엔드포인트 직접 호출 안 함** — 포털 전용 읽기 래퍼. SQL·헬퍼만 재사용.
- **단일 진실(§0)**: 구독 카드는 `subscriptions`(기관×과목)만, `institutions` 옛 구독 컬럼 0건. 좌석 현황 = `active_seat_count`(status='active', P1·리포트와 동일 단일판정식, pending 미점유). 접근창·만료·D-day = 기존 `_sub_status`/`_sem_dates` 재사용(신규 계산식 없음).
- **스코프 격리(§9)**: scope는 `g.institution_id` 강제 — inst_id를 body/쿼리로 안 받음(IDOR 불가).
- **슬라이드 목록**: 그 과목 `deploy_status='deployed'` 메타데이터 카탈로그(ID·제목·과목·염색)만, 타일·토큰 발급 없음. "열람"은 `/viewer/<id>` 이동 → **표준 `_slide_access_allowed` 게이트가 판정**(포털이 게이트 우회 안 함, 관리자도 과목 좌석 필요).
- **과목 격리(전 slides 경로)**: 목록·export 모두 `_subscribed_subjects` allowlist — 비구독 `subject_code`는 빈 목록 아닌 **403(SUBJECT_NOT_SUBSCRIBED)**.
- **내보내기 수식주입 방어**: XLSX(openpyxl)·CSV(BOM) 모든 셀 `_xlsx_safe` 재사용(§8·§18 D9). PDF는 클라이언트 `window.print()`(한국어 폰트 reportlab 한계 §13-1 회피).
- 내부 QA(읽기라 §12 외부검증 대신 Claude Code 내부): (a)스코프격리 (b)/viewer 우회없음 (c)수식주입 방어 (+)전 slides 경로 과목격리 — pytest 168(P2 16 추가). P3(이용 리포트)는 다음 세션.

---

## 10. AI 튜터 구조 (v1.0)

VectorDB 없이 `knowledge_base` JSON + 슬라이드 메타데이터만으로 Claude API 호출. v2.0은 system_prompt에 Vector DB 검색 결과만 추가하면 RAG 전환(나머지 무변경).

> ⚠ **현황(QA)**: api_chat 항상 스트리밍 반환→퀴즈(startQuiz) 파싱 실패→폴백 퀴즈, 실제 생성 미완(§18 D6).

---

## 11. 콘텐츠 현황 (v3.0 — 조달 방식 확정, 공급사 미정)

**조달 확정: 물리슬라이드 구매 → 뷰웍스 일괄 스캔.** 디지털 SVS 라이선스 아닌 물리 구매·직접 스캔(사유: 비용 우위·원본 확보·**MPP·품질 직접 통제**·짧은 리드타임).

**공급사: 율린 vs Vic — 택일 예정.** 둘 다 물리슬라이드 후보, 가격·종류·수량 비교해 택일. **Vic 견적 대기 중**(수령 후 율린 $600/134장과 비교). 기준: 커버 수·단가·품질/리드타임·장기 라이선스.

- 후보: Yulin(A, 견적 134장 약 $600)·Vic Science(B, 견적 대기). 보류: Happy Science(SVS, 글로벌 옵션). 스캔: 뷰웍스(장당 1만원+VAT). MVP용: TCGA/3DHISTECH 샘플.

**저작권/공급사 관계(CEO 원칙)**: 우회 없이 디지털 라이선스 가치 설명 + **연 라이선스비 선제안**. 1년차 물리 구매 갈음, 2년차부터 연 라이선스. 목적: 분쟁 예방 + 장기 신뢰.

**미확보 슬라이드**: 중국 공급사 조달 불가분 **v1.0 제외**(예: brown adipose tissue — Ward's Science만, 향후 보충). v1.0 목표 = 선택 공급사 스캔 완료분. **일정**: 공급사 결정·송금 → 스캔.

> 외부 문서에 중국 제조사명 미기재(공급망 보호). 파일명 규칙·메타데이터 엑셀 양식은 스캔 전 확정.

---

## 12. QA 거버넌스 — 3단계 검증 구조

```
Claude Code 내부: Lead Developer(구현) ↔ QA(레드팀, 섹션당 max 3회)
   ↓ 내부 통과 → Codex 외부 검증(엣지케이스) → 통과 → CEO 최종 승인 → 다음 섹션
```

**워크플로우 통제**: 내부 핑퐁 max 3회 초과 시 중단→CEO. Codex 통과 없이 다음 섹션 금지. **인프라 변경(RDS/EC2/S3)은 CEO 명시 승인 없이 절대 금지.** QA·검증 에이전트는 읽기 전용(코드·grep·로컬 pytest만, DB 쓰기·SSH·마이그레이션 금지). 토큰 절약 위해 diff 우선.

**QA 5대 무조건 체크리스트 (하나라도 미통과 시 Reject)**
1. **보안·멀티테넌시·과목 구독 격리(단일 게이트)**: 슬라이드 접근은 `_slide_access_allowed`만 사용 — `deploy_status=='deployed'` AND `g.subject_code==slide.subject_code` AND 기관이 그 과목 구독/접근권 보유. **"슬라이드 기관==사용자 기관" 잔존 0건**, **"deploy_status만 검사 공용 허용" 완화 금지**(§0-4·§8). + JWT 변조 방어·1기기 동시접속·타일토큰 대조/TTL/재발급 게이트·no-store·계정잠금(24h/10회)·인증코드 재발송 한도·CSRF(interceptor 전 fetch)·**접근창 구독 만료 매요청(fail-closed)**·**특별계정 special_expires_at 집행**·ADMIN_SECRET_KEY fail-closed·/api/chat 탈옥 방어·**어드민 권한 게이트(super_admin/staff) 우회 불가**.
2. **파이프라인 안전성**: COG 스트리밍(전체 메모리 로드 금지), QC 실패·ready_no_mpp가 ready로 전환 안 됨, 미니맵·썸네일 S3 경로 정확, ready_no_mpp 배율 버튼 비활성.
3. **비즈니스 로직·온보딩 순서**: 만료 사용자 차단+결제 유도, **변환 ready여도 deploy_status='deployed' 아니면 비노출**, **과목별 좌석(max_seats) 정확**, **접근창 active 구독 없으면 가입·인증 거부**(SUBSCRIPTION_INACTIVE, §6-3).
4. **DB 마이그레이션**: 트랜잭션, 중간 에러 전면 Rollback.
5. **라이선스 격리**: 미배포 비구독 노출 차단, 반려(rejected) 원본 비노출(특별계정 포함), license_source 외부 유출 차단.

---

## 13. 개발 원칙 & 주의사항

### 13-1. 일반 원칙
- **AWS 자격증명**: nohup 인라인 치환 실패 → 환경변수 먼저 export. **Windows SCP**: PEM 권한 비관리자 PowerShell icacls.
- **한국어 PDF**: reportlab/weasyprint 폰트 한계 → Illustrator. **중국어 docx**: Node.js·SimSun TextRun 분리. **COG 배치**: SVS 1장 5~15분, 134장 ≤30시간 EC2 밤샘.
- **매출 우선**: 정부지원보다 9월 매출. **모듈 경계**: `ConversionJob`/`ConversionResult` 계약 변경 금지. **과목 축 단축 금지(§0-4)**: "HST 하나니까" subject_code 검사 생략 금지.

### 13-2. 인증·구독 코드 불변식 (v3.0)
- 만료=subscriptions.subscription_end / 정원=subscriptions.max_seats / 가입=roster (institution_id,subject_code,email) 매칭 + users.subject_code 채번. (institutions.* 참조 금지, 모두 (institution_id,subject_code) 키.)
- 반환 shape(데코레이터·_authenticate 튜플 길이) 변경은 다운스트림 언패킹·테스트 회귀 유발 → 신중히, 변경 시 인증 테스트 전수 재실행.

---

## 14. 주요 외부 연락처

- Yulin(율린): Jessy, Cathy — 물리슬라이드 후보 A(견적 수령) / Vic Science: Joy Xu joy@vicscience.com — 후보 B(견적 대기)
- Happy Science: Linda Li info@ihappysci.com(보류, 글로벌 옵션) / 뷰웍스: 스캔 서비스(장당 1만원+VAT) / 성원애드피아: 명함

---

## 15. 슈퍼관리자 어드민 (구현 사양)

> 화면 사양은 `docs/mockups/` HTML 목업 6개를 1차 사양서로(§17).

### 15-1. 탭 구조
`[운영]` 대시보드·기관 관리·슬라이드 관리·접근 제어·이용 리포트·특별 계정 / `[고객 응대]` 공지 관리·1:1 문의

### 15-2. 권한 (2단계)
| 탭 | super_admin | staff |
|---|---|---|
| 대시보드 | ✅ | ✅ 읽기만 |
| 기관·슬라이드·접근제어·이용리포트·특별계정 | ✅ | ❌ (사이드바에서 숨김) |
| 공지 관리 | ✅ | ✅ |
| 1:1 문의 | ✅ | ✅ |
- staff는 운영 탭 사이드바 미노출 + **API 레벨 차단**, 액션 버튼 숨김. 모든 작성/수정/답변에 `created_by` 기록.

### 15-3. 슬라이드 배포 상태 (변환 상태와 별개)
```
qc_pending(배포 대기) → deployed(배포 중) ↔ revoked(철회→배포 대기 복귀)
                      ↘ rejected(반려, 사유 기록)
```
- **반려(rejected)**: 원본 품질 문제(찢어짐·초점). 사유 기록 → **학생·특별계정 비노출** → 공급사 재공급 목록 자동 등록 → 원본 보존(삭제 금지) → 대체본 도착 시 같은 slide_id 재업로드. (재공급 목록은 2번째 모듈 시점.)
- **철회(revoked)**: 배포 내림→qc_pending 복귀(내부 결정). **배치 QC**: 체크박스 다중 → 일괄 배포/반려.

### 15-4. 기관 추가/수정/갱신 (§16 모델 기반)
- 기본 정보: 학교명·단과대·(영문)·이메일 도메인(슬라이드ID/기관코드 입력 없음, SA 고정).
- 구독: **과목별 구독 카드**(과목+좌석플랜/수+시작학기+학기수+구독료+결제), "+ 추가". **v1.0 카드 1개(HST)일 뿐 N개 지원**(§0-4). 좌석은 플랜 선택 시 자동·직접 수정 가능, 카드별 독립.
- 학기/접근창: §16 학기제, 오픈일·만료일 자동(읽기전용). 관리자 ≤5명, 저장 시 SES 안내. 갱신: **과목 단위**, 다음 학기 자동 세팅, 이력 누적(`subscription_history`).

### 15-5. 슬라이드 QC / 파이프라인
- 변환 상태(자동)+배포 상태(사람) 2축 표시, 상태 필터 칩. 개별 추가: 파일+메타데이터, **MPP 입력칸 없음**, 기관 SA 고정, 과목 필수, 공급원→푸터(§5-2).
- ready_no_mpp: 인라인 MPP+재처리. failed: 로그+재변환. 검수 모달: kb 초안(핵심구조/시험포인트/혼동주의/한국어 관찰포인트) 편집 후 배포(§5-4).

### 15-6. 접근 제어
- **콘텐츠 모듈 레지스트리**(조직학 활성/병리·기생충 준비중), 좌석↔콘텐츠 분리(§16).
- **기관 × 모듈 매트릭스**: 조직학 전 기관 자동·잠김, 병리·기생충 출시 후 토글. 기관 추가 시 행 자동 생성, **2번째 모듈 시점 구현**(v1.0 미리보기). ⚠ 모듈 활성 진실은 `subject_codes.is_active`(DB) — 코드 상수와 단일화.

### 15-7. 이용 리포트
- 포털 리포트와 동일 화면 + **학교 선택 드롭다운**. **집계 과목별 → 기관 롤업**(개별 학생 추적 지양). 좌석 소진율 = 과목별 (활성/max_seats). 엑셀/PDF. ⚠ 문자열이 `=+-@`로 시작 시 CSV 수식 주입 → 셀 앞 이스케이프.

### 15-8. 특별 계정
- 자문위원·검수자·데모·공급사 평가용. 구독 만료 무관(is_special), 워터마킹 동일.
- **접근 범위(CEO)**: qc_pending·deployed 허용(검수), **rejected 차단**. institution 축은 정책상 우회.
- **선택 만료일 + 사전 알림(14/30일 전)**. 무기한 비권장(잊힌 계정=보안 구멍).

### 15-9. 공지 관리
- 랜딩 공지 **최대 5개 노출**, 순서 지정, 게시↔숨김.
- **소프트 삭제(보관함)**: 삭제→보관함(이력 보존), 복원→숨김 복귀, 완전 삭제는 보관함 확인 후. super_admin·staff 모두 가능.
- 비로그인 노출은 `is_published=TRUE AND is_archived=FALSE`, title+date만(created_by/보관함 미노출).

### 15-10. 1:1 문의
- "사이트 사용 전반/FAQ 미해결". 접수 시 **기관 정보 자동 첨부**(로그인 institution_id, 비로그인 NULL) → staff가 운영 탭 없이 응대.
- 답변 SES 발송, created_by, open/answered. **메일 성공 시에만 `answered`**(실패 시 open+경고). 헤더 주입 거부·HTML escaping(§8).
- ⚠ **개인정보 동의 저장 공백**: 폼은 동의 받으나 privacy_agreed 부재로 미저장(§18 D1).

### 15-11. 대시보드
- KPI: 활성 구독 기관 / 이번 학기 확정 매출 / **활성 사용자·과목별 좌석** / 만료 임박(D-90). 만료·갱신 D-day(과목 단위), 학기별 매출 추이, 파이프라인 현황, 처리 대기(미답변 문의·검수·MPP없음·갱신).

---

## 16. 가격·구독 모델 (v3.0)

- **좌석 플랜이 기본 가격축**: Department(50)/Standard(150)/Campus(300)/Institution(500+). 특수계약은 좌석 수 직접 지정.
- **학기 단위 라이선스**: 봄(3/1~8/31)/가을(9/1~익년 2월말), 6개월 단위. **방학 접근 허용**(복습 목적).
- **접근 오픈일 = 학기 시작 −30일**(봄 2/1, 가을 8/1; 편의, 라이선스 기간과 별개). 날짜 경계는 **KST 일관**(`_today_kst`, §18 D10). **접근창 집행**: 만료/가입 검사가 `access_open_date<=today<=subscription_end`를 본다(미래 학기 구독이 미리 active여도 창 전엔 불가, §8 Codex#3).
- **참고 가격**: 연 ₩4,000,000 / 학기 ₩2,500,000(학기 단가 할증으로 연납 유도). 실제는 딜별 확정.
- **베타·런칭 모델 (v3.1)**: **특정 학교 고정 아닌 "6개월 무료 → 구독 전환"**. 무료 기간도 (기관×과목) 구독 레코드(접근창·좌석)를 생성해야 학생이 가입·접근(§6-3). "확정 베타 파트너"로 문서 고정 안 함.
- **좌석⊥콘텐츠**: 좌석=규모·가격, 모듈=무엇을 여는가. **HST는 첫 런칭 과목일 뿐 자동/기본 제공 아님** — 다른 과목처럼 (기관×과목) 구독 필요(§6-1).
- **(기관×과목) 단위 독립**(§0; 예: 조직학 150석 + 기생충학 30석, 좌석·학기·구독료·갱신 따로). 정원 = subscriptions.max_seats(§13-2). 신규 과목 가격(별도/번들/상위티어)은 출시 시점 결정.

---

## 17. 화면 사양서 (목업)

구현 1차 사양은 `docs/mockups/`의 HTML 목업(클릭 가능):
- `institution_modals.html` — 기관 추가/수정/갱신(과목별 구독 카드, 학기제)
- `slide_qc.html` — 슬라이드 QC/파이프라인(2축 상태, 배치 QC, 검수 kb, 반려, MPP 재처리, 개별 추가)
- `access_reports_special.html` — 접근 제어·이용 리포트·특별 계정 / `notices_inquiries.html` — 공지(보관함)·1:1 문의(권한 분리)
- `admin_integrated.html` — 통합 대시보드(IA) / `institution_portal.html` — 포털 /portal(명단·구독플랜·리포트 3탭)

> 목업과 본 문서 충돌 시 본 문서 우선. 목업은 레이아웃·동작 참조용.

---

## 18. 기술부채 & 출시 전 필수 항목 (v3.0 신설 — 단일 집결지)

> 미룬 항목·출시 전 필수 항목을 한곳에 집결. 상태: 🔴 출시 전 필수 / 🟠 v1.5 전 / 🟡 추적

| ID | 항목 | 내용 | 상태 | 조치 주체 |
|----|------|------|------|-----------|
| D1 | inquiries.privacy_agreed 컬럼 | 개인정보 동의 저장 공백(법적). 폼은 동의받으나 DB 미저장. | 🔴 출시 전 필수 | CEO → ALTER |
| D2 | SES 발송 전환 | Gmail SMTP → SES(도메인 인증 후). **★ e2e(2026-06): EC2 Gmail SMTP 미설정으로 가입 인증코드 메일 미발송(users·코드는 생성되나 미수신) — 9월 학생 가입 출시 블로커. 임시 Gmail 앱비번 또는 SES 전환, 인증코드 메일 반드시 발송.** | 🔴 출시 전 필수 | 도메인 인증 후 |
| D3 | ADMIN_SECRET_KEY 환경변수 | ✅ 코드 fail-closed(미설정 시 기동 실패, Codex #6) + Render 설정 확인. | ✅ 완료 | 확인 |
| D4 | users.subject_code 채번 | ✅ 완료(17bb18a): register 캡처→채번, verify_email 누락 거부, login·_authenticate NULL 폴백 제거. 정원 검사 subscriptions.max_seats 이전(ddfab51). | ✅ 완료 | Lead Developer |
| D4b | 라이브 DB NULL subject_code 0건 확인 | 출시 전 EC2에서 `SELECT COUNT(*) FROM users WHERE subject_code IS NULL` 1회 실행해 0건 확인(존재 시 백필). RDS는 EC2 전용 VPC(§12·§19). | 🔴 출시 전 필수 | CEO |
| D5 | institutions 옛 구독 컬럼 DROP | subscription_plan/start/end·max_users. 코드 미참조화 완료, 데이터만 잔존. | 🟠 v1.5 전 | CEO → DROP |
| D6 | 퀴즈 실제 생성 로직 | api_chat 항상 스트리밍 반환 → startQuiz 파싱 실패 → 폴백 퀴즈, 실제 생성 미구현. | 🟠 v1.5 전 | Lead Developer |
| D7 | 미니맵/썸네일 파이프라인 | §4-2 "S3 사전 생성" vs 현재 동적 생성. /minimap 라우트 부재. | 🟠 v1.5 전 | Lead Developer |
| D8 | 기관×모듈 매트릭스 | 2번째 모듈 시점 구현. subject_codes.is_active(DB) 단일 진실. | 🟠 2번째 모듈 시 | Lead Developer |
| D9 | 리포트 집계 과목별 산출 (Codex #7) | 이용 리포트는 과목별 산출→기관 롤업이어야 함(§9·§15-7). 현재 일부 집계가 과목 축 미분리. (XLSX 수식 방어는 별건 완료 2-2#4.) | 🟠 v1.5 전 | Lead Developer |
| D10 | 날짜 타임존 일관성 | ✅ 인증·접근창·만료·가입은 `_today_kst`(KST) 통일(v3.1). 잔여(리포트 기간 등) 추적. | 🟡 추적(주요 완료) | Lead Developer |
| D11 | DB 커넥션 release 전수 | get_db_conn/release_db_conn 누수 전수 카운트 미완. | 🟡 추적 | QA |
| D12 | 다중 과목 접근 (정책 확정 v3.2, Codex#3·Gemini#5) | ✅ 정책 확정: **이메일당 users 1계정, 과목 접근은 institution_rosters 행, users.email 전역 UNIQUE**(§6-2). register가 이메일 전역 검사로 중복 계정/pending 차단(앱 레이어). 잔여: ① DB 차원 email 전역 UNIQUE 제약(별도 마이그레이션) ② 단일 `users.subject_code` 게이트라 한 계정 다과목 동시 열람 미구현 — v1.5. (구분: 수업 다대다 등록은 `course_enrollments`로 v1.0 지원, 과목 구독과 별개 축 §21.) | 🟠 v1.5 전(정책 확정) | Lead Developer |
| D13 | 온보딩 순서 운영 체크리스트 | §6-3 순서(구독 계약·입금 → access/subscriptions 생성 → roster 등록 → 학생 가입)를 운영 절차로 문서·교육. 코드는 강제하나(SUBSCRIPTION_INACTIVE) ② 선행 누락 시 학생 가입 불가 → 사고 방지. **v3.9: 과목 이동 = 기존 명단 삭제 후 새 과목 추가(2단계, 자동 전환 없음 — D12).** | 🔴 출시 전 필수 | CEO/운영 |
| D14 | Locust 부하 테스트 (7월 말) | 표적: 동시 가입·로그인 시 `FOR UPDATE` 좌석 잠금(over-seating/데드락), 동시 타일 EC2 부하, 커넥션 풀 고갈(D11), 로그인 폭주 계정잠금. (타일 DB 병목은 v3.2 토큰 인증 분리로 해소 §8.) | 🟠 v1.5 전(7월 말) | Lead Developer/QA |
| D15 | 다중 기관 관리자 포털 접근 (Gemini#2) | 한 사람이 여러 기관 관리자면 포털 scope가 단일 기관(`g.institution_id`) 고정이라 갇힘. v1.0 밖(드묾). **v1.5: `/portal/<institution_id>` 또는 기관 선택 드롭다운.** | 🟡 v1.5 과제 | Lead Developer |
| D16 | EC2 정식 배포 이전 (9월 런칭 = EC2) | **결정(v3.2): "Render 런칭 후 AWS 이전" 폐기, 9월부터 EC2.** RDS는 VPC 프라이빗(같은 VPC EC2만 접속). 정석: EC2에서 Flask를 gunicorn+nginx+TLS(현 Flask 개발서버·Render는 임시). 기능 완료 후 EC2 이전 → DNS를 EIP(3.34.35.58) 전환 → Render 폐기. | 🔴 출시 전 필수 | CEO |
| D17 | 콘텐츠 비소비 관리자 역할 미커버 | 근본: '과목 roster 행 유무'가 좌석·지위·콘텐츠 소비를 묶어(§6-4) "명단 관리만 하는 교수/조교" 표현 못함(관리자 선가입 시 admin-only로 굳음). **✅ 해결(v3.8): 포털 P1 `_sync_member`가 명단 추가/업로드 시 기존 user의 position·subject_code 동기화(§9 — 좌석 재검사 FOR UPDATE, 다과목 보류 D12, 접근창 닫힘 보류, role 불변, 공통 헬퍼 §0, 제거 시 좌석 회수). 행정직원 회피책 불요화.** 잔여: 다과목 동시 active(D12) v1.5. | ✅ P1 해결 / 잔여 D12 | Lead Developer |
| D18 | institutions에 고객/소유자/공급사 혼재 | 공개 GET /api/institutions가 고객 학교+소유자(SA)+공급사를 모두 드롭다운 노출(is_subscribable 플래그안은 수동관리 부담 폐기). **✅ 해결(v3.8): 드롭다운 기준을 '구독 존재 여부'로 교체 — `JOIN subscriptions`(status 무관). SA·공급사 자동 제외, 새 학교 즉시 노출. is_subscribable 코드 참조 0건.** 잔여(v1.5): 컬럼 DROP + suppliers 테이블 분리 + license_source FK화. | 🟠 v1.5 잔여 ✅ 교체 완료 | Lead Developer |
| D19 | 발송 실패 시 가입 트랜잭션 정책 미정의 | register 메일 실패 시 users(pending)·email_verifications 잔존 → 반복 실패 시 pending 누적 + 재가입 EMAIL_EXISTS 교착 가능. 정책 미정((가)재발송/(나)롤백/(다)기존 pending 재발송 우회). D2와 묶임. | 🟠 v1.5 전(D2 후속) | Lead Developer |
| D20 | 현재-접근창 테스트 구독 생성 수단 부재(개발 편의) | 가을 런칭 기준이라 시작학기 선택지가 2026 가을부터·갱신은 다음 학기만 → '지금 접근창 열린' 테스트 구독을 UI로 못 만들어 psql로 access_open_date 임시 조정(e2e). **2026-06 스모크용으로 TEST 기관 HST access_open_date를 2026-06-04로 임시 조정 — 실데이터 전환 시 원복 검토.** | 🟡 추적(개발 편의) | Lead Developer/QA |
| D21 | 접근 모델 이원화(게이트 vs 가입) | `_slide_access_allowed`는 `institution_subject_access.granted=TRUE` **OR** 접근창 active 구독을 보나, register·_authenticate·포털 sync는 **구독만** 본다(Gemini). 정상 운영에선 구독 생성 시 access를 함께 INSERT해 불일치 없으나 granted-OR 가지가 잉여(dead branch). 구독 단일화로 게이트 정리 검토. **별도 §12 세션.** | 🟠 v1.5/별건 | Lead Developer |
| D22 | 좌석 mutex tie(동시성 코너) | 같은 (기관×과목)에 접근창 겹치는 active 구독 2개+이고 `subscription_end` 동률이면 FOR UPDATE가 `ORDER BY subscription_end DESC LIMIT 1`로 다른 행을 잠가 마지막 좌석 중복 통과 여지(Codex). 정상 운영 미발생(과목당 구독 1개). 7월말 Locust(D14) 검증 대상. | 🟡 추적(D14) | Lead Developer/QA |
| D24 | 라이브 DB 잔재 정리 | 2026-06 스모크 발견: ① HS-PATH-004/005/006(옛 MVP 잔재, HS- 접두사로 SA 단일채번 위반) ② 'TEST'(title_ko='x') 쓰레기 행 ③ SA-HST-0001 conversion_status=pending·deploy_status=qc_pending. HST 134종 입고 시 정돈, 삭제·재채번은 CEO 판단(콘텐츠 손실 주의). | 🔴 출시 전 | CEO |

**✅ v3.1에서 닫힌 항목 (Codex 묶음 A·B, pytest 65/65)** — 표에서 별도 행 불요:
- #1 SA 슬라이드 접근 / #2 과목 IDOR → 단일 게이트로 통합·기관일치 화석 제거(db6a1ae). #3 접근창 집행(01ab005) / #5 특별계정 만료 집행(2c21b81). #6 ADMIN_SECRET_KEY fail-closed / #4 구독 없는 가입·인증 거부(70dbfee).
- 2-2#3 문의답변 answered 금지+헤더/HTML 방어(57a5169) / 2-2#4 XLSX 수식 주입 방어(06c50b9) / 2-2#5 admin XSS escaping(202d598) / 2-2#2 타일토큰 무중단 재발급(24325ec). 묶음 A 전: FAIL1 만료 fail-closed(0a34592) / WARN2 roster is_verified 과목 한정(087895c).

---

## 19. 인프라 접속 정보

### RDS PostgreSQL
- 엔드포인트: `slideatlas-db.c94iwikwox6l.ap-northeast-2.rds.amazonaws.com` | DB/유저/포트: slideatlas / slideatlas_admin / 5432 | 리전/AZ: ap-northeast-2 / 2c
- 접속: EC2 Instance Connect → psql(로컬 불필요). SG는 EC2 IP만 인바운드(VPC 내부 전용).

### EC2 SSH (Windows)
- 고정 IP(EIP): 3.34.35.58 | PEM: `C:\Users\아무개\slideatlas-key.pem` | 명령: `ssh -i "...\slideatlas-key.pem" ubuntu@3.34.35.58` | **비관리자 PowerShell**.

> ⚠ RDS는 VPC 프라이빗, 같은 VPC EC2만 접속(외부·Render 직접 불가). 앱 정식 구동 위치는 EC2 — §18 D16.

---

## 20. 환경·인프라 점검 (코드 검증 사각지대 — 별도 문서 포인터)

> **본문은 `docs/INFRA_CHECKLIST.md`(운영 매뉴얼급)에 있다. 이 섹션은 요약·포인터이며, 인프라 영역에서 본 문서와 충돌 시 `INFRA_CHECKLIST.md`가 우선한다.**

**왜 별도 문서인가 (핵심 원칙)**: Codex·Gemini·Claude QA(§12)는 **git 코드만** 본다. 코드 추론 결함(IDOR·인증 우회·권한 게이트·SQL)은 잘 잡지만, **git 밖 — 환경변수 실제값, 인프라(systemd·nginx·TLS·보안그룹·DNS·S3), 라이브 DB 상태, 배포 환경 — 은 구조적으로 못 본다.**

> ★ **실제 사고(2026-06)**: JWT_SECRET_KEY가 Render 미설정인데 외부검증 다 돌려도 못 잡음(코드엔 결함 없음 — 환경변수 *읽는 법*만 알 뿐 *실재*는 모름). 어드민 해시 잘림·reboot 후 타일서버 미기동도 동류. → **"코드가 맞다 ≠ 배포가 맞다."**

**검증 책임 분리**: 코드 로직 → Codex·Gemini·Claude QA(§12) / 환경변수·인프라·라이브 데이터·배포 → **사람이 `INFRA_CHECKLIST.md`로 점검**(AI 대체 불가) / 부하 → Locust(§18 D14).

**INFRA_CHECKLIST.md 구성**: A 사각지대 개념지도 / B 런칭 전 체크리스트(환경변수·자동기동·TLS·DNS·RDS·S3·라이브데이터·옛서버제거·스모크) / C 정기점검 / D 사고대응 Runbook / E 책임경계 / F 부록.

**운영 규칙**: Codex/Gemini가 OK해도 **B절 통과 못 하면 런칭 금지**. 인프라 명령은 EC2에서 **CEO 직접 실행**(AI SSH 금지, §12). B절은 "AI 확인"으로 대체 불가 — **명령 출력을 사람 눈으로 대조**. 관련: §12·§18(D2·D3·D4b·D14·D16)·§19.

---

## 21. 교수 수업 페이지(LMS) — v1.0 정식 범위

> **포지셔닝**: "땡시 대비, 집에서 한국어로." Histology Guide류(영어·무료) 대비 차별점은
> **한국어 + 국가고시 연계 + 교수 지정 커리큘럼**이다. LMS가 v1.0의 핵심 과금 근거다.

### 21-1. 모델 (지위 ⊥ 역할 — 두 별개 축)
- **지위(position) 4개**: 교수/조교/학생/행정직원(roster에 기관 관리자가 등록). **역할(role) 2개**: `viewer`/`admin`. **별개의 두 축.**
- **admin은 별도 지위가 아니라 4개 지위 누구에게나 얹히는 플래그**(겸직, §6-4).
- **행정직원**: 슬라이드 열람·즐겨찾기·좌석 **제외**(좌석 0, 콘텐츠 비소비). admin 얹히면 roster 관리·리포트만. subject 행 없이 admin-only(position NULL)로 표현.
- **슬라이드 접근은 과목 구독만**(§8). **수업은 접근 게이트가 아니라 학습 경로** — 미등록이어도 구독 과목 슬라이드 전체 열람 가능.

### 21-2. 수업 구조
- 수업은 **특정 과목(`subject_code`) 안에서만** 개설, **수업=페이지 1개**. 구조 **수업→주차→슬라이드**(추가 계층 없음). 주차 자유 구성, **빈 주차 허용 + 사유 메모**(`empty_reason`).

### 21-3. 권한표
| 작업 | 학생 | 조교 | 교수 | 행정직원 |
|------|------|------|------|----------|
| 슬라이드 열람 | ✅ | ✅ | ✅ | ❌ |
| 즐겨찾기 | ✅ | ✅ | ✅ | ❌ |
| 수업 목록 열람 | ✅ | ✅ | ✅ | — |
| 수업 등록/해지 | ✅ | ✅ | — | — |
| 수업 개설 | ❌ | ✅(위임 시) | ✅ | ❌ |
| 주차 추가/삭제 | ❌ | ✅(위임 시) | ✅ | ❌ |
| 슬라이드 배치 | ❌ | ✅(위임 시) | ✅ | ❌ |
| 조교 지정 | ❌ | ❌ | ✅ | ❌ |
| 수업 삭제 | ❌ | ❌ | ✅ | ❌ |
| roster 관리·리포트 | (admin 시) | (admin 시) | (admin 시) | (admin 시) |

> ★ **기능 권한 분기는 `role`이 아니라 `position` 기반**(수업 개설=position∈{교수,조교}). `role`은 포털 접근(viewer/admin)만 가르며, roster 관리·리포트만 role='admin'에 종속.

### 21-4. 교수/조교 편집 화면
- **수업 개설 모달**: 수업명+과목+학기. 개설 즉시 **같은 기관 해당 과목 구독 학생에 노출**.
- **조교 지정**: 수업별 위임, `position='조교'`만 검색 노출(지정자 비활성).
- **주차 관리**: 추가/삭제/펼침·접힘, 빈 주차 사유 메모. **슬라이드 배치**: 주차 "+" → 선택 모달(체크박스 다중, 이름/ID 검색, **중복 허용**).

### 21-5. 학생 수업 탭
- **내 수업**: 등록 목록 + "해지". **전체 수업**: 기관 공개 수업 + "등록"(등록된 건 뱃지·비활성). **승인 불필요**(자유 등록). 한 학생 **여러 수업 가능**(`course_enrollments` 다대다, 과목 구독과 별개 축).

### 21-6. 수업 접근 범위
- 노출 대상 = **그 과목 구독 기관의 그 과목 좌석 viewer**(기관 전체가 아니라 과목 단위).

### 21-7. 즐겨찾기 vs 수강
- **즐겨찾기(★)**: 개인 북마크(`favorites`, 수업 무관). **수강**: 수업 등록→주차 커리큘럼(`course_enrollments`).

### 21-8. 마이페이지
- 프로필(이름·이메일·소속·지위 — **소속/지위 읽기전용**)·비밀번호 변경·즐겨찾기·열람 기록.

### 21-9. 스키마·마이그레이션
- 테이블: course_* 6개(§7) + `users.position` + `users.role` 기본 `viewer`. 마이그레이션: `db/lms_and_viewer_role_migration.sql`(멱등·트랜잭션, **실행은 CEO가 EC2에서 직접** — §12·§20).

---

## 버전 이력 (요약 — 각 버전의 핵심 변경만)

- **v3.0**: 과목/좌석 분리 골격(§0). 구독·좌석·만료·접근이 (기관×과목) 단위 독립.
- **v3.1** (Codex 묶음 A·B, pytest 65/65): 단일 게이트(`_slide_access_allowed`)·기관일치 화석 제거 / 온보딩 구독 선행(SUBSCRIPTION_INACTIVE) / 접근창(KST) fail-closed / 특별계정 만료·ADMIN_SECRET_KEY fail-closed·타일토큰 무중단 재발급·문의답변/XLSX/XSS 방어. D3·D10 완료.
- **v3.2**: §20 신설(인프라 점검 — docs/INFRA_CHECKLIST.md)·어드민 세션 DB대조·잠금. 계기: JWT_SECRET_KEY 미설정 등 코드검증 사각 사고.
- **v3.3**: LMS 섹션 복원·role student→viewer·가입 두 트랙·courses 외 6테이블 추가.
- **v3.4**: §6-4 position 단일 출처(subject roster 행)·institution_rosters.position 컬럼(bf777d3)·행정직원=admin-only. 가입 폼 이름칸 제거(표시명=roster.name)·register 두 트랙 재구성·공개 드롭다운·에러코드 정렬(pytest 101).
- **v3.5**: 구독/좌석 면제 기준 role→subject_code 4경로(register·verify·login·_authenticate) 일관화(pytest 109). D17 신설.
- **v3.6**: D18 신설(institutions 고객/소유자/공급사 혼재). §6-1 공급사=license_source 비공개 명시.
- **v3.7**: e2e 발견 — D2(인증메일 미발송, 출시 블로커) 보강·D17 보강·D18 재설계(is_subscribable 플래그→구독 존재 여부)·D19·D20 신설.
- **v3.8**: 포털 P1(명단 관리) 구현 + D18 드롭다운=구독 보유 기관(JOIN subscriptions). D17 ✅ `_sync_member` 해결. 공통 헬퍼(`active_window_subscription`/`active_seat_count`) 추출(§0). pytest 127, security-reviewer FAIL 0.
- **v3.9** (포털 P1 외부검증 Codex+Gemini): IDOR 차단·저장형 XSS 차단·seat_full skip·xlsx 안전 파싱·겸직 is_verified 두 행 갱신. D21·D22 신설, D13 과목이동 2단계. pytest 149. 2차: 좌석 캐시 active 기준 일치·xlsx entry 상한 완화(pytest 152).
- **v3.10**: P1 라이브 스모크(분기 A 통과) 기록 + D24 신설 + D20 보강.
- **v3.11**: CLAUDE.md 압축(내용 보존·표현 축약, 40k 한도 대응). 규칙·결정·부채 행 불변, 표현만 요약.
- **v3.12**: 포털 P2(구독 플랜) 구현 — 읽기 전용 래퍼 3개(plans·plans/slides·export). §0 단일 진실(subscriptions·active_seat_count), 스코프 격리(g.institution_id), /viewer 표준 게이트 비우회, 전 slides 경로 과목격리(비구독 403), 내보내기 _xlsx_safe(xlsx·csv)·PDF=client print. 내부 QA(a·b·c+과목격리). pytest 168.
