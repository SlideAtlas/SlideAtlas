# CLAUDE.md — SlideAtlas 프로젝트 메모리 v3.22

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

**제품**: SlideAtlas | **운영사**: 아틀라스랩(Atlas Lab Co., Ltd.) | **대표**: 김보람 | **URL**: www.slide-atlas.net(공식) | **도메인**: atlaslab.co.kr(가비아) | **이메일**: boram@atlaslab.co.kr

**한 줄 정의**: 의·치·수의·한의·약·간호대 대상 디지털 병리/조직학 WSI(Whole Slide Image) 구독 SaaS.

**비즈니스 모델**: 오프라인 슬라이드 납품(보람바이오텍: 1985년 설립, 2006년부터 Ward's Science 현미경 슬라이드 수입·판매 — 회사 약 40년·슬라이드 사업 약 20년) 네트워크를 디지털 구독 SaaS로 전환. **좌석 플랜 기반 학기 단위 구독**, 장비 불필요(경쟁사 대비 차별점).

**경쟁 구도 — 최대 도전**: 진짜 경쟁자는 장비형(WinMedic 등)이 아니라 **Histology Guide(영어·무료, 우수 품질 ~300종)**. 종류·품질 다 앞서는 무료 디지털 슬라이드를 두고 **유료 구독을 어떻게 정당화하느냐가 SlideAtlas 전반의 핵심 challenge.** 차별점 베팅 = **LMS(한국어 + 국가고시 연계 + 교수 지정 커리큘럼, §21)** — 이 베팅이 먹히는지는 **7~8월 영업으로 판가름.** (WinMedic 대비 '장비 불필요 콘텐츠 SaaS' 구분은 부차적.)

> **장기 해자(moat)**: 복제 가능한 LMS·가격을 넘어, normal-abnormal 연동·희귀표본 등 **복제 불가능한 콘텐츠 자산**으로 이동. v1.5 PATH 연동이 그 첫 수(범문/대한해부학회가 가격·LMS는 따라와도 연동 콘텐츠·라이브러리는 구조적으로 못 따라옴).

---

## 2. 버전별 개발 로드맵

### v1.0 — 한국 런칭 (2026년 9월 목표)
- **타겟**: 국내 지방의대·수의대·약대·한의대·보건대. **콘텐츠**: 아틀라스랩 직접 라이선스만(교수 업로드 없음). **AI 튜터**: 슬라이드 메타데이터 + `knowledge_base` JSON → Claude API(VectorDB 없음).
- **모듈**: **조직학(HST) 단일**(*판매 과목 하나뿐*, 코드·구독은 다과목 일급 §0). 병리·기생충 v1.5+. **구독**: (기관×과목) 단위, 좌석 플랜 × 학기(§16).
- **LMS**(수업 개설·주차 배치·수강·즐겨찾기): **v1.0 정식 범위·핵심 과금 차별점**(한국어+국가고시+교수 커리큘럼, §21). **모바일**: 반응형 웹. **마일스톤**: 9월 가을 2~3개교 → 초창패 추경.

### v1.5 — PATH 연동·콘텐츠 확장 (HST 구독 학교 확인 즉시 착수)
- **헤드라인 = HST↔PATH normal-abnormal 연동.** 같은 장기의 정상(HST)↔병변(PATH) 슬라이드를 연결해 비교 학습 제공 — e-Histology류 자가학습 콘텐츠가 구조적으로 못 따라오는 핵심 차별점(§1, 원광대 교수 요청 반영). **트리거: HST v1.0에서 실제 구독 학교가 나오면 즉시 PATH 모듈 착수**(시장 검증 후 집행, §13-1).
- PATH 모듈 활성(`subject_codes.PATH.is_active=TRUE`) + PATH 콘텐츠 라이선스/스캔, Mahidol 라이선스, 자문 교수 1인→kb 검수, 10~15개교, §18 부채 정리(옛 구독 컬럼 DROP 등).
- **연동은 추가(additive) 작업** — §0 다과목 구조 덕에 구독·좌석·접근은 무변경, 신규는 슬라이드 연결 레이어(`slide_links`, §7·§18 D29)뿐. **§8 단일 게이트가 과목별 접근을 그대로 강제하므로 교차과목 연동은 '포인터+업셀'이지 접근 구멍이 아님** — HST 단독 구독 학교는 병변 비교본 *존재*를 보되 PATH 미구독이면 열람 불가 → 자연 업셀.

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
| 배포 | AWS EC2 (gunicorn + systemd + nginx + TLS). Render 폐기 완료(2026-06) — §18 D16 |
| 저장소 | AWS S3 (ap-northeast-2, 버킷: slideatlas-slides) |
| 타일서버 | AWS EC2 t3.medium (slideatlas-tileserver, EIP 3.34.35.58) — 동적 워터마킹 (~$40/월) |
| 타일엔진 | titiler + 커스텀 타일서버 (~/tileserver/main.py, rasterio) |
| 파이프라인 | SVS/DCM/TIFF/NDPI/VSI → COG TIFF → S3 → titiler |
| 데이터 관리 | RDS PostgreSQL (slideatlas-db, ap-northeast-2c), 주요 마이그레이션 적용·검증 완료(잔여 §18 D1·D5·D12) |
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
   → (대량 약 138종) kb 초안 엑셀 내보내기 → 검수자 일괄 보완 → 일괄 반영(엑셀) → 일괄 배포
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
-- subject_codes: code VARCHAR(10) PK('HST'..), name_ko, name_en, created_at. ⚠ is_active(모듈 활성 플래그)는 **v1.5 신설 예정(D29)** — 현재 DB 미존재(schema.sql에 컬럼 없음). v1.0은 코드 미참조.

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

-- > **v1.5 PATH 연동 선설계 (v3.19)**: normal-abnormal 연동은 '같은 장기, 다른 상태'가 본질이므로 **연결 앵커 = `organ`**. 따라서 v1.0에서 `organ`을 자유텍스트가 아닌 **통제 어휘로 정규화**한다(`organs` 참조 테이블 + `slides.organ_code`, §18 D28) — 138종 HST를 정규 organ_code로 적재. 연동 자체(`slide_links`)는 기존 테이블 무변경의 **순수 additive**라 v1.5로 이연하되 설계만 고정(§18 D29). ⇒ "지금부터 PATH 염두 설계"의 실제 v1.0 작업량은 **organ 정규화 한 가지**로 수렴.

-- organs (v1.0 신설, §18 D28): organ_code VARCHAR(20) PK, name_ko, name_en, organ_system VARCHAR(40)(계통: 소화기/순환기/호흡기 등 — ★'organ AS system' 별칭 충돌 피해 organ_system으로 명명), display_order INT, is_active BOOLEAN DEFAULT TRUE, created_at
--   ★ slides.organ_code VARCHAR(20) REFERENCES organs(organ_code) 추가(nullable로 시작). 기존 자유텍스트 organ은 표시/마이그레이션 대조용 유지 후 v1.5 정리.
--   ★ 배치 업로드(§5-1) 엑셀·개별 추가(§5-2)·QC 모달에서 organ_code 드롭다운으로 캡처.

-- slide_links (v1.5 신설·설계고정, §18 D29 — v1.0 미구현, additive 마이그레이션):
--   id SERIAL PK, primary_slide_id VARCHAR REFERENCES slides(id)(정상/기준), related_slide_id VARCHAR REFERENCES slides(id)(병변/비교),
--   link_type VARCHAR(30)('normal_abnormal'; 확장: 'stain_variant' 등), organ_code VARCHAR(20) REFERENCES organs(organ_code)(공유 앵커),
--   note_ko TEXT(교육 설명), display_order INT, created_by INT REFERENCES admin_users(id), created_at TIMESTAMP DEFAULT NOW()
--   · 1정상↔다병변 지원(다중 행), 방향성(primary=정상).
--   · ★ 접근은 §8 단일 게이트 불변 — 링크는 포인터일 뿐, related 슬라이드 열람은 그 과목(PATH) 구독 필요(포인터+업셀).

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
- **★ 엑셀 양식 다운로드 (✅ 구현, v3.22)**: `GET /portal/api/roster/template?format=xlsx|csv` (`@login_required`+`_portal_guard`, scope=`g.institution_id`). 업로드 전 빈 양식을 받아 형식 오류를 줄인다. 헤더는 **단일 상수 `_PORTAL_ROSTER_HEADER`(이름|지위|과목|이메일)** 로 업로드 파서와 **글자단위 일치** — 생성물을 그대로 재업로드하면 헤더 자동 스킵·예시행만 남음(양식↔파서 round-trip 안전, 자기 양식을 거부하지 않음). 지위 안내=**학생/조교/교수**(행정직원은 admin-only라 제외 + "관리자로 등록" 별도 안내). 과목 안내=**`_subscribed_subjects` 동적**(그 기관 구독 과목만, scope 격리, 구독0 graceful). 예시행(코멘트)+별도 '안내' 시트, 모든 셀 **`_xlsx_safe`**(수식주입 방어 §8·D9). 화면=명단 탭 "양식 다운로드" 버튼(GET 다운로드, P2 export 동일 패턴). ★ **이 기능은 본 사양서가 1차 — 향후 포털 목업 재제작 시 누락 방지**(§17 "목업 충돌 시 본 문서 우선").
- **★ 성능 단계1 — 중복 admin 조회 제거 (✅ 구현, v3.22, 커밋 `d1530af`)**: 한 요청에서 `__ADMIN__` roster 존재를 `_authenticate`와 `_is_institution_admin`이 **2회 조회**하던 것을, `_authenticate`가 1회 조회→`g._admin_roster_cache`(요청 스코프: user_id+본인 institution_id+bool) 적재 → `_is_institution_admin`이 캐시 키 일치 시 재사용, 불일치/부재 시 폴백 조회. ★ **요청 스코프 한정이라 §8 DB 권위(매 요청 재조회) 불변 — roster 회수 즉시 반영**(같은 요청 내 중복만 제거). **판정 의미·반환 shape 불변(§13-2)**, 외부검증 통과(pytest 293). 인덱스 `db/portal_perf_indexes.sql`(CEO EC2 적용): `users(lower(email))`·`institution_rosters(lower(email))` 함수형 + `subscriptions(institution_id,subject_code,status)` 복합 — `lower(email)` 조인 seq scan 해소.

**포털 P2 — 구독 플랜 (✅ 구현, v3.12, 읽기 전용)**
- 라우트(전부 `@login_required`+`_portal_guard`, GET): `GET /portal/api/plans`(구독 카드+좌석현황) / `GET /portal/api/plans/slides?subject_code=`(과목 배포 슬라이드 메타) / `GET /portal/api/plans/slides/export?subject_code=&format=xlsx|csv`(내보내기). 화면 `templates/portal.html` `#panel-plan`(P1과 동일 standalone+interceptor.js, esc() XSS).
- **슈퍼관리자 엔드포인트 직접 호출 안 함** — 포털 전용 읽기 래퍼. SQL·헬퍼만 재사용.
- **단일 진실(§0)**: 구독 카드는 `subscriptions`(기관×과목)만, `institutions` 옛 구독 컬럼 0건. 좌석 현황 = `active_seat_count`(status='active', P1·리포트와 동일 단일판정식, pending 미점유). 접근창·만료·D-day = 기존 `_sub_status`/`_sem_dates` 재사용(신규 계산식 없음).
- **스코프 격리(§9)**: scope는 `g.institution_id` 강제 — inst_id를 body/쿼리로 안 받음(IDOR 불가).
- **슬라이드 목록**: 그 과목 `deploy_status='deployed'` 메타데이터 카탈로그(ID·제목·과목·염색)만, 타일·토큰 발급 없음. "열람"은 `/viewer/<id>` 이동 → **표준 `_slide_access_allowed` 게이트가 판정**(포털이 게이트 우회 안 함, 관리자도 과목 좌석 필요).
- **과목 격리(전 slides 경로)**: 목록·export 모두 `_subscribed_subjects` allowlist — 비구독 `subject_code`는 빈 목록 아닌 **403(SUBJECT_NOT_SUBSCRIBED)**.
- **내보내기 수식주입 방어**: XLSX(openpyxl)·CSV(BOM) 모든 셀 `_xlsx_safe` 재사용(§8·§18 D9). PDF는 클라이언트 `window.print()`(한국어 폰트 reportlab 한계 §13-1 회피).
- 내부 QA(읽기라 §12 외부검증 대신 Claude Code 내부): (a)스코프격리 (b)/viewer 우회없음 (c)수식주입 방어 (+)전 slides 경로 과목격리 — pytest 168(P2 16 추가).

**포털 P3 — 이용 리포트 (✅ 구현, v3.13, 읽기 전용 — 포털 3탭 완성)**
- 라우트(전부 `@login_required`+`_portal_guard`, GET): `GET /portal/api/report?period=&subject_code=`(KPI·구성원활동·월별조회·Top10·AI월별 통합 1응답) / `GET /portal/api/report/export?...&format=xlsx`(XLSX). 화면 `templates/portal.html` `#panel-report`(P1·P2와 동일 standalone+interceptor.js, esc() XSS). 기간=1m/3m/6m/all, 과목=all(기관 합산)/특정.
- **슈퍼관리자 reports 엔드포인트 직접 호출 안 함** — SQL·집계 로직만 재사용. **학교 선택 드롭다운 없음**(자기 기관 고정, 슈퍼관리자와 차이).
- **단일 진실(§0)**: 집계 원천 = `access_logs`·`chat_logs`·`users`·`subscriptions`만(`institutions` 옛 컬럼 0건). '활성 사용자' = `status='active'`(P1·P2·`active_seat_count` 일치). util·per_user 0나눗셈 가드.
- **스코프 격리(§9)**: `g.institution_id` 강제, inst_id를 body/쿼리로 안 받음(IDOR 불가).
- **과목 격리**: `subject_code`='all'(구독과목 합산) 또는 `_subscribed_subjects` 중 하나 — 비구독은 **403**(report·export 공통).
- **과목축 분리→기관 롤업(§18 D9)**: active_users·max_seats·소진율을 (기관×과목)으로 산출, 'all'은 과목별 합(SUM, 단일 사용자=단일 subject_code라 중복 없음). 구성원 활동은 status 기반(활성=active/미인증=pending/비활성=그외+NULL).
- **빈 데이터 graceful**: 로그 0이어도 0·빈 배열·"데이터 없음" 표시, 'all'+구독0은 `_empty_report`로 ANY(빈배열) 회피, chat_logs 부재 시 AI만 0/[]로 격리(다른 집계 보존).
- **내보내기**: XLSX(openpyxl, 전 셀 `_xlsx_safe`)·PDF는 `window.print()`(서버 PDF 금지 §13-1).
- **★ 외부검증(Codex+Gemini) 반영 (v3.14)**:
  - **조회수 = access_logs 스냅샷 기준**(High#1): total_views·monthly·top_slides 는 `al.institution_id`·`al.subject_code`(열람 시점 스냅샷)로 필터. JOIN users/slides 현재값으로 거르면 사용자/슬라이드 과목 이동 시 과거 로그 재분류(시간축 오염). slides 조인은 Top10 제목·염색 표시용만. (chat_logs 는 이미 `cl.*` 스냅샷.)
  - **활성 = `status='active'`(NULL 제외)**(Med#2 §0): COALESCE 제거 — `active_seat_count`와 정확히 일치(P2 좌석↔P3 활성 모순 제거). NULL 은 비활성. 근본해결로 `users.status NOT NULL` 마이그레이션(`db/users_status_notnull_migration.sql`, CEO 실행, §18 D25).
  - **max_seats 합산 접근창 필터**(Med#3): `SUM(max_seats)`에 `access_open_date<=today<=subscription_end`(today=`_today_kst`) 추가 — 미래 갱신 구독 합산(150+150=300) 차단. ★ `active_seat_count`(점유)는 불변, 정원 합산만. (P2 카드는 구독 행별 개별표시라 SUM 없음 — status_key로 현재/미래/만료 구분, 변경 불요.)
  - **타임존 `_today_kst` 일괄**(item4): P2·P3 대시보드 날짜연산을 게이트와 동일 KST로 — `_sub_status`(P2 카드·슈퍼관리자 기관목록 공유)·`portal_plans_list` D-day·`_portal_report_range`·관리자 dday. 날짜 경계 `>= start AND < end+1day`(half-open). 새 헬퍼 없이 기존 `_today_kst` 재사용(§18 D10 대시보드까지 확장).
  - **period allowlist**(Low item5): `{'1m','3m','6m','all'}` 외엔 조용히 전체확장 않고 기본 '3m'(`_norm_report_period`).
- 내부 QA(a)스코프격리 (b)과목격리(비구독 403) (c)수식주입 방어 (d)집계 과목별 산출→롤업 (+)빈데이터 graceful — pytest 196(P3 15 + 외부검증반영 13). **포털 3탭(P1·P2·P3) 완성.**
- **★ 재검증 2R(Codex) 반영 (v3.15)**:
  - **is_special 좌석 정합(§0 같은 집합)**: `active_seat_count`(is_special 절 없음, subject_code 매칭)와 P3 active를 '글자까지 같은 집합'으로 — **특별계정은 승격 시 `subject_code=NULL`(+position NULL)로 정리**(좌석 비점유, CEO 결정). `api_special_accounts_create` 수정 + 기존 잔존 정리 `db/special_subject_code_cleanup_migration.sql`(CEO 실행). P3 users 집계의 `is_special` 제외절 제거(subject_code=NULL로 자연 제외) → P2 좌석↔P3 활성 동일 증감.
  - **소진율 분자=분모 같은 행 집합(기준 A)**: 분모(max_seats 합산)뿐 아니라 **분자(active_users)도 현재 접근창 열린 active 구독 과목(`window_codes`)만** 본다. 만료 과목의 active 사용자는 `_authenticate`가 이미 차단한 유령 → 분자에서도 제외(N명/0석 "0% 소진" 왜곡 제거). 접근창 닫힌 과목은 분자·분모 양쪽에서 빠짐(집계 제외). 구성원 활동(donut)도 window_codes 기준. 등록 이용자(총원)는 전체 구독 과목 기준(별도 KPI). ★ `active_seat_count`는 불변.
  - **top_slides LEFT JOIN**: `JOIN`→`LEFT JOIN slides` + 제목 `COALESCE(s.title_ko, al.slide_id)` — slides 행 부재/깨진 참조여도 total/monthly와 같은 기준으로 집계(표시용 조인이 집계 떨구지 않게).
  - **스냅샷 subject_code NULL 과거 로그**: `al.subject_code IS NULL`인 과거 로그는 `=ANY()`에서 빠져 'all' 집계에서 과소(누수 아님). **의도적 집계 제외(과목 귀속 불명)** — 백필 안 함(§15-7 명문화).
- pytest 202(2R 6 추가). 본 수정분(is_special 정리 후 P2=P3 같은 집합·소진율 분자/분모 같은 행집합) 인접 경로 한정 Codex 재확인 → CEO 승인.

---

## 10. AI 튜터 구조 (v1.0)

VectorDB 없이 `knowledge_base` JSON + 슬라이드 메타데이터만으로 Claude API 호출. v2.0은 system_prompt에 Vector DB 검색 결과만 추가하면 RAG 전환(나머지 무변경).

> ⚠ **현황(QA)**: api_chat 항상 스트리밍 반환→퀴즈(startQuiz) 파싱 실패→폴백 퀴즈, 실제 생성 미완(§18 D6).

---

## 11. 콘텐츠 현황 (v3.17 — 공급사·조달 확정)

**조달 확정: 물리슬라이드 구매 → 뷰웍스 일괄 스캔.** 디지털 SVS 라이선스 아닌 물리 구매·직접 스캔(사유: 비용 우위·원본 확보·**MPP·품질 직접 통제**·짧은 리드타임).

**공급사 확정: Yulin 메인.** Yulin 134종 구매 오더 완료, Yulin 미보유 4종은 Vic에서 보완 구매 → **9월 런칭 잠정 138종**. (143 목표 중 138 확보, 미확보 5종은 v1.0 제외.) 보류: Happy Science(SVS, 글로벌 백업 옵션). 스캔: 뷰웍스(장당 1만원+VAT). MVP용: TCGA/3DHISTECH 샘플.

**저작권/공급사 관계(CEO 원칙)**: 우회 없이 디지털 라이선스 가치 설명 + **연 라이선스비 선제안**. 1년차 물리 구매 갈음, 2년차부터 연 라이선스. 목적: 분쟁 예방 + 장기 신뢰.

**미확보 슬라이드**: 중국 공급사 조달 불가분 **v1.0 제외**(예: brown adipose tissue — Ward's Science만, 향후 보충). v1.0 목표 = 138종 스캔 완료분. **일정**: 송금·구매 완료 → 뷰웍스 스캔.

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

- Yulin(율린): Jessy, Cathy — **메인 공급사 확정**(134종 오더) / Vic Science: Joy Xu joy@vicscience.com — **Yulin 미보유 4종 보완 구매**
- Happy Science: Mallen Zhang info@ihappysci.com(보류, 글로벌 백업) / 뷰웍스: 스캔 서비스(장당 1만원+VAT) / 성원애드피아: 명함

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
- **기관 × 모듈 매트릭스**: 조직학 전 기관 자동·잠김, 병리·기생충 출시 후 토글. 기관 추가 시 행 자동 생성, **2번째 모듈 시점 구현**(v1.0 미리보기). ⚠ 모듈 활성 진실은 `subject_codes.is_active`(DB) — **단 이 컬럼은 v1.5 신설 예정(D29), 현재 DB 미존재**. 신설 시 코드 상수와 단일화.

### 15-7. 이용 리포트
- 포털 리포트와 동일 화면 + **학교 선택 드롭다운**. **집계 과목별 → 기관 롤업**(개별 학생 추적 지양). 좌석 소진율 = 과목별 (활성/max_seats). 엑셀/PDF. ⚠ 문자열이 `=+-@`로 시작 시 CSV 수식 주입 → 셀 앞 이스케이프.
- **소진율 분자/분모 기준(기준 A, v3.15)**: 활성(분자)·정원(분모) 모두 **현재 접근창 열린 active 구독 과목만**(만료/미래 과목 제외 — 만료 과목 active 사용자는 접근 차단된 유령). 분자·분모가 같은 행집합. 활성 정의=`status='active'`(NULL 제외)=`active_seat_count` 같은 집합. **특별계정은 좌석 비점유**(승격 시 subject_code=NULL, §15-8).
- **분모 과목별 권위 row 정규화(v3.16, §0)**: 같은 (기관×과목)에 접근창 겹치는 active 구독이 2개+여도 분모는 **과목별 1개 row만**(인증 게이트 `active_window_subscription`의 `subscription_end DESC` 규칙을 `DISTINCT ON (subject_code) … ORDER BY subject_code, subscription_end DESC`로 재사용) 합산 — 중복 합산(150+150=300) 금지. 분모 과목집합·과목별 정원 = 분자(window_codes) = 인증 게이트 권위 구독, 셋이 같은 행집합. (동률 subscription_end 코너는 §18 D22 추적.)
- **★ 이용량 KPI vs 소진율 과목 집합 비대칭(설계 의도, v3.16 CEO 확정)**: **이용량 KPI(조회수·월별·Top·AI 호출)는 그 기관이 구독 보유한 과목 전체(만료 포함)를 집계** — 과거 이용 기록도 의미가 있으므로. **좌석 소진율(활성/정원)은 현재 접근창 열린 과목만** — 현재 정원 대비 점유 지표이므로. 두 KPI의 과목 집합이 다른 것은 의도이며 버그 아님(코드 불변).
- **조회수 스냅샷 집계(v3.14)**: 조회수는 `access_logs.institution_id·subject_code`(열람 시점 스냅샷)로 집계. ⚠ **스냅샷 컬럼이 NULL인 과거 로그(마이그레이션 이전)는 의도적으로 집계 제외**(과목 귀속 불명) — 백필하지 않음(과거 로그의 정확한 과목 귀속 불가, 누수 아닌 과소집계).

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

## 16. 가격·구독 모델 (v3.17)

- **좌석 플랜이 기본 가격축**: Department(50)/Standard(150)/Campus(300)/Institution(500+). 특수계약은 좌석 수 직접 지정.
- **학기 단위 라이선스**: 봄(3/1~8/31)/가을(9/1~익년 2월말), 6개월 단위. **방학 접근 허용**(복습 목적).
- **접근 오픈일 = 학기 시작 −30일**(봄 2/1, 가을 8/1; 편의, 라이선스 기간과 별개). 날짜 경계는 **KST 일관**(`_today_kst`, §18 D10). **접근창 집행**: 만료/가입 검사가 `access_open_date<=today<=subscription_end`를 본다(미래 학기 구독이 미리 active여도 창 전엔 불가, §8 Codex#3).
- **참고 가격(Standard 기준)**: 연 ₩4,000,000 / 학기 ₩2,500,000(학기 단가 할증으로 연납 유도). **그 외 플랜(Department/Campus/Institution) 가격은 추후 영업 시 확정.** 실제는 딜별.
- **최초 구독 할인 (정책 고민 중)**: early bird(선착순·기한 한정)가 아니라 **모든 최초 구독 학교 일괄 할인**으로 진입 장벽을 낮춘다. 의도 = 일단 진입해 실사용이 붙으면 정상가 원복 후에도 이탈하기 어렵다(lock-in). 할인율·원복 시점 미정.
- **베타·런칭 모델 (v3.1)**: **특정 학교 고정 아닌 "6개월 무료 → 구독 전환"**. 무료 기간도 (기관×과목) 구독 레코드(접근창·좌석)를 생성해야 학생이 가입·접근(§6-3). "확정 베타 파트너"로 문서 고정 안 함.
- **좌석⊥콘텐츠**: 좌석=규모·가격, 모듈=무엇을 여는가. **HST는 첫 런칭 과목일 뿐 자동/기본 제공 아님** — 다른 과목처럼 (기관×과목) 구독 필요(§6-1).
- **(기관×과목) 단위 독립**(§0; 예: 조직학 150석 + 기생충학 30석, 좌석·학기·구독료·갱신 따로). 정원 = subscriptions.max_seats(§13-2).
- **가격제는 모두 HST 단일 기준** — v1.5+ 신규 과목 플랜 가격(별도/번들/상위티어)은 출시 시점 결정.

---

## 17. 화면 사양서 (목업)

구현 1차 사양은 `docs/mockups/`의 HTML 목업(클릭 가능):
- `institution_modals.html` — 기관 추가/수정/갱신(과목별 구독 카드, 학기제)
- `slide_qc.html` — 슬라이드 QC/파이프라인(2축 상태, 배치 QC, 검수 kb, 반려, MPP 재처리, 개별 추가)
- `access_reports_special.html` — 접근 제어·이용 리포트·특별 계정 / `notices_inquiries.html` — 공지(보관함)·1:1 문의(권한 분리)
- `admin_integrated.html` — 통합 대시보드(IA) / `institution_portal.html` — 포털 /portal(명단·구독플랜·리포트 3탭)
- **LMS 목업 7종 (v3.21 추가, §21)**: `lms_student_home`·`lms_course_detail`·`lms_teacher_courses`·`lms_course_edit`·`lms_assistants`·`lms_course_dashboard`·`mypage`(`.html`) — 학생 수업 탭·수업 상세·교수 수업 목록·주차 구성·조교 지정·명단/익명집계 대시보드·마이페이지.

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
| D7 | 미니맵/썸네일 파이프라인 | §4-2 "S3 사전 생성" vs 현재 동적 생성. /minimap 라우트 부재. **v3.21 비고**: LMS 3단계-B 수업상세·마이페이지 슬라이드 카드는 실썸네일 대신 아이콘 플레이스홀더 사용(게이트 무관 표시 원칙) — 실썸네일은 게이트 통과 슬라이드 한정 토큰 발급으로 확장 가능. | 🟠 v1.5 전 | Lead Developer |
| D8 | 기관×모듈 매트릭스 | 2번째 모듈 시점 구현. subject_codes.is_active(DB) 단일 진실 — **단 is_active 컬럼은 v1.5 신설 예정(D29), 현재 DB 미존재**(schema.sql 미포함). | 🟠 2번째 모듈 시 | Lead Developer |
| D9 | 리포트 집계 과목별 산출 (Codex #7) | 이용 리포트는 과목별 산출→기관 롤업(§9·§15-7). **✅ 포털 P3(v3.13)에서 과목축 분리→기관 롤업 구현.** 잔여: 슈퍼관리자 리포트(§15-7)가 동일 집계 로직을 재사용하는지 확인. | ✅ 포털 해결 / 슈퍼관리자 확인 | Lead Developer |
| D10 | 날짜 타임존 일관성 | ✅ 인증·접근창·만료·가입(v3.1)에 더해 **포털 대시보드(P2 구독카드·D-day·`_sub_status`·P3 리포트 기간·관리자 dday)도 `_today_kst`(KST) 통일(v3.14)** — 자정~오전9시 게이트/대시보드 하루 어긋남 제거, 경계 half-open(`>=start AND <end+1d`). 잔여 추적 거의 소진. | 🟡 추적(대부분 완료) | Lead Developer |
| D11 | DB 커넥션 release 전수 | get_db_conn/release_db_conn 누수 전수 카운트 미완. **v3.22 비고**: 단계1에서 포털 명단 경로 RDS 왕복 5→감소(중복 admin 조회 제거), 단 한 요청 4 체크아웃 구조는 잔존 — 추가 최적화는 D14 Locust 시 측정 후 판단(D33). | 🟡 추적 | QA |
| D12 | 다중 과목 접근 (정책 확정 v3.2, Codex#3·Gemini#5) | ✅ 정책 확정: **이메일당 users 1계정, 과목 접근은 institution_rosters 행, users.email 전역 UNIQUE**(§6-2). register가 이메일 전역 검사로 중복 계정/pending 차단(앱 레이어). 잔여: ① DB 차원 email 전역 UNIQUE 제약(별도 마이그레이션) ② 단일 `users.subject_code` 게이트라 한 계정 다과목 동시 열람 미구현 — v1.5. (구분: 수업 다대다 등록은 `course_enrollments`로 v1.0 지원, 과목 구독과 별개 축 §21.) | 🟠 v1.5 전(정책 확정) | Lead Developer |
| D13 | 온보딩 순서 운영 체크리스트 | §6-3 순서(구독 계약·입금 → access/subscriptions 생성 → roster 등록 → 학생 가입)를 운영 절차로 문서·교육. 코드는 강제하나(SUBSCRIPTION_INACTIVE) ② 선행 누락 시 학생 가입 불가 → 사고 방지. **v3.9: 과목 이동 = 기존 명단 삭제 후 새 과목 추가(2단계, 자동 전환 없음 — D12).** | 🔴 출시 전 필수 | CEO/운영 |
| D14 | Locust 부하 테스트 (7월 말) | 표적: 동시 가입·로그인 시 `FOR UPDATE` 좌석 잠금(over-seating/데드락), 동시 타일 EC2 부하, 커넥션 풀 고갈(D11), 로그인 폭주 계정잠금. (타일 DB 병목은 v3.2 토큰 인증 분리로 해소 §8.) | 🟠 v1.5 전(7월 말) | Lead Developer/QA |
| D15 | 다중 기관 관리자 포털 접근 (Gemini#2) | 한 사람이 여러 기관 관리자면 포털 scope가 단일 기관(`g.institution_id`) 고정이라 갇힘. v1.0 밖(드묾). **v1.5: `/portal/<institution_id>` 또는 기관 선택 드롭다운.** | 🟡 v1.5 과제 | Lead Developer |
| D16 | EC2 정식 배포 이전 (9월 런칭 = EC2) | **✅ 완료(2026-06): AWS EC2 이전, gunicorn+systemd+nginx+TLS 구동, DNS를 EIP(3.34.35.58) 전환, Render 폐기, www.slide-atlas.net 확정.** TLS·nginx 등 실작동은 §20 INFRA_CHECKLIST B절로 사람이 실측 확인. | ✅ 완료(실측 §20) | CEO |
| D17 | 콘텐츠 비소비 관리자 역할 미커버 | 근본: '과목 roster 행 유무'가 좌석·지위·콘텐츠 소비를 묶어(§6-4) "명단 관리만 하는 교수/조교" 표현 못함(관리자 선가입 시 admin-only로 굳음). **✅ 해결(v3.8): 포털 P1 `_sync_member`가 명단 추가/업로드 시 기존 user의 position·subject_code 동기화(§9 — 좌석 재검사 FOR UPDATE, 다과목 보류 D12, 접근창 닫힘 보류, role 불변, 공통 헬퍼 §0, 제거 시 좌석 회수). 행정직원 회피책 불요화.** 잔여: 다과목 동시 active(D12) v1.5. | ✅ P1 해결 / 잔여 D12 | Lead Developer |
| D18 | institutions에 고객/소유자/공급사 혼재 | 공개 GET /api/institutions가 고객 학교+소유자(SA)+공급사를 모두 드롭다운 노출(is_subscribable 플래그안은 수동관리 부담 폐기). **✅ 해결(v3.8): 드롭다운 기준을 '구독 존재 여부'로 교체 — `JOIN subscriptions`(status 무관). SA·공급사 자동 제외, 새 학교 즉시 노출. is_subscribable 코드 참조 0건.** 잔여(v1.5): 컬럼 DROP + suppliers 테이블 분리 + license_source FK화. | 🟠 v1.5 잔여 ✅ 교체 완료 | Lead Developer |
| D19 | 발송 실패 시 가입 트랜잭션 정책 미정의 | register 메일 실패 시 users(pending)·email_verifications 잔존 → 반복 실패 시 pending 누적 + 재가입 EMAIL_EXISTS 교착 가능. 정책 미정((가)재발송/(나)롤백/(다)기존 pending 재발송 우회). D2와 묶임. | 🟠 v1.5 전(D2 후속) | Lead Developer |
| D20 | 현재-접근창 테스트 구독 생성 수단 부재(개발 편의) | 가을 런칭 기준이라 시작학기 선택지가 2026 가을부터·갱신은 다음 학기만 → '지금 접근창 열린' 테스트 구독을 UI로 못 만들어 psql로 access_open_date 임시 조정(e2e). **2026-06 스모크용으로 TEST 기관 HST access_open_date를 2026-06-04로 임시 조정 — 실데이터 전환 시 원복 검토.** | 🟡 추적(개발 편의) | Lead Developer/QA |
| D21 | 접근 모델 이원화(게이트 vs 가입) | `_slide_access_allowed`는 `institution_subject_access.granted=TRUE` **OR** 접근창 active 구독을 보나, register·_authenticate·포털 sync는 **구독만** 본다(Gemini). 정상 운영에선 구독 생성 시 access를 함께 INSERT해 불일치 없으나 granted-OR 가지가 잉여(dead branch). 구독 단일화로 게이트 정리 검토. **별도 §12 세션.** | 🟠 v1.5/별건 | Lead Developer |
| D22 | 좌석 mutex tie(동시성 코너) | 같은 (기관×과목)에 접근창 겹치는 active 구독 2개+이고 `subscription_end` 동률이면 FOR UPDATE가 `ORDER BY subscription_end DESC LIMIT 1`로 다른 행을 잠가 마지막 좌석 중복 통과 여지(Codex). 정상 운영 미발생(과목당 구독 1개). 7월말 Locust(D14) 검증 대상. | 🟡 추적(D14) | Lead Developer/QA |
| D24 | 라이브 DB 잔재 정리 | 2026-06 스모크 발견: ① HS-PATH-004/005/006(옛 MVP 잔재, HS- 접두사로 SA 단일채번 위반) ② 'TEST'(title_ko='x') 쓰레기 행 ③ SA-HST-0001 conversion_status=pending·deploy_status=qc_pending. HST 134종 입고 시 정돈, 삭제·재채번은 CEO 판단(콘텐츠 손실 주의). | 🔴 출시 전 | CEO |
| D25 | users.status NOT NULL 제약 | 외부검증 Med#2(§0): '활성'은 `active_seat_count`가 `status='active'`(NULL 제외)로 센다. 앱 레이어는 P3도 COALESCE 제거해 통일(v3.14). 근본해결로 `db/users_status_notnull_migration.sql`(멱등·트랜잭션: NULL 백필→DEFAULT→NOT NULL) **CEO가 EC2 psql 실행**(§12·§20). 실행 전엔 잔존 NULL status 행이 P3 비활성으로 분류될 수 있음(좌석엔 영향 없음 — active만 점유). | 🔴 출시 전(마이그레이션 작성 완료) | CEO 실행 |
| D25b | 특별계정 subject_code 정리 | 재검증 2R#1(§0): 특별계정은 좌석 비점유(CEO). 승격 코드는 subject_code=NULL 처리하나 코드 수정 이전 잔존 계정 정리용 `db/special_subject_code_cleanup_migration.sql`(멱등: is_special=TRUE AND subject_code IS NOT NULL → NULL). 작업자 RDS 조회 권한 없어 잔존 건수 미확인 → 멱등 정리로 양쪽 분기 안전 커버(0건이면 no-op). **CEO 실행**. 미실행 시 잔존 특별계정이 P2 좌석·P3 활성 양쪽에 동일 계상(여전히 일치, 다만 좌석 1 과점유). | 🔴 출시 전(작성 완료) | CEO 실행 |
| D26 | 슈퍼관리자 COALESCE(status) 잔재 | Gemini 발견(MD감사 세션): 슈퍼관리자 영역 `COALESCE(status,'active')` 잔존 — L2232 S5-1 대시보드 KPI / L3528 `/admin/api/reports/kpi` / L3723 리포트 엑셀 / L3842 특별계정 리스트(표시용·무해 가능). **포털(기관 관리자)엔 영향 없음**(슈퍼관리자 전용, 포털은 v3.14에서 status='active' 통일). §0 활성 정의 일관성 차원에서 CLAUDE.md 정합성 감사 세션 때 `status='active'`로 통일 검토 — 1·2·3은 집계라 슈퍼관리자 KPI 숫자 영향, 4는 표시용(감사 때 구분). | 🟡 MD감사 세션 | Lead Developer |
| D27 | 사용자 공통 마이페이지 미구현 | 프로필·비밀번호 변경·즐겨찾기·열람기록(§21-8). 포털 헤더 링크도 없음. **포털 P4 아님** — 포털은 3탭 완결(§9), 관리자 설정 탭 미설치 확정. 학생 e2e·즐겨찾기/열람기록 필요 시점에 함께 구현. | 🟠 학생 e2e 전 | Lead Developer |
| D28 | organ 통제어휘 정규화 (v1.0) | ✅ **구현·외부검증·라이브 배포 완료(2026-06-11)**: organs 테이블+slides.organ_code+FK+46종 시드(12계통) RDS 적용, 코드 배포(api_slide_add organ_code 필수·계통 드롭다운·GET /admin/api/organs·레거시 /admin/api/slide→410·fail-loud). Codex+Gemini 통과(650a5ee). 잔여: 138종 organ 시드 확정 + D24 잔재 6행(계통레벨 organ값, organ_code NULL) 정리 → 배치 적재(D30) 시. | ✅ 완료(잔여 D30) | Lead Developer |
| D29 | slide_links 연동 테이블 + PATH 활성 (v1.5) | 설계 고정(§7), additive 마이그레이션. §8 게이트 불변(포인터+업셀). HST 구독 학교 확인 즉시 착수. | 🟠 v1.5 | Lead Developer |
| D30 | §5-1 슬라이드 배치 메타 적재 미구현 | 138종을 organ_code 포함 일괄 적재하는 xlsx 파서 부재(현재 개별추가만; §5-1 문서는 양식만 기술). **런칭 크리티컬** — 138 입고·스캔 후 적재 경로 필요. 이때 organs 138 시드 확정(FK 통과 위해 138이 쓰는 organ_code 전부 시드) + D24 잔재 정리 동반. | 🔴 출시 전(다음 task) | Lead Developer |
| D31 | 학생 비밀번호 변경 API 부재 | 마이페이지(§21-8) 비번 폼이 표시용(토스트)+TODO 주석. 학생이 비밀번호 변경 불가 → 출시 전 필요. | 🔴 출시 전 | Lead Developer |
| D32 | 즐겨찾기 UI 토글 연결 | favorites API(GET/POST/DELETE)는 구현 완료(3단계-B). 뷰어·슬라이드 카드에서 ★ 누르는 UI 토글(API 호출 연결)만 미구현 → 뷰어 정교화 작업 때 함께. | 🟠 뷰어 작업 시 | Lead Developer |
| D33 | 포털 명단 단계2(커넥션 체크아웃 합치기) | 한 요청 4 getconn/putconn(체크아웃)을 줄이는 건 데코레이터 구조 변경이라 회귀 위험. 단계1(중복 admin 조회 제거 v3.22)로 RDS 왕복은 줄었으나 체크아웃 구조는 잔존(D11). D14 Locust 측정 후 필요 시 착수. | 🟡 D14 시 | Lead Developer |

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

> ⚠ **배포 디버전스 주의(2026-06-11)**: organ 배포 시 EC2 운영본이 main보다 ~4.5일(LMS+포털 전체)만큼 뒤처져 있던 게 발견됨 — 마이그레이션은 RDS에 선적용됐으나 코드 배포가 지연. git pull로 organ+LMS+포털 코드가 함께 첫 라이브 배포(RDS 스키마 선존재로 무사). 교훈: ① 같은 EC2/RDS에 두 작업 스트림(예: 동시 LMS 작업) 동시 배포·마이그레이션 금지 — 누가 어디까지 올렸는지 꼬임. ② 배포 전 라이브 RDS 스키마 vs 배포 코드 기대 스키마 대조(information_schema). ③ 작업 재개 시 main 기준 리베이스 필수.

---

## 21. 교수 수업 페이지(LMS) — v1.0 정식 범위

> **포지셔닝**: "땡시 대비, 집에서 한국어로." Histology Guide류(영어·무료) 대비 차별점은
> **한국어 + 국가고시 연계 + 교수 지정 커리큘럼**이다. LMS가 v1.0의 핵심 과금 근거다.

> **★ 구현 상태 (v3.21 — 스펙 → 구현 완료)**: 아래 §21 사양이 프론트·API로 구현됨. 외부검증(Codex+Gemini) 통과, pytest 276, **보호 게이트(`_slide_access_allowed`·`_visible_slides`·`_course_owner_or_assistant`·`auth`) 무수정**.
> - **교수/조교 프론트 4화면 (커밋 `43b3025`)**: `/teacher/courses`(수업 목록)·`/teacher/course/<cid>`(주차 구성)·`/assistants`(조교 지정)·`/dashboard`(명단+익명집계). 표시용 읽기 API 3(`available-slides`·`assistants`·`assistant-candidates`). **권한 분기 = position 기반**(§21-3) + `_course_owner_or_assistant` 재사용, **슬라이드 배치 과목 정합 가드**(`slide.subject_code == course.subject_code`), 조교 후보는 `status='active'`만.
> - **학생 프론트 3화면 (커밋 `24033c8`)**: `/home` 수업 탭(내 수업·개설 수업)·`/course/<cid>` 수업 상세(주차 아코디언)·`/mypage` 마이페이지. `favorites` API(GET/POST/DELETE, **scope=`g.user_id`**, 추가 시 게이트 읽기 + **실패 응답 정규화로 존재 oracle 차단**)·`/api/me/history`(**access_logs 열람시점 스냅샷 scope 필터** — 현재 slides.subject_code 아님, §15-7·P3 원칙 재사용).
> - **슬라이드 표시축**: 수업/마이페이지 카드의 organ 표기는 기존 자유텍스트(`load_slides` 'system') 참조. **organ_code 표시 전환은 별도(v1.5)** — D28 정규화와 분리.

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
- **v3.13**: 포털 P3(이용 리포트) 구현 — 읽기 전용 래퍼 2개(report·report/export). 집계 원천 access_logs·chat_logs·users·subscriptions(§0), 과목축 분리→기관 롤업(§18 D9), 활성=status='active' 일치, 스코프 격리(학교 드롭다운 없음), 비구독 403, 빈데이터 graceful(0나눗셈 가드·ANY 빈배열 회피·chat_logs 격리), XLSX _xlsx_safe·PDF=print. 내부 QA(a·b·c·d+빈데이터). pytest 183. **포털 3탭 완성.**
- **v3.14** (포털 P2+P3 외부검증 Codex+Gemini 반영 5건): ① 조회수 access_logs 스냅샷(al.institution_id·al.subject_code) 기준으로 시간축 오염 제거(High) ② P3 활성=status='active'(NULL 제외)로 active_seat_count 일치(§0)+users.status NOT NULL 마이그레이션(D25) ③ max_seats 합산 접근창 필터(미래 갱신 합산 차단, active_seat_count 불변) ④ 대시보드 날짜 _today_kst 일괄(_sub_status·D-day·report_range, half-open 경계) ⑤ period allowlist(잘못된 값→'3m'). pytest 196. D21 추적 유지(코드 변경 없음).
- **v3.15** (포털 P2+P3 재검증 2R Codex 반영): ① is_special 좌석 정합 — 특별계정 승격 시 subject_code=NULL(좌석 비점유)로 P2 좌석↔P3 활성 '같은 집합'(§0), 잔존 정리 마이그레이션 신설 ② 소진율 분자/분모 기준 A 통일 — active_users도 접근창 열린 과목(window_codes)만(만료 과목 유령 active 제외, 분자=분모 같은 행집합) ③ top_slides LEFT JOIN+제목 폴백(표시용 조인이 집계 떨구지 않게) ④ 스냅샷 subject_code NULL 과거 로그 집계 제외 명문화(§15-7). pytest 202. D26(슈퍼관리자 COALESCE 잔재) 추적 신설.
- **v3.16** (포털 P3 재검증 3R Codex 반영): ① 소진율 분모(max_seats)를 과목별 권위 row 1개로 정규화 — 접근창 겹치는 구독 중복 합산(150+150=300) 제거, 인증 게이트 `active_window_subscription`의 `subscription_end DESC` 규칙을 `DISTINCT ON (subject_code)`로 재사용(새 규칙 없음). 분자=분모=인증 셋이 같은 행집합(§0) ② 이용량 KPI(구독 보유 과목 전체, 만료 포함) vs 소진율(현재 접근창 과목만) 과목 집합 비대칭은 설계 의도로 명문화(§15-7, 코드 불변). pytest 205. D21·D22·D26 추적 유지.
- **v3.17**: 검토·재정비(문서). Render 폐기·EC2 이전 완료 반영(§3·D16)·www.slide-atlas.net 확정(§1). 보람바이오텍 연혁 정정(회사 1985 설립/슬라이드 사업 2006~ §1). 공급사 Yulin 확정·9월 138종(§11·§14·§5-4). §1 경쟁구도 재정의(Histology Guide 무료 vs 유료 정당화 = LMS 베팅, 7~8월 영업 판가름). §16 가격(Standard 기준 명시·최초 구독 일괄 할인 lock-in 정책 신설·HST 단일). D9 포털 P3 해결 반영. (지시 문서는 v3.13→v3.14 가정이었으나 직전 포털 작업으로 파일이 v3.16이라 v3.17로 매김 — 내용 동일.)
- **v3.18**: §14 Happy Science 담당자 오기 수정(Linda Li→Mallen Zhang). §18 D27 신설(사용자 공통 마이페이지 미구현 — 포털 P4 아님, 학생 e2e 시 구현). (지시는 D25 가정이었으나 D25·D25b·D26 사용 중이라 D27로, §22-1 참조는 부재라 §9·§21-8로 조정.)
- **v3.19**: 이번 세션 전략 결론 반영 — HST v1.0 구독 학교 확인 즉시 **HST↔PATH normal-abnormal 연동 v1.5** 착수(§2). §0 다과목 구조 덕에 구독/좌석/접근 무변경, 신규는 연결 레이어뿐. v1.0 선투자는 **organ 통제어휘 정규화 한 가지**(organs 테이블+slides.organ_code, D28); 연동 테이블(slide_links)은 additive라 v1.5 설계고정·이연(D29). §8 단일 게이트 불변 → 교차과목 연동=포인터+업셀(접근 구멍 아님). §1 장기 해자=복제불가 콘텐츠 자산으로 이동 명시.
- **v3.20**: D28 organ 통제어휘 정규화 구현·외부검증·라이브 배포 완료(2026-06-11). organs 테이블+slides.organ_code+FK+46종 시드(12계통) RDS 적용, 코드 배포(organ_code 필수·계통 드롭다운·레거시 /admin/api/slide→410·fail-loud, 650a5ee). Codex+Gemini 검증 반영(High 배포순서→운영, Med#1 organ_code 필수, Med#2 레거시 410). 배포 시 EC2가 main보다 ~4.5일 뒤처져 LMS+포털 코드도 함께 첫 라이브(RDS 선마이그레이션돼 무사) — §20 디버전스 주의 신설. D30 신설(§5-1 배치 적재 미구현, 런칭 크리티컬). 잔여: 138 organ 시드 확정·D24 6행 정리는 배치 적재 시.
- **v3.21**: LMS 3단계 구현 완료 반영(스펙→구현). 교수 4화면(`43b3025`: /teacher/courses·/teacher/course/<cid>·/assistants·/dashboard + 표시 API 3)·학생 3화면(`24033c8`: /home 수업 탭·/course/<cid>·/mypage), favorites GET/POST/DELETE·/api/me/history. 외부검증(Codex+Gemini) 통과(pytest 276). 배치 과목 정합 가드(slide.subject_code==course.subject_code)·favorites 존재 oracle 차단(실패 응답 정규화)·history 스냅샷 scope 필터(§15-7·P3 원칙 재사용). 표시축 organ 자유텍스트 유지(organ_code 전환 v1.5). §21 구현상태·§17 LMS 목업 7종·D31(학생 비번 변경 API 부재 🔴)·D32(즐겨찾기 UI 토글 🟠) 신설, D7 비고 1줄. **organ(v3.19/v3.20) 내용 무변경 additive.** (※ 지시는 v3.20 가정이었으나 main이 이미 organ v3.20이고 D30 사용 중이라 역행 금지 원칙대로 v3.21·D31/D32로 매김 — 내용 동일.)
- **v3.22**: 포털 명단 **양식 다운로드**(`GET /portal/api/roster/template`, 헤더 단일상수 `_PORTAL_ROSTER_HEADER`로 양식↔파서 글자단위 정합·round-trip 안전, 행정직원 제외, 과목 `_subscribed_subjects` 동적 scope 격리, `_xlsx_safe` 수식주입 방어) §9 P1 명문화(향후 목업 누락 방지). 포털 명단 **성능 단계1**(커밋 `d1530af`: 한 요청 `__ADMIN__` 조회 2→1회, `g._admin_roster_cache` 요청 스코프 — §8 DB 권위·회수 즉시 반영·반환 shape §13-2 불변; 인덱스 `db/portal_perf_indexes.sql` users/rosters `lower(email)` 함수형+subscriptions 복합, CEO EC2 적용) 반영. 외부검증 통과(pytest 293). D11 비고·D33(단계2 커넥션 체크아웃 합치기, D14 시) 추가. **기존(organ·PATH·slide_links·LMS 3A/3B·D1~D32) 무변경 additive.**
