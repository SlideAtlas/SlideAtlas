# CLAUDE.md — SlideAtlas 프로젝트 메모리 v3.1

> 이 파일은 Claude Code 세션 시작 시 반드시 읽어야 하는 프로젝트 컨텍스트 파일입니다.
> 모든 에이전트(오케스트레이터, 개발, QA)는 이 파일을 기준으로 작업합니다.
>
> **v3.1 핵심 변경 — Codex 외부 검증(묶음 A·B) 반영, 문서를 현재 코드 상태에 정렬(pytest 65/65).**
> ① 슬라이드 접근은 **단일 게이트(`_slide_access_allowed`) 기반 과목 구독 격리** — "슬라이드 기관==사용자 기관"
> 화석 제거, `SA`는 소유자 표시일 뿐 공용/기본제공 아님(§6-1·§8). ② **온보딩은 구독 선행**(구독 없으면
> 가입·인증 거부, §6-3). ③ 만료·가입은 **접근창(`access_open_date<=today<=subscription_end`, KST)·fail-closed**
> (§8·§16). ④ 특별계정 만료·ADMIN_SECRET_KEY fail-closed·타일토큰 무중단 재발급·문의답변/XLSX/XSS 방어.
>
> **v3.0 골격(유지) — 과목/좌석 분리.** 구독·좌석·만료·접근·집계가 모두 (기관 × 과목) 단위로 독립(§0).
> v1.0(HST 단일)은 그 구조의 *특수 케이스일 뿐*. 의도적으로 미룬 항목은 **§18 기술부채**에 집결한다.

---

## 0. 단일 진실 원칙 (v3.0 신설 — 최상위 규칙)

혼선 방지를 위해 다음을 **모든 섹션·코드·QA에 우선하는 상위 규칙**으로 둔다.

1. **구독의 단위는 (기관 × 과목)이다.** 진실의 원천은 `subscriptions` 테이블이다.
   좌석(max_seats)·만료(subscription_end)·접근권·집계·정원검사는 **전부 과목별로 독립**한다.
2. **`institutions`의 옛 구독 컬럼(subscription_plan/start/end, max_users)은 deprecated다.**
   인증·좌석·만료 경로에서 **참조 금지**. 데이터는 남아 있으나 죽은 컬럼이며 v1.5에 정리한다(§18).
3. **`users.subject_code`는 "이 사용자가 어느 과목 명단에 속하는가"이며, 가입 시 반드시 채워진다.**
   `institution_rosters`에서 (institution_id, subject_code, email)로 매칭해 캡처한다.
   단 **계정 단위는 이메일이다 — 한 이메일 = users 1계정, 과목 접근은 roster 행으로 표현**(v3.2 확정, §6-2).
   `users.email`은 전역 UNIQUE. (다과목 N-레코드 인증의 잔여 한계는 §18 D12.)
4. **v1.0이 HST 단일인 것은 데이터의 우연이지 구조의 전제가 아니다.**
   코드는 항상 과목 축을 일급으로 다루며, "어차피 과목 하나니까"라는 단축(shortcut)을 두지 않는다.
5. 위 원칙과 충돌하는 옛 서술/코드를 발견하면 **이 문서가 우선**이며, 코드를 이 문서에 맞춘다.

---

## 1. 프로젝트 개요

**제품명**: SlideAtlas
**운영사**: 아틀라스랩 주식회사 (Atlas Lab Co., Ltd.)
**대표**: 김보람 (Boram Kim)
**URL**: slideatlas.onrender.com / slide-atlas.net (공식 도메인, 2025.05 확정)
**도메인**: atlaslab.co.kr (가비아)
**이메일**: boram@atlaslab.co.kr

**한 줄 정의**: 의과대학·치과대학·수의대·한의대·약대·간호대를 대상으로 한 디지털 병리/조직학 WSI(Whole Slide Image) 구독 SaaS 플랫폼.

**핵심 비즈니스 모델**: 오프라인 슬라이드 납품(보람바이오텍, 20년 의대 납품 이력) 네트워크를 디지털 구독 SaaS로 전환. **좌석 플랜 기반 학기 단위 구독**, 장비 불필요(WinMedic 등 경쟁사 대비 차별점).

**경쟁 구도**: WinMedic(스캐너+플랫폼 수직통합, 장비 수천만원) vs SlideAtlas(콘텐츠 구독 SaaS, 장비 불필요) = 장비판매 vs Netflix. 실제 경쟁 프레임은 "유리슬라이드 1회 구매(₩18M+) 대체"이지 무료 디지털 사이트가 아니다.

---

## 2. 버전별 개발 로드맵

### v1.0 — 한국 런칭 (2026년 9월 목표)
- **타겟**: 국내 지방의대·수의대·약대·한의대·보건대
- **콘텐츠**: 아틀라스랩이 직접 라이선스 계약한 컬렉션만 제공 (교수 업로드 없음)
- **모듈**: **조직학(HST) 단일**. 단, 이는 *판매되는 과목이 하나뿐*이라는 뜻이며, 코드·구독 구조는 다과목을 일급으로 지원한다(§0). 병리·기생충은 v1.5 이후 활성.
- **AI 튜터**: 슬라이드 메타데이터 + `knowledge_base` JSON → Claude API (VectorDB 없음)
- **구독**: (기관 × 과목) 단위. 좌석 플랜(Department/Standard/Campus/Institution) × 학기 단위. v1.0은 과목 구독 카드가 1개(HST)일 뿐, 구조는 N개 카드를 지원. 자세한 모델은 §16.
- **교수 수업 페이지(LMS)**: 수업 개설·주차별 슬라이드 배치·학생 수강·즐겨찾기. **v1.0 정식 범위이자 핵심 과금 차별점**(한국어+국가고시 연계+교수 지정 커리큘럼). 상세 §21.
- **모바일**: 반응형 웹 (OpenSeadragon 터치 기본 지원 + CSS 미디어쿼리)
- **마일스톤**: 9월 가을학기 2~3개교 구독 확보 → 초창패 추경 신청

### v1.5 — 콘텐츠 확장·국내 안착 (2026년 말)
- **콘텐츠**: 병리·기생충 모듈 활성, Mahidol 열대의학 컬렉션 라이선스
- **AI 튜터**: 자문 교수 1인 영입 → knowledge_base JSON 검수·보완
- **영업**: 국내 10~15개교 확보, 매출 레퍼런스 구축
- **부채 정리**: §18 기술부채 항목(옛 구독 컬럼 DROP 등) 처리 시점

### v1.5M — 모바일 PWA 출시 (2027년 1분기)
- PWA(브라우저 설치, 앱스토어 불필요). WSI 뷰어 터치 최적화, 태블릿 레이아웃, 홈화면 추가.

### v2.0 — 글로벌 플랫폼 (2027년 이후)
- Liverpool 열대의학 등 특수 컬렉션, 교수 업로드+로열티, Vector DB(multilingual-e5)+RAG 다국어, 유튜브식 콘텐츠 마켓플레이스.

### v2.x — 네이티브 앱 (2027년 Q3~Q4 목표)
- React Native/Flutter(팀 구성 시 결정). 고배율 렌더링·오프라인 캐시·펜 마킹·푸시. 투자 유치 후 착수.

> **설계 원칙**: v2.0 기능(VectorDB, 교수 업로드, 다국어, 로열티)은 v1.0 범위 제외. 단 코드 모듈 경계는 v2.0 확장을 고려해 설계. PWA 전환 고려해 v1.0부터 프론트엔드 구조를 잡는다.

---

## 3. 현재 기술 스택

| 구분 | 내용 |
|------|------|
| 백엔드 | Python Flask (server_render.py + auth/ 패키지 + templates/) |
| 뷰어 | OpenSeadragon |
| 배포 | Render Starter ($7/월) (개발: Render 임시. 9월 정식 런칭은 EC2 — §18 D16. 과거 'Render 런칭 후 이전' 안은 폐기) |
| 저장소 | AWS S3 (ap-northeast-2, 버킷: slideatlas-slides) |
| 타일서버 | AWS EC2 t3.medium (slideatlas-tileserver, ec2-3-34-35-58.ap-northeast-2) — 동적 워터마킹 포함 (~$40/월) |
| 타일엔진 | titiler + 커스텀 타일서버 (~/tileserver/main.py, rasterio 기반) |
| 파이프라인 | SVS/DCM/TIFF/NDPI/VSI → COG TIFF → S3 → titiler |
| 데이터 관리 | RDS PostgreSQL (slideatlas-db, ap-northeast-2c) 구축 완료, 마이그레이션 진행 중 |
| AI 연동 | Claude API (/api/chat), 구조가이드/질문하기/퀴즈 탭 |
| 버전 관리 | GitHub (SlideAtlas/SlideAtlas) |

---

## 4. 슬라이드 변환 파이프라인 (핵심 인프라)

### 4-1. 설계 원칙
변환 스펙을 완전히 고정. 어떤 파일이 들어오든 출력은 항상 동일한 COG TIFF 스펙.

**고정 변환 스펙 (모든 슬라이드 공통)**
```
타일: 256×256 px / 압축: JPEG Q=85 / 오버뷰: 7레벨 고정 (2,4,8,16,32,64,128)
MPP: 원본에서 추출 (없으면 ready_no_mpp, 임의 기본값 금지), DB 저장
좌표계: 픽셀 기준, 북서쪽 원점 / BigTIFF: 4GB 초과 시 자동
```

### 4-2. 파이프라인 실행 순서
관리자 파일 업로드 → S3 임시 버킷 → EC2 워커 자동 트리거 → 순차 실행:
```
① extract_meta()      → MPP·해상도·포맷·스캐너 추출·검증
② convert_cog()       → COG TIFF 변환 (표준 스펙 고정)
③ extract_minimap()   → 최저 오버뷰에서 minimap.png 추출 → S3
④ extract_thumbnail() → 20x 해당 오버뷰에서 thumbnail.jpg(400×300) → S3
⑤ generate_kb_json()  → Claude API로 knowledge_base JSON 자동 초안 생성
⑥ run_qc()           → 타일 응답·흰타일 비율·줌 정합성 자동 검증
⑦ update_db()        → status 갱신, 전체 메타데이터 DB INSERT
```
**미니맵/썸네일 원칙**: 뷰어에서 그리지 않고 파이프라인이 미리 생성해 S3 저장. OpenSeadragon은 불러오기만.

> ⚠ **현황 주의(QA 발견)**: 현재 코드의 thumbnail은 openslide 동적 생성 방식이며 §4-2의 "파이프라인이 S3에 미리 생성" 원칙과 불일치. /minimap 라우트도 미구현. 파이프라인 ③④는 아직 미구현 영역 → §18 부채.

### 4-3. 모듈 구조 (SQS/Lambda 이식성 보장)
```
pipeline/
├── models.py              # ConversionJob, ConversionResult (데이터 계약, 변경 금지)
├── trigger_adapter.py     # 트리거별 파싱 (v1.0 HTTP / v1.5 SQS / v2.0 Lambda)
├── conversion_engine.py   # 변환 엔진 (트리거 무관 동일 작동)
└── storage_adapter.py     # S3 이동, RDS 업데이트, 상태 갱신
```
`ConversionJob`/`ConversionResult` 데이터 계약은 어떤 이유로도 변경 금지. 마이그레이션 시 `trigger_adapter.py`만 교체, 엔진 코드 무변경.

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
                    ↘            ↘          ↘
                     failed       failed     ready_no_mpp
```
| 상태 | 의미 | 어드민 표시 |
|------|------|-------------------|
| pending | 업로드 완료, 변환 대기 | 🟡 대기 |
| converting | COG 변환 중 | 🔵 변환 중 |
| qc_check | 자동 QC 검증 중 | 🔵 검증 중 |
| ready | 변환·자동QC 통과 | 🟢 변환완료 |
| ready_no_mpp | MPP 없음, 배율 비활성 서빙 | 🟠 MPP 없음 |
| failed | 변환/QC 실패 | 🔴 실패 + 로그 |

**ready_no_mpp 원칙**: 열람 가능(타일 정상)하나 배율 버튼 비활성, "배율 정보 없음" 표시. 어드민에서 **MPP 수동 입력 후 재처리(Retry)** 가능. 임의 기본값(0.5)으로 처리하지 않는다(배율 오류가 교육적으로 더 위험).

> ⚠ **변환 상태(자동)와 배포 상태(사람 결정)는 별개 축이다.** 변환이 `ready`여도 학생에게 자동 공개되지 않는다. 사람의 교육 QC(배포 결정)가 별도로 얹힌다 — §5-4, §15-3 참조. 노출 게이트는 `deploy_status=='deployed'`만 사용하며 `conversion_status`는 게이트에 쓰지 않는다(QA 확인됨).

---

## 5. 슬라이드 메타데이터 & 지식베이스(kb)

### 5-1. 배치 업로드 (100장 이상)
엑셀(.xlsx) + 슬라이드 파일 동반 업로드. 컬럼:
```
slide_id | title_ko | title_en | organ | stain | species | subject_code | description
```
- `slide_id`는 파일명에서 자동 파싱. 공급사에 파일명 규칙 사전 합의.
- `subject_code`는 슬라이드가 어느 과목에 속하는지를 결정(과목 축의 콘텐츠 측 기준).
- **MPP는 입력하지 않는다 — 변환 시 파일에서 자동 추출.**

### 5-2. 개별 추가 (1~2장)
파일 업로드(SVS/TIFF/NDPI/DCM/VSI) + 메타데이터 폼. **기관코드는 SA 고정(§6)**, 과목만 선택 → 슬라이드 ID 자동 채번. **MPP 입력칸 없음(자동 추출)**. 공급원(Acknowledgement)은 `license_source`로 별도 입력 → 뷰어 푸터 자동 표기.

### 5-3. knowledge_base JSON 자동 생성
`generate_kb_json()`이 Claude API로 자동 초안 생성:
```json
{
  "key_structures": ["villus", "Lieberkuhn crypt", "goblet cell"],
  "exam_points": ["villus height ratio"],
  "common_confusions": ["jejunum vs ileum — Peyer's patches 유무"],
  "ko_observation_points": "점막 표면 융모를 먼저 찾고 ..."
}
```
AI 튜터 컨텍스트로 사용. `ko_observation_points`(한국어 관찰 순서·키워드)는 Histology Guide류 무료 사이트 대비 핵심 차별점.

### 5-4. kb 검수 = QC 단계 게이트 (중요)
kb 초안 검수·보완은 **업로드 시점이 아니라 배포(QC) 단계**에서 일어난다. 흐름:
```
업로드(파일+메타) → 자동 변환 + kb 자동 초안 → 배포 대기
   → (소수) 어드민 "검수" 모달에서 보완 후 배포
   → (대량 134장) kb 초안 엑셀 내보내기 → 검수자(대학원생) 일괄 보완 → 검수결과 일괄 반영(엑셀) → 일괄 배포
```
검수는 학생 노출 직전의 게이트다. `deploy_status`(§15-3)로 관리.

---

## 6. 슬라이드 ID 체계 & 사용자–과목 매칭

### 6-1. 슬라이드 ID
형식: `{기관코드}-{과목코드}-{순번}`

**v1.0 채번 원칙**: 아틀라스랩은 슬라이드 제작자가 아니라 **라이선스 후 스캔하는 주체**다. 따라서 v1.0의 모든 콘텐츠는 **기관코드 `SA`(SlideAtlas 자체)로 단일 채번**한다. 공급사(율린/Vic 등)는 ID에 넣지 않는다.
- 공급원·저작권 출처는 ID가 아니라 **`slides.license_source` 컬럼**에 기록.
- 제조사가 acknowledgement를 요구하면 `license_source`를 기준으로 **뷰어 하단 푸터에 "Provided by ___" 자동 표기**.
- **공급사는 institutions 테이블에 기관으로 넣지 않는다 — 공급원은 slides.license_source 컬럼으로만 관리하며 대부분 비공개, acknowledgement가 필요한 경우만 푸터에 노출한다(§18 D18).**
- (과거 검토했던 율린 `YL` 코드 안은 폐기. `YU`는 연세대로 예약됨.)

> ★ **`SA`는 "콘텐츠 소유자(아틀라스랩이 라이선스·스캔)" 표시일 뿐, "전 기관 공용"이나 "기본 제공"이 절대 아니다(v3.1 명문화).**
> 슬라이드의 `institution_id='SA'`는 채번·소유 표시이며 **접근 격리의 기준이 아니다**. 각 슬라이드는
> **그 과목(`slide.subject_code`)을 구독한 기관 + 그 과목 좌석(roster)에 등록된 사용자에게만** 노출된다(§8 단일 게이트).
> 따라서 "슬라이드 기관 == 사용자 기관" 비교(구 유튜브형 화석)는 코드에서 제거되었고, 접근은 **오직 과목 구독**으로 판정한다(§0-4).
> **HST(조직학)는 v1.0의 첫 런칭 과목일 뿐 기본 제공이 아니다** — 어떤 기관은 PARA(기생충학)만 구독하고 HST는 구독 안 할 수 있다.

**과목코드** → `subject_codes` 테이블로 관리(코드 하드코딩 금지, 관리자 페이지에서 행 추가):
- HST: 조직학 / PATH: 병리학 / PARA: 기생충학 / ANAT: 해부학 / EMBRY: 발생학

**순번**: 기관+과목 조합별 독립 카운터(자동 채번). 예: `SA-HST-001`, `SA-PARA-003`.

> 향후 교수 업로드(v2.0)나 고객 기관 자체 콘텐츠가 생기면 그때 기관코드 다축 채번을 재도입한다.

### 6-2. 사용자–과목 매칭 (v3.0 명문화 / v3.2 정책 확정 — 핵심)
- **회원가입은 `institution_rosters`에 (institution_id, subject_code, email)이 등록된 경우만 허용.**
- **가입(register) 및 이메일 인증(verify_email) 시 `users.subject_code`를 반드시 채운다.**
  매칭 키는 roster의 (institution_id, subject_code, email).
- **★ 이메일당 users 1계정 (v3.2 — CEO·외부검증 확정, Codex#3·Gemini#5).**
  과거 서술("한 사용자가 여러 과목 명단에 있으면 과목별 user 레코드가 독립 생성")은 **옛 설계이며 폐기**한다.
  현행 정책: **한 이메일 = users 1계정**, **과목 접근은 `institution_rosters` 행으로 표현**한다.
  `users.email`은 **전역 UNIQUE**(복합키로 바꾸지 않는다)이며, register는 동일 이메일 재가입 시
  새 계정/중복 pending을 만들지 않고 `EMAIL_EXISTS`로 거부한다. verify/login은 이메일 단일 키로
  계정을 모호함 없이 식별한다. (DB 차원의 전역 UNIQUE 제약 추가는 별도 마이그레이션으로 분리 — 현재는
  앱 레이어 강제. 다과목 N-레코드 인증의 잔여 한계는 §18 D12에서 추적.)
- ⚠ **회귀 주의(QA 발견)**: 과거 코드가 가입 시 subject_code를 채우지 않아 전 사용자 NULL이었다.
  이로 인해 과목별 만료/좌석 검사가 무력화되었다. v3.0 이후 가입 경로는 반드시 채번하며,
  NULL 사용자에 대한 폴백(기관 단위 처리)은 **제거됨**(정상 경로만 존재, §13-2·§18).

### 6-3. 온보딩 순서 원칙 (v3.1 명문화 — CEO 확정 정책)
**구독 계약·입금 전에는 학생을 받지 않는다.** 온보딩은 반드시 다음 순서를 따르며, 코드가 이를 강제한다:
```
① 구독 계약·입금
② institution_subject_access / subscriptions 생성 (어드민 — 기관×과목, 접근창·좌석 설정)
③ institution_rosters 등록 (이름+이메일+과목 명단 업로드)
④ 학생 회원가입(register) → 이메일 인증(verify_email)
```
- **가입·인증 시점에 (institution_id, subject_code)의 접근창 내 active 구독이 없으면 거부**한다
  (`SUBSCRIPTION_INACTIVE` 403). 즉 ②가 선행되지 않으면 `active` 계정이 생성되지 않는다.
- 접근창 = `access_open_date <= today <= subscription_end`(KST). 미래 학기 구독이 미리 active여도
  창이 열리기 전에는 가입·접근 모두 불가(§8·§16).
- 과거 "구독 없으면 정원 무제한 허용(max_seats=None)" 로직은 **제거**됨(Codex #4 반영).

### 6-4. 가입·역할 모델 — 두 트랙(position·role 자동부여, v3.3 명문화)
가입 시 **두 명단을 순차 대조**해 `position`(지위)과 `role`(시스템 권한)을 **모두 자동 부여**한다.
가입자는 지위·역할을 입력하지 않는다 — **폼 = 기관 드롭다운 + 이메일 + 비번 + 비번확인 (이름 입력 없음 — 표시용 이름은 roster.name을 사용)**뿐.
- **트랙1 (이용자 roster)**: (기관, 이메일) 매칭 → `position` 캡처(교수/조교/학생/행정직원) → `role='viewer'`.
  슬라이드 열람·좌석(TO) 관련 축. (행정직원은 좌석 0·콘텐츠 비소비 — §21.)
- **트랙2 (기관관리자 리스트, `__ADMIN__` 행)**: 매칭되면 `role='admin'`(포털 접근).
- **겸직 가능**: 두 트랙 다 매칭이면 `position`=실제 지위, `role='admin'`. (`role`과 `position`은 별개 두 축, §21.)
- **role 두 값**: `viewer`/`admin`. **기능 권한 분기는 `role`이 아니라 `position` 기반**(예: 수업 개설 = position∈{교수,조교}). `role`은 viewer/admin만 가른다(§21 권한표).
- §6-2의 **"이메일당 users 1계정"** 정책은 그대로 유지.

> **position의 단일 출처 = 과목(subject) roster 행이다(v3.4 CEO 확정).**
> 가입 시 트랙1이 매칭된 subject 행의 position(교수/조교/학생)을 `users.position`에 복사한다.
> **subject 행이 없는 계정(admin-only)은 position=NULL**이며 운영 전용(좌석 0·콘텐츠 비소비)이다.
> **행정직원은 subject 행 없는 admin-only 계정으로 표현**한다(별도 subject 행을 만들지 않는다).
> (한계: 지위가 있으나 콘텐츠를 소비하지 않는 관리자는 v1.0에서 행정직원으로 등록해 회피한다 — §18 D17.)
> 겸직(subject 행 + `__ADMIN__` 행)이어도 position은 subject 행에서 나온다 — **겸직 우선순위 규칙은 없다**.
> `__ADMIN__` roster 행의 position은 NULL로 둔다(`_upsert_admin_roster`는 position을 채우지 않는다).

---

## 7. DB 스키마 (v1.0 기준)

> **단일 진실(§0)**: 구독·좌석·만료·접근은 `subscriptions`(기관×과목)가 원천이다.
> `institutions`의 subscription_* / max_users 컬럼은 **deprecated**이며 어떤 코드도 참조하지 않는다(§18).

```sql
CREATE TABLE subject_codes (
  code VARCHAR(10) PRIMARY KEY,  -- 'HST','PATH','PARA'
  name_ko VARCHAR(50), name_en VARCHAR(50),
  is_active BOOLEAN DEFAULT FALSE,   -- 모듈 활성 여부 (v1.0은 HST만 TRUE)
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE institutions (
  id VARCHAR(20) PRIMARY KEY,     -- 기관코드
  name_ko VARCHAR(100),           -- "충남대 의과대학" (학교+단과대)
  name_en VARCHAR(100),
  university VARCHAR(100),         -- 학교명
  college VARCHAR(100),            -- 단과대명
  domain VARCHAR(100),             -- 이메일 자가인증 도메인
  -- ⚠ DEPRECATED (v3.0): 아래 4개 컬럼은 옛 "기관 단위 구독" 모델 잔재.
  --   인증/좌석/만료 경로에서 참조 금지. 데이터는 남아있으나 죽은 컬럼. v1.5 DROP 예정(§18).
  subscription_plan VARCHAR(20),   -- DEPRECATED → subscriptions.plan
  subscription_start DATE,         -- DEPRECATED → subscriptions.access_open_date
  subscription_end DATE,           -- DEPRECATED → subscriptions.subscription_end
  max_users INT,                   -- DEPRECATED → subscriptions.max_seats
  created_at TIMESTAMP DEFAULT NOW()
);

-- 구독: 기관 × 과목 단위 (좌석·학기·구독료 독립) ── 단일 진실 원천(§0)
CREATE TABLE subscriptions (
  id SERIAL PRIMARY KEY,
  institution_id VARCHAR(20) REFERENCES institutions(id),
  subject_code VARCHAR(10) REFERENCES subject_codes(code),
  plan VARCHAR(20),                -- 'department'|'standard'|'campus'|'institution'|'custom'
  max_seats INT,                   -- 플랜 기본값 또는 직접 지정(특수계약). 정원 검사의 기준.
  start_term VARCHAR(10),          -- '2026-fall' 등 학기 식별자
  term_count INT,                  -- 구독 학기 수
  access_open_date DATE,           -- 학기 시작 -30일 (자동 계산)
  subscription_end DATE,           -- 마지막 학기 종료일 (자동 계산). 만료 검사의 기준.
  fee INT,                         -- 구독료(원)
  payment_method VARCHAR(20),      -- '연간 선불'|'학기 선불'|'기타'
  status VARCHAR(20) DEFAULT 'active',
  created_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(institution_id, subject_code, start_term)
);

-- 구독 갱신/변경 이력 (덮어쓰지 않고 누적 보존)
CREATE TABLE subscription_history (
  id SERIAL PRIMARY KEY,
  subscription_id INT REFERENCES subscriptions(id),
  event VARCHAR(20),               -- 'initial'|'renewal'|'change'
  plan VARCHAR(20), max_seats INT,
  start_term VARCHAR(10), term_count INT,
  fee INT, note TEXT,
  created_by INT REFERENCES admin_users(id),
  created_at TIMESTAMP DEFAULT NOW()
);

-- 콘텐츠 접근권: 기관 × 과목 (좌석 플랜과 직교)
CREATE TABLE institution_subject_access (
  institution_id VARCHAR(20) REFERENCES institutions(id),
  subject_code VARCHAR(10) REFERENCES subject_codes(code),
  granted BOOLEAN DEFAULT TRUE,
  PRIMARY KEY (institution_id, subject_code)
);

CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  institution_id VARCHAR(20) REFERENCES institutions(id),
  subject_code VARCHAR(10),         -- ★ 어느 과목 명단인지 (과목별 좌석 카운터). 가입 시 필수 채번(§6-2).
  email VARCHAR(200) NOT NULL,
  password_hash VARCHAR(255),
  role VARCHAR(20) DEFAULT 'viewer',  -- ★ v3.3: 'viewer'|'admin' (구 'student'→'viewer' 정정, §21). role과 position은 별개 축.
  position VARCHAR(20),               -- ★ v3.3: 교수/조교/학생/행정직원. 기능 권한 분기 근거(§21). 가입 시 roster에서 캡처.
  status VARCHAR(20) DEFAULT 'pending_verification', -- active|pending_verification|locked
  is_special BOOLEAN DEFAULT FALSE,  -- 구독 만료 무관 접근 (§15-8)
  special_expires_at DATE,           -- 특별계정 만료일 (NULL=무기한, 비권장)
  special_review_at DATE,            -- 특별계정 재검토일/사전알림 기준
  last_login TIMESTAMP,
  locked_at TIMESTAMP,
  failed_attempts INT DEFAULT 0,     -- 계정 잠금 카운터(§8)
  failed_window_start TIMESTAMP,     -- 24h 카운팅 윈도우 시작
  session_token VARCHAR(255),
  created_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(institution_id, subject_code, email)
  -- ★ v3.2 정책(§6-2): 계정 단위는 이메일 — 한 이메일 = 1계정, 과목 접근은 roster 행으로 표현.
  --   register는 이메일 전역 검사로 중복 계정/pending 생성을 막는다(앱 레이어 강제).
  --   DB 차원 email 전역 UNIQUE 제약 추가는 별도 마이그레이션으로 분리(기존 데이터 점검 후).
);

CREATE TABLE slides (
  id VARCHAR(50) PRIMARY KEY,        -- 'SA-HST-001'
  institution_id VARCHAR(20),        -- v1.0은 항상 'SA'
  subject_code VARCHAR(20),
  title_ko VARCHAR(200), title_en VARCHAR(200), description TEXT,
  s3_key VARCHAR(500), s3_minimap_key VARCHAR(500), s3_thumbnail_key VARCHAR(500),
  mpp FLOAT, width INT, height INT,
  stain VARCHAR(50), organ VARCHAR(100), species VARCHAR(50) DEFAULT 'human',
  license_source VARCHAR(100),       -- 공급원 (푸터 표기 근거) 예: 'Provided by Yulin'
  original_format VARCHAR(20),
  conversion_status VARCHAR(20) DEFAULT 'pending', -- §4-5
  deploy_status VARCHAR(20) DEFAULT 'qc_pending',  -- §15-3: qc_pending|deployed|rejected (revoked→qc_pending)
  reject_reason TEXT,                -- 반려 사유 (검수자 보고)
  conversion_log TEXT, qc_passed_at TIMESTAMP,
  knowledge_base JSONB,
  created_at TIMESTAMP DEFAULT NOW()
);

-- 어드민 계정: 2단계 권한 (학생 JWT와 완전 분리)
CREATE TABLE admin_users (
  id SERIAL PRIMARY KEY,
  email VARCHAR(200) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  name VARCHAR(100),
  role VARCHAR(20) NOT NULL,         -- 'super_admin'|'staff'
  is_active BOOLEAN DEFAULT TRUE,
  last_login_at TIMESTAMP,
  session_token VARCHAR(255),        -- v3.2: 매 요청 DB 대조(탈취·재로그인 시 무효화, Codex#2)
  failed_attempts INT DEFAULT 0,     -- v3.2: 어드민 로그인 무차별 대입 차단(Gemini#1)
  failed_window_start TIMESTAMP,     -- v3.2: 24h 카운팅 윈도우 시작
  locked_at TIMESTAMP,               -- v3.2: 잠금 시각(NULL=미잠금, +24h 자동 해제)
  updated_at TIMESTAMP DEFAULT NOW(),
  created_at TIMESTAMP DEFAULT NOW()
);
-- ⚠ 위 4개 컬럼(session_token·failed_attempts·failed_window_start·locked_at)은
--   db/admin_security_schema.sql(ADD COLUMN, 멱등)로 추가. 신 코드 병합 전 RDS 실행 필수.

-- 랜딩 공지: 소프트 삭제(보관함)
CREATE TABLE announcements (
  id SERIAL PRIMARY KEY,
  title VARCHAR(200), body TEXT,
  is_published BOOLEAN DEFAULT FALSE,  -- 랜딩 노출 (최대 5)
  display_order INT,
  is_archived BOOLEAN DEFAULT FALSE,   -- 보관함(소프트 삭제)
  archived_at TIMESTAMP,
  created_by INT REFERENCES admin_users(id),
  updated_by INT REFERENCES admin_users(id),
  created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW()
);

-- 1:1 문의: 기관 컨텍스트 자동 첨부
CREATE TABLE inquiries (
  id SERIAL PRIMARY KEY,
  user_id INT REFERENCES users(id),
  institution_id VARCHAR(20) REFERENCES institutions(id) ON DELETE SET NULL,  -- 익명 문의 NULL 허용
  title VARCHAR(200), body TEXT,
  user_email VARCHAR(200), user_name VARCHAR(100),
  status VARCHAR(20) DEFAULT 'open',   -- open|answered
  created_at TIMESTAMP DEFAULT NOW()
  -- ⚠ privacy_agreed 컬럼 부재 → 개인정보 동의 저장 공백. 출시 전 필수 처리(§18).
);
CREATE TABLE inquiry_replies (
  id SERIAL PRIMARY KEY,
  inquiry_id INT REFERENCES inquiries(id),
  body TEXT,
  created_by INT REFERENCES admin_users(id),  -- 감사 추적
  sent_via_ses BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE access_logs (
  id SERIAL PRIMARY KEY,
  user_id INT REFERENCES users(id),
  slide_id VARCHAR(50) REFERENCES slides(id),
  institution_id VARCHAR(20),
  accessed_at TIMESTAMP DEFAULT NOW(),
  session_id VARCHAR(100)
);

-- 기관 명단 화이트리스트 / 이메일 인증 (JWT 인증)
CREATE TABLE institution_rosters (
  id SERIAL PRIMARY KEY,
  institution_id VARCHAR(20) REFERENCES institutions(id) ON DELETE CASCADE,
  subject_code VARCHAR(10),            -- ★ 과목별 명단. 가입 시 users.subject_code의 출처(§6-2).
  email VARCHAR(200) NOT NULL, name VARCHAR(100),
  role VARCHAR(20) NOT NULL DEFAULT 'viewer',  -- ★ v3.3: 'viewer'|'admin' (구 'student'→'viewer' 정정)
  position VARCHAR(20),                -- ★ v3.4: 지위(교수/조교/학생). subject 행에만. __ADMIN__ 행 NULL. users.position 출처(§6-4 트랙1).
  is_verified BOOLEAN DEFAULT FALSE, added_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(institution_id, subject_code, email)
);
CREATE TABLE email_verifications (
  id SERIAL PRIMARY KEY,
  user_id INT REFERENCES users(id) ON DELETE CASCADE,
  code VARCHAR(6) NOT NULL,
  created_at TIMESTAMP DEFAULT NOW(), expires_at TIMESTAMP NOT NULL,
  consumed BOOLEAN DEFAULT FALSE, attempt_count INT DEFAULT 0
);

-- ── 교수 수업 페이지(LMS) — v1.0 정식 범위 (§21) ───────────────────────
-- 수업(course)은 슬라이드 접근 게이트가 아니라 학습 경로/커리큘럼이다(접근은 §8 단일 게이트).
CREATE TABLE courses (
  id SERIAL PRIMARY KEY,
  institution_id VARCHAR(20) REFERENCES institutions(id),
  subject_code VARCHAR(10) REFERENCES subject_codes(code),  -- 수업은 특정 과목 안에서만 개설
  professor_user_id INT REFERENCES users(id),
  title VARCHAR(200), semester VARCHAR(20),
  created_at TIMESTAMP DEFAULT NOW()
);
CREATE TABLE course_weeks (
  id SERIAL PRIMARY KEY,
  course_id INT REFERENCES courses(id) ON DELETE CASCADE,
  week_number INT, title VARCHAR(200), empty_reason TEXT,  -- 빈 주차 사유 메모(시험·출장 등)
  created_at TIMESTAMP DEFAULT NOW()
);
CREATE TABLE course_week_slides (
  id SERIAL PRIMARY KEY,
  course_week_id INT REFERENCES course_weeks(id) ON DELETE CASCADE,
  slide_id VARCHAR(50) REFERENCES slides(id), display_order INT  -- 주차 내 중복 허용
);
CREATE TABLE course_assistants (
  course_id INT REFERENCES courses(id) ON DELETE CASCADE,
  user_id INT REFERENCES users(id), PRIMARY KEY (course_id, user_id)  -- 수업별 조교 위임
);
CREATE TABLE course_enrollments (
  course_id INT REFERENCES courses(id) ON DELETE CASCADE,
  user_id INT REFERENCES users(id), enrolled_at TIMESTAMP DEFAULT NOW(),
  PRIMARY KEY (course_id, user_id)  -- 자유 등록(승인 불필요). 한 학생 여러 수업 = 다대다(과목 구독과 별개 축)
);
CREATE TABLE favorites (
  user_id INT REFERENCES users(id),
  slide_id VARCHAR(50) REFERENCES slides(id),
  created_at TIMESTAMP DEFAULT NOW(), PRIMARY KEY (user_id, slide_id)  -- 개인 북마크(수업 무관)
);
```

> 회원가입은 institution_rosters에 (institution_id, subject_code, email)이 등록된 경우만 허용. 가입 시 users.status='pending_verification' + **users.subject_code를 roster에서 캡처** → 이메일 인증 완료 시 'active'. 마이그레이션 스크립트는 멱등·트랜잭션(BEGIN/COMMIT), 실행은 CEO 판단.

---

## 8. 보안 아키텍처

- **타일 접근 토큰**: TTL 5분, HMAC-SHA256. 뷰어 로드 시 `generate_tile_token(user_id, institution_id, slide_id)` 발급 → 모든 타일/DZI URL에 `?t=`. `verify_tile_token`은 user_id·institution_id·slide_id·exp **모두 대조**(QA 확인됨). 검증 실패 401. S3 퍼블릭 차단.
  - **무중단 재발급 (v3.1)**: TTL 5분이 만료돼도 끊김 없게, `GET /api/tile-token?slide=`가 **단일 게이트(`_slide_access_allowed`) 통과 시에만** 새 토큰을 발급한다(접근권 없는 슬라이드는 재발급 거부). 뷰어는 4분마다 **선제 갱신** + 타일 로드 실패 시 **재발급 후 재그리기**. `TILE_TOKEN_INVALID`는 로그인과 무관 → **강제 `/login` 리다이렉트 금지**(viewer가 `window.refreshTileToken()`로 처리).
  - **인증 2단계 분리 (v3.2 — Gemini#1 DoS 방어)**: 슬라이드 권한 검사(`_slide_access_allowed` + 구독·세션 DB 조회)는 **저빈도 '토큰 발급' 경로**(`/viewer/<id>`, `GET /api/tile-token`)에만 둔다. **고빈도 타일 스트리밍 경로**(`/dzi/<id>.dzi`, `/dzi/.../<col>_<row>.jpeg`, `/thumbnail/<id>`, `/ec2tile/<path>`)는 `@tile_token_required`로 **DB 조회 없이** 서명 JWT 복호화(신원 확보)+HMAC tile_token 검증만 한다. 타일 1장마다 무거운 구독·기관 JOIN이 도는 RDS 고갈/DoS를 차단. 권한 회수는 토큰 TTL(≤5분) 후 발급 게이트에서 반영(허용 가능한 지연). 발급 경로의 DB 권위 검증(§아래 매요청 검사)은 그대로 유지.
- **동적 워터마킹**: v1.0 포함. 사용자 ID·기관명을 타일마다 투명 삽입(Pillow, 15~20%, 대각선 반복). **특별 계정도 동일 적용**(유출 추적 유지).
- **브라우저 캐시 차단**: 타일/DZI/인증 응답 `Cache-Control: no-store`.
- **서버사이드 캐시**: EC2 메모리 캐시(서버에만 존재, 보안 위험 없음).
- **동시접속 제어**: 새 기기 로그인 시 기존 session_token 무효화(기관 해약 아닌 세션 종료).
- **도메인 자가인증**: 기관 이메일 도메인 검증 + 6개월 재인증.
- **멀티테넌시**: `institution_id`는 **user·access_logs·subscriptions·roster 등 사용자/운영 데이터 격리**에 쓴다. ⚠ **슬라이드 접근 격리에는 institution_id를 쓰지 않는다** — "슬라이드 기관 == 사용자 기관" 비교(구 유튜브형 화석)는 v3.1에서 전 경로 제거됨(아래 단일 게이트로 대체).
- **슬라이드 접근 단일 게이트 (v3.1 — `_slide_access_allowed`)**: 모든 슬라이드/타일/DZI/썸네일/뷰어/목록 경로가 **하나의 게이트**를 통과한다. 일반 사용자는 다음 **전부(AND)** 충족 시에만 접근:
  1. `deploy_status == 'deployed'`
  2. `g.subject_code == slide.subject_code` (사용자가 등록된 과목 == 슬라이드 과목)
  3. 사용자 기관이 그 과목 접근권 보유: `institution_subject_access.granted=TRUE` **또는** (institution_id, subject_code) 접근창 내 active 구독
  → 하나라도 불충족이면 403. **"deploy_status만 맞으면 공용 허용" 같은 완화 절대 금지(§0-4).** `institution_id`(='SA')는 게이트에 쓰지 않는다.
  - **is_special**: `deploy_status=='rejected'`만 차단(나머지 qc_pending/deployed 허용), **institution·subject 축은 정책상 우회**(§15-8). 단 만료(special_expires_at)는 집행.
  - **수업(course)은 슬라이드 접근 게이트가 아니다.** 접근은 오직 과목 구독(단일 게이트). 수업은 커리큘럼 안내일 뿐 — 수업 미등록이어도 구독 과목 슬라이드는 전체 열람 가능(§21).
- **라이선스 격리**: deploy_status != 'deployed' 슬라이드는 어떤 경로로도 직접 URL 접근 불가. **특별계정(is_special)도 deploy_status=='rejected'는 차단**(§15-8, CEO 결정).
- **CSRF 방어**: 더블서밋 쿠키. POST/PUT/DELETE/PATCH에서 `X-CSRF-Token` 헤더와 `csrf_token` 쿠키를 `secrets.compare_digest`로 대조. **모든 인증 fetch 경로는 interceptor.js를 로드해 토큰 자동 주입**(standalone 템플릿 viewer.html 포함 — QA 회귀 H1 교훈).
- **계정 잠금**: 24h 내 비번+인증코드 오류 합산 10회 → status='locked'. `locked_at` 기준 24h 후 자동 해제.
- **인증코드 재발송**: 1분 쿨다운, 24h 최대 5회. 경쟁조건은 `SELECT ... FOR UPDATE`.
- **구독 만료 매 요청 검사 (v3.1 정정 — 접근창 집행, fail-closed)**: `_authenticate()`·`login()`에서 매 요청, 해당 user의 **(institution_id, subject_code)에 매칭되며 접근창이 열린(`access_open_date <= today <= subscription_end`, KST) active 구독**이 있는지 확인한다. 옛 `institutions.subscription_end`(deprecated) 참조 금지.
  - **매칭 구독이 없으면(NULL) 차단** = fail-closed(§8 명문). 옛 `is not None` 가드(매칭 없음을 통과시킴)는 제거됨(Codex FAIL1).
  - **미래 학기 구독이 미리 active여도 access_open_date 전에는 통과 금지**(접근창 밖 → NULL → 만료)(Codex #3).
  - `is_special`은 구독 만료 면제. **단 `special_expires_at < today`면 차단**(NULL=무기한은 통과, §15-8 비권장). (Codex #5)
  - **role·is_special·institution_id는 DB 권위 (v3.2, Codex#2/Gemini#4)**: `_authenticate()`가 매 요청 DB에서 다시 읽어 `g`에 적재하고 게이트 판정에 쓴다(JWT payload 값 신뢰 금지 — 강등/특별계정 해제가 토큰 만료 전에 즉시 반영).
  - **기관 관리자(role='admin') 구독 면제는 'roster 결합' (v3.2, Codex#2)**: admin의 구독 만료 면제는 **현재 `__ADMIN__` roster 행이 존재할 때만** 유효(`_has_admin_roster`). roster 회수(권한 박탈) 시 면제가 사라져 일반 사용자처럼 구독 검사를 받고 차단된다(`users.role` 강등 없이 일관 처리).
- **어드민 세션 시크릿 fail-closed (v3.1)**: `ADMIN_SECRET_KEY` 환경변수 누락 시 **고정 문자열 폴백 없이 기동 실패**(RuntimeError). 알려진 secret으로 Flask 어드민 세션 쿠키가 위조되는 사고 차단(§18 D3, Codex #6).
- **어드민 세션 DB 대조·잠금 (v3.2, Codex#1/Gemini#3)**: 어드민 로그인 성공 시 `admin_users.session_token` 회전(DB+Flask 세션 저장) → **매 요청 `_get_admin_user`가 DB와 `compare_digest` 대조**(탈취·재로그인 시 무효). `/admin/login`에 학생과 동일한 계정 잠금(24h·10회→`locked_at`, 자동 해제). **잠금 시 `session_token=NULL` 회전으로 기존 어드민 세션 즉시 무효화** + `_get_admin_user`가 매 요청 `locked_at`(24h 내) 검사로 차단.
- **401 코드 구분**: SESSION_REVOKED(타 기기 로그인) / TOKEN_INVALID(세션 없음) / TILE_TOKEN_INVALID(타일토큰 검증실패, 로그인과 무관 — **리다이렉트 금지, 뷰어 JS 재발급으로 분기**) / SUBSCRIPTION_EXPIRED. interceptor.js가 4종을 구분 처리.
- **문의 답변 발송 (v3.1)**: 메일 발송 **성공 시에만** `status='answered'` 전환(실패 시 open 유지+경고, 조용한 실패 방지). 메일 Subject/To **헤더 주입 거부**(개행 제거), 제목·본문 **HTML escaping**(Codex 2-2#3).
- **리포트 XLSX 수식 주입 방어 (v3.1)**: 셀 값이 `=,+,-,@`로 시작하면 `'` 프리픽스로 무력화(Codex 2-2#4, §18 D9 일부 처리). 어드민 화면 사용자 문자열은 `escH()` escaping(Codex 2-2#5).
- **/api/chat 탈옥 방어**: 클라이언트 `system` 파라미터 무시, 서버 측 고정 가드레일만 사용(QA 확인됨).
- **어드민 인증**: `admin_users` 이메일+비밀번호(bcrypt). staff 계정은 super_admin이 발급·비활성화. 매 요청 admin_users.status='active' DB 확인. 권한 게이트는 §15-2(API 핸들러 레벨, UI 숨김 아님).

---

## 9. 기관 관리자 포털 (/portal)

**기관 관리자(admin) 계정 모델 (v3.2 명문화)**
- **저장**: 기관 관리자는 별도 테이블이 아니라 `institution_rosters`에 **센티넬 과목코드 `subject_code='__ADMIN__'`(`ADMIN_ROSTER_SUBJECT`), `role='admin'`** 행으로 저장된다. 같은 이메일이 관리자 행(`__ADMIN__`)과 과목 학생 행(`HST` 등)으로 충돌 없이 공존(겸직 가능). `role`(시스템 권한, 포털 접근)과 `position`(교수/조교 등, 표시용)은 별개.
- **로그인·식별**: 관리자도 **학생과 동일한 JWT 인증**(`/api/auth/register`·`/verify-email`·`/login`)을 그대로 탄다. 별도 로그인 경로 없음. 인증 후 `users.role='admin'`으로 식별되며, 관리자 등록(role='admin')은 과목·구독·좌석 게이트를 면제받아 가입·인증이 통과한다(슬라이드 접근은 별도 단일 게이트가 과목 좌석으로 판정, §8). **단 `_authenticate`의 구독 만료 면제는 현재 `__ADMIN__` roster 행 존재와 결합**(`_has_admin_roster`) — roster 회수 시 면제·포털 접근 모두 사라진다(§8, Codex#2).
- **등록 플로우 (닫힘)**: ① 계약 후 super_admin이 어드민에서 기관 추가/수정 시 `admin_contacts`(이름·지위·이메일·전화, 최대 5명) 입력 → ② `_upsert_admin_roster`가 `institution_rosters`에 `__ADMIN__`·`role='admin'` 행 등록(같은 트랜잭션) + 커밋 후 **포털 초대 메일 발송**(`_send_portal_invite_email`, 헤더 주입 방어) → ③ 관리자가 **학생과 동일하게 회원가입 → 이메일 인증** → ④ `/portal` 진입(`page_login_required` + `_is_institution_admin`이 `__ADMIN__` roster 행 존재로 판정, `role` 단독 우회 없음 — §8 Codex#1). 기관 수정 시 관리자 제거 = `__ADMIN__` 행만 DELETE(포털 권한만 회수, users 계정·과목 행 불가침).
- 계약 후 super_admin이 기관 관리자 이메일 등록.
- **이용자 명단: (이름 + 지위 + 과목 + 이메일) 축으로 xlsx/csv 업로드** → `institution_rosters`에 등록.
  · roster에는 학생·조교·교수 세 지위의 이용자가 모두 등록된다("학생 명단" 아님 — 교수·조교 포함).
  · 지위(position) = 학생/조교/교수/행정직원. 표시·운영용이며, 시스템 권한 role(viewer/admin)과 별개(§21).
    이용자 명단 행의 role은 'viewer' 고정(구 'student'→'viewer' 정정). 지위는 position 컬럼에 캡처.
  · 과목(subject_code) = 좌석 카운터 축(과목별 독립). 한 이용자가 여러 과목 명단에 들어갈 수 있다.
  · 컬럼/표시 순서는 이름 | 지위 | 과목 | 이메일로 통일(업로드 엑셀·포털 인라인 편집·다운로드 동일).
  · 포털 인라인 편집 시 지위·과목은 드롭다운(지위: 학생/조교/교수).
- 개별 이용자 추가/삭제, 과목별 라이선스 현황(과목당 활성 N / max_seats N). 삭제 시 즉시 접근 차단 + 해당 과목 좌석 반환.
- **이용 리포트**: 과목별 활성/좌석 소진율, 총 열람, AI 튜터 질문수, 많이 본 슬라이드 Top N, 로그인 추세, 마지막 활동. 집계는 과목별 산출 후 기관 롤업. 이 리포트를 super_admin은 학교 선택해 동일하게 열람(§15-7).

**포털 P1 — 명단 관리 (✅ 구현, 2026-06-05 v3.8)**
- 라우트: `GET /portal/api/roster`(명단 조회) · `POST /portal/api/roster`(개별 추가) · `DELETE /portal/api/roster`(제거) · `POST /portal/api/roster/upload`(xlsx/csv 일괄). 화면은 `templates/portal.html` 명단 관리 탭(interceptor.js CSRF 자동주입, esc() XSS 방어).
- **게이트**: 상태변경 라우트는 `@login_required`(더블서밋 CSRF) + `_portal_guard`(=`_is_institution_admin` 재확인, `__ADMIN__` roster 행 존재 단일 기준, role 단독 우회 불가). **scope는 `g.institution_id`로 강제** — body의 institution_id는 어디서도 읽지 않음(타 기관 IDOR 불가, §9 멀티테넌시).
- **과목 입력 allowlist**: `_subscribed_subjects` = 그 기관이 **구독 행을 보유한 과목만**(status 무관, CEO 확정). 미래학기 구독=접근창 닫힘은 분기 C 안전망.
- **★ sync(`_sync_member`) — D17 해결**: 명단 추가/업로드 시 동일 이메일 기존 user의 `position`·`subject_code`를 동기화. 판정식은 register와 **공통 헬퍼(`active_window_subscription`/`active_seat_count`)로 단일화(§0)**.
  · 분기 A(admin-only + 접근창 열림 + 좌석 여유) → NULL→과목 전환(구독행 FOR UPDATE 좌석 직렬화). 좌석부족이면 skip-and-report(전환 안 함).
  · 분기 B(이미 다른 과목 active) → 보류(D12 다과목 미지원, 덮어쓰지 않음). 분기 C(접근창 닫힘) → admin-only 유지(fail-closed). 분기 D(기존 user 없음) → roster 행만 추가(가입 시 채번).
  · **role은 어떤 sync 경로에서도 UPDATE 안 함**(겸직 admin 보존).
- **제거 회수(`_remove_member`)**: 과목 행 삭제 시 그 과목이 user의 현재 active 과목이면 `subject_code`·`position` NULL 회수(좌석 1석 반환 + 단일 게이트가 슬라이드 접근 자동 차단). 계정·role 불변(겸직은 admin-only 복귀, 계정 삭제 없음). `__ADMIN__` 행은 포털에서 제거 불가(읽기전용 — 슈퍼관리자 기관수정 관할).
- **일괄 업로드**: 단일 트랜잭션, 예상된 거절(좌석/다과목/형식/중복)은 skip-and-report(부분 성공), 예기치 못한 에러만 전면 롤백. 행별 outcome 반환. 이메일 정규식·지위/과목 allowlist·중복 dedup·인코딩 폴백·행수 상한(2000)·content-length 상한(5MB).
- P2(구독 플랜)·P3(이용 리포트)는 다음 세션.

---

## 10. AI 튜터 구조 (v1.0)

VectorDB 없이 `knowledge_base` JSON + 슬라이드 메타데이터만으로 Claude API 호출. v2.0에서 system_prompt에 Vector DB 검색 결과만 추가하면 RAG 전환 완료(나머지 코드 무변경).

> ⚠ **현황 주의(QA 발견)**: api_chat이 항상 스트리밍을 반환해 퀴즈(startQuiz)가 JSON 파싱에 실패 → 하드코딩 폴백 퀴즈로 동작. 퀴즈 실제 생성 로직 미완 → §18 부채.

---

## 11. 콘텐츠 현황 (v3.0 — 조달 방식 확정, 공급사 미정)

**조달 방식 확정: 물리슬라이드 구매 → 뷰웍스 일괄 스캔.**
- 디지털 SVS 라이선스 방식이 아니라 **물리 유리슬라이드를 구매해 직접 스캔**하는 방식으로 방향을 확정.
- 사유: 비용(디지털 라이선스 대비 우위), 원본 유리슬라이드 확보, **MPP·품질 직접 통제**, 짧은 리드타임.

**공급사: 율린(Yulin) vs Vic(Vic Science) — 택일 예정 (미확정).**
- 두 곳 모두 물리슬라이드 공급 후보. **가격, 제공 가능한 슬라이드 종류·수량을 종합 비교해 한 곳으로 선택**한다.
- **Vic 견적 대기 중** — 견적 수령 후 율린 견적($600/134장 수준)과 비교해 최종 결정.
- 결정 기준: (1) 커버 가능한 커리큘럼 슬라이드 수, (2) 단가·총액, (3) 품질·리드타임, (4) 장기 라이선스 협력 가능성.

| 공급사 | 상태 | 비고 |
|--------|------|------|
| Yulin (율린) | **후보 A** | 물리슬라이드, 견적 수령(134장 약 $600 수준) |
| Vic Science (Joy Xu) | **후보 B** | 물리슬라이드, **견적 대기 중** |
| Happy Science (Linda Li) | 보류 | SVS 공급사. 향후 글로벌 확장 시 파트너 옵션 |
| 뷰웍스(Viewworks) | 스캔 서비스 | 장당 1만원(VAT 별도), 150장 기준 약 2.5시간 |
| TCGA / 3DHISTECH 샘플 | MVP용 | 일부 |

**저작권 / 공급사 관계 (CEO 거래 원칙)**:
- 우회 프레이밍 없이 정면으로 디지털 라이선스 가치를 설명하고 **연 라이선스비 선제안** 방침(선택된 공급사와 협의).
- 1년차는 물리 구매로 갈음, 2년차부터 연 라이선스 지급 구조를 협의.
- 목적: 분쟁 예방 + 장기 파트너 신뢰. 제조사가 디지털 라이선스 개념이 없더라도 이를 이용하지 않고 정당한 가치를 지급한다.

**미확보 슬라이드**: 중국 공급사에서 조달 불가분은 **v1.0 제외**. 예) brown adipose tissue(미국 Ward's Science만 가능, 라이선스 복잡) — 향후 보충 대상 기록(당장 우선순위 아님). v1.0 확보 목표 = 선택 공급사의 물리슬라이드 중 스캔 완료분.

**일정**: 공급사 결정·송금 → 스캔 완료 목표(견적 확정 후 일정 확정).

> 외부 문서에 중국 제조사명 미기재 원칙(공급망 보호). 파일명 규칙·메타데이터 엑셀 양식은 스캔 전 확정.

---

## 12. QA 거버넌스 — 3단계 검증 구조

```
Claude Code 내부:  Lead Developer(구현) ↔ QA 에이전트(레드팀, 섹션당 max 3회)
   ↓ 내부 QA 통과
Codex 외부 검증(엣지케이스 이중검증)
   ↓ 통과
CEO(보람) 최종 승인 → 다음 섹션
```

**워크플로우 통제**: 내부 핑퐁 max 3회 초과 시 중단→CEO 판단. Codex 통과 없이 다음 섹션 금지. **인프라 변경(RDS/EC2/S3)은 CEO 명시 승인 없이 절대 실행 금지.** QA·검증 에이전트는 읽기 전용(코드·grep·로컬 pytest만, DB 쓰기·SSH·마이그레이션 실행 금지). 토큰 절약 위해 전체 재작성보다 diff 우선.

**QA 5대 무조건 체크리스트 (하나라도 미통과 시 Reject)**
1. **보안·멀티테넌시·과목 구독 격리(단일 게이트)**: **슬라이드 접근은 `_slide_access_allowed` 단일 게이트만 사용** — `deploy_status=='deployed'` AND `g.subject_code==slide.subject_code` AND 기관이 그 과목 구독/접근권 보유. **"슬라이드 기관==사용자 기관" 비교 잔존 0건**, **"deploy_status만 검사하는 공용 허용" 완화 금지**(§0-4·§8). JWT 변조 방어, 1기기 동시접속, 타일토큰 대조·TTL·재발급 게이트, no-store 헤더, 계정잠금(24h/10회), 인증코드 재발송 한도, CSRF(interceptor 전 fetch 경로 적용), **접근창 내 구독 만료 매요청 검사(fail-closed)**, **특별계정 special_expires_at 집행**, ADMIN_SECRET_KEY fail-closed, /api/chat 탈옥 방어. **어드민 권한 게이트(super_admin/staff) 우회 불가.**
2. **파이프라인 안전성**: COG 스트리밍(전체 메모리 로드 금지), QC 실패·ready_no_mpp가 ready로 전환 안 됨, 미니맵·썸네일 S3 경로 정확, ready_no_mpp 배율 버튼 비활성.
3. **비즈니스 로직·온보딩 순서**: 만료 사용자 접근 차단+결제 유도, **변환 ready여도 deploy_status='deployed' 아니면 학생 비노출**, **과목별 좌석 카운터(max_seats) 정확**, **구독(접근창 내 active) 없으면 가입·인증 거부**(SUBSCRIPTION_INACTIVE, §6-3).
4. **DB 마이그레이션**: 트랜잭션 처리, 중간 에러 전면 Rollback.
5. **라이선스 격리**: 미배포 슬라이드 비구독 노출 차단, 반려(rejected) 원본 비노출(특별계정 포함), license_source 콘텐츠 외부 유출 경로 차단.

---

## 13. 개발 원칙 & 주의사항

### 13-1. 일반 원칙
- **AWS 자격증명**: nohup 컨텍스트에서 인라인 치환 실패 → 환경변수 먼저 export.
- **Windows SCP**: PEM 권한은 비관리자 PowerShell에서 icacls.
- **한국어 PDF**: reportlab/weasyprint 한글 폰트 한계 → Illustrator 직접.
- **중국어 문서**: Node.js docx, SimSun TextRun 별도 분리.
- **COG 변환 배치**: SVS 1장 5~15분, 134장 최대 30시간 → EC2 밤샘 배치.
- **매출 우선**: 정부지원(초창패)보다 9월 매출 데이터 확보가 최우선.
- **모듈 경계**: `ConversionJob`/`ConversionResult` 데이터 계약 변경 금지.
- **과목 축 단축 금지(§0-4)**: "어차피 HST 하나니까"라는 이유로 subject_code 검사를 생략하는 코드를 작성하지 않는다.

### 13-2. 인증·구독 코드 불변식 (v3.0 신설)
- 만료 검사 = (institution_id, subject_code) → subscriptions.subscription_end. institutions.* 참조 금지.
- 정원 검사 = (institution_id, subject_code) → subscriptions.max_seats. institutions.max_users 참조 금지.
- 가입 = institution_rosters의 (institution_id, subject_code, email) 매칭 + users.subject_code 채번.
- 반환 shape(데코레이터·_authenticate 튜플 길이)를 바꾸는 수정은 다운스트림 언패킹·테스트 회귀를 유발하므로 신중히. 변경 시 인증 테스트 전수 재실행.

---

## 14. 주요 외부 연락처

- Yulin(율린): Jessy, Cathy — 물리슬라이드 후보 A (견적 수령)
- Vic Science: Joy Xu / joy@vicscience.com — 물리슬라이드 후보 B (견적 대기)
- Happy Science: Linda Li / info@ihappysci.com (보류, 글로벌 확장 옵션)
- 뷰웍스(Viewworks): 스캔 서비스 (장당 1만원+VAT)
- 성원애드피아: 명함 인쇄

---

## 15. 슈퍼관리자 어드민 (구현 사양)

> 화면 사양은 `docs/mockups/`의 HTML 목업 6개를 1차 사양서로 삼는다(§17).

### 15-1. 탭 구조
```
[운영]      대시보드 · 기관 관리 · 슬라이드 관리 · 접근 제어 · 이용 리포트 · 특별 계정
[고객 응대]  공지 관리 · 1:1 문의
```

### 15-2. 권한 (2단계)
| 탭 | super_admin | staff |
|---|---|---|
| 대시보드 | ✅ | ✅ 읽기만 |
| 기관·슬라이드·접근제어·이용리포트·특별계정 | ✅ | ❌ (사이드바에서 숨김) |
| 공지 관리 | ✅ | ✅ |
| 1:1 문의 | ✅ | ✅ |
- staff에는 운영 그룹 탭이 사이드바에서 노출되지 않고 **API 레벨에서도 차단**. 액션 버튼(추가/갱신/비활성화 등)도 숨김.
- 모든 작성/수정/답변에 `created_by`(admin_users.id) 기록.

### 15-3. 슬라이드 배포 상태 (변환 상태와 별개)
```
qc_pending(배포 대기) → deployed(배포 중) ↔ revoked(철회→배포 대기로 복귀)
                      ↘ rejected(반려, 사유 기록)
```
- **반려(rejected)**: 변환은 됐으나 원본 품질 문제(조직 찢어짐·초점 흐림 등). 사유 기록 → **학생·특별계정 모두 비노출** → 공급사 재공급/재스캔 요청 목록에 자동 등록 → 원본 보존(삭제 금지) → 대체본 도착 시 같은 slide_id로 재업로드. 반려 이력 보존. (재공급 목록은 2번째 모듈 시점에 구현.)
- **철회(revoked)**: 배포했던 것을 내림 → qc_pending 복귀(내부 결정, 공급사 클레임 아님).
- **배치 QC**: 체크박스 다중선택 → "선택 항목 일괄 배포/반려". 134장 대응.

### 15-4. 기관 추가/수정/갱신 (§16 모델 기반)
- 기본 정보: 학교명·단과대·(영문)·이메일 도메인. (슬라이드ID/기관코드 입력 없음 — SA 고정.)
- 구독: **과목별 구독 카드**(과목 + 좌석플랜/좌석수 + 시작학기 + 학기수 + 구독료 + 결제). "+ 과목 구독 추가"로 줄 추가. **v1.0은 과목 구독 카드 1개(HST)일 뿐, UI·데이터는 N개 카드를 지원**(과목 단일은 우연이지 전제가 아님 — §0-4).
- 좌석: 플랜 선택 시 자동, 직접 수정 가능(특수계약 좌석 직접 지정). 좌석은 과목 카드별 독립.
- 학기/접근창: §16 학기제. 오픈일·만료일 자동 계산(읽기전용).
- 관리자 등록 최대 5명(이름/지위/이메일/전화). 저장 시 SES 포털 안내 발송.
- 갱신: **과목 단위**. 현재 학기 다음 학기 자동 세팅, 이력 누적 보존(`subscription_history`).

### 15-5. 슬라이드 QC / 파이프라인
- 변환 상태(자동) + 배포 상태(사람) 2축 표시. 상태 필터 칩.
- 개별 추가: 파일 업로드 + 메타데이터, **MPP 입력칸 없음**, 기관 SA 고정, 과목 선택 필수, 공급원→푸터. (§5-2)
- ready_no_mpp: 인라인 MPP 입력 + 재처리. failed: 로그 보기 + 재변환.
- 검수 모달: kb 자동 초안(핵심구조/시험포인트/혼동주의/한국어 관찰포인트) 편집 후 배포. (§5-4)

### 15-6. 접근 제어
- **콘텐츠 모듈 레지스트리**(조직학 활성 / 병리·기생충 준비중). 좌석↔콘텐츠 분리(§16).
- **기관 × 모듈 매트릭스**: 조직학은 전 기관 자동·잠김. 병리·기생충 열은 출시 후 토글. 이 매트릭스는 기관 관리 데이터에 연동(기관 추가 시 행 자동 생성)되며, **2번째 모듈 출시 시점에 구현**. v1.0은 미리보기.
  - ⚠ 구현 시 주의: 모듈 활성 판단의 진실은 `subject_codes.is_active`(DB)다. 코드 상수(frozenset 등)와 DB가 두 진실로 갈리지 않도록 단일화. (QA 잠재 위험 지적.)

### 15-7. 이용 리포트
- 기관 관리자 포털 리포트와 동일 화면 + **학교 선택 드롭다운**. **집계 단위는 과목별 → 기관 롤업**(개별 학생 추적 지양). 좌석 소진율 = 과목별 (활성 사용자 / max_seats). 엑셀/PDF 내보내기.
  - ⚠ 내보내기 주의: 기관명·chat_logs 등 사용자 제어 문자열이 `=`,`+`,`-`,`@`로 시작하면 CSV 수식 주입 위험 → 셀 값 앞 이스케이프. (QA 잠재 위험 지적.)

### 15-8. 특별 계정
- 자문위원·검수자·데모·공급사 평가. 구독 만료 무관(is_special), 워터마킹 동일.
- **콘텐츠 접근 범위(CEO 결정)**: qc_pending(미배포)·deployed 접근 허용(검수 목적), **rejected(반려)는 차단**. institution 축은 특별계정 정책상 우회 허용.
- **선택적 만료일 + 사전 알림(14/30일 전)**. 무기한은 비권장(잊힌 계정 = 보안·라이선스 구멍) → "검토 권장" 경고.

### 15-9. 공지 관리
- 랜딩 공지, **최대 5개 동시 노출**, 순서 지정. 게시↔숨김.
- **소프트 삭제(보관함)**: 삭제 시 보관함 이동(이력 보존). 복원 시 숨김 상태로 복귀. 완전 삭제는 보관함에서 확인 후 영구 제거. super_admin·staff 모두 가능, created_by 기록.
- 비로그인 노출 시 `is_published=TRUE AND is_archived=FALSE`만, title+date만 반환(created_by/보관함 미노출 — QA 확인됨).

### 15-10. 1:1 문의
- "사이트 사용 전반 / FAQ 미해결" 문의. 접수 시 **기관 정보 자동 첨부**(로그인 시 institution_id, 비로그인 NULL) → staff가 운영 탭 접근 없이 응대. (관련 슬라이드란은 두지 않음.)
- 답변은 SES 발송, 작성자 기록(created_by). 상태 open/answered. **메일 발송 성공 시에만 `answered` 전환**(실패 시 open 유지+경고, 조용한 실패 방지). 메일 헤더 주입 거부·HTML escaping(§8, v3.1).
- ⚠ **개인정보 동의 저장 공백**: 문의 폼이 동의를 받으나 inquiries에 privacy_agreed 컬럼 부재로 미저장. 출시 전 필수 처리(§18).

### 15-11. 대시보드
- KPI: 활성 구독 기관 / 이번 학기 확정 매출 / **활성 사용자·과목별 좌석** / 만료 임박(D-90 내).
- 만료·갱신 임박 D-day 리스트(과목 단위), 학기별 매출 추이, 파이프라인 현황, 처리 대기(미답변 문의·검수 대기·MPP없음·갱신 협의).

---

## 16. 가격·구독 모델 (v3.0)

- **좌석 플랜이 기본 가격축**: Department(50) / Standard(150) / Campus(300) / Institution(500+). 특수계약은 좌석 수 직접 지정.
- **학기 단위 라이선스**: 봄학기(3/1~8/31) / 가을학기(9/1~익년 2월말). 라이선스는 6개월 단위. **방학 접근 허용**(여름·겨울방학 포함, 복습 목적).
- **접근 오픈일 = 학기 시작 −30일**(봄 2/1, 가을 8/1). 학기 첫날 혼란 방지 위해 한 달 일찍 오픈(편의 제공이며 라이선스 기간과 별개). 신규·재구독은 이전 만료일이 없으므로 겹침 문제 없음.
  - 날짜 경계는 **KST(UTC+9) 기준으로 일관 처리**(`_today_kst`). 접근창·만료 검사가 UTC와 하루 어긋나지 않게 코드에 반영됨(v3.1, §18 D10 부분 처리).
  - **접근창 집행**: 만료/가입 검사가 `access_open_date <= today <= subscription_end`(접근창)를 본다. 미래 학기 구독이 미리 active여도 창 전엔 접근·가입 불가(§8, Codex #3).
- **참고 가격**: 연 ₩4,000,000 / 학기 ₩2,500,000(학기 단가에 의도적 할증으로 연납 유도). 실제 가격은 딜별 확정.
- **베타·런칭 모델 (v3.1 일반화)**: 베타는 **특정 학교 고정이 아니라 "6개월 무료 → 구독 전환" 모델**로 운영한다(active sales lead/베타 후보를 대상으로 협의). 무료 기간도 동일하게 (기관×과목) 구독 레코드(접근창·좌석)를 생성해야 학생이 가입·접근할 수 있다(§6-3 온보딩 순서). 특정 학교를 "확정 베타 파트너"로 문서에 고정하지 않는다.
- **좌석과 콘텐츠는 분리(직교)**: 좌석 플랜 = 규모·가격, 콘텐츠 모듈 = 무엇을 여는가. **HST(조직학)는 v1.0의 첫 런칭 과목일 뿐 "자동 부여/기본 제공"이 아니다** — 다른 과목과 똑같이 (기관×과목) 구독이 있어야 열린다(§6-1). 어떤 기관은 PARA만 구독할 수 있다.
- **구독·좌석·만료·정원은 (기관 × 과목) 단위로 독립**(§0). 과목마다 좌석 카운터(max_seats)가 독립(예: 조직학 의대 150석 + 기생충학 기생충학교실 30석). 과목별로 좌석·학기·구독료·갱신이 모두 따로 굴러간다. → 구독 = (기관 × 과목) 단위(`subscriptions`).
- **정원 검사 = subscriptions.max_seats(과목별)**. institutions.max_users(deprecated) 사용 금지(§13-2).
- 신규 과목(병리·기생충) 가격(별도 과금/번들/상위티어)은 **출시 시점에 결정**(데이터 모델이 셋 다 지원).

---

## 17. 화면 사양서 (목업)

구현 1차 사양은 `docs/mockups/`의 HTML 목업이다(클릭 가능한 인터랙션 포함):
- `institution_modals.html` — 기관 추가/수정/갱신 (과목별 구독 카드, 학기제)
- `slide_qc.html` — 슬라이드 QC/파이프라인 (2축 상태, 배치 QC, 검수 kb, 반려, MPP 재처리, 개별 추가)
- `access_reports_special.html` — 접근 제어·이용 리포트·특별 계정
- `notices_inquiries.html` — 공지 관리(보관함)·1:1 문의(권한 분리)
- `admin_integrated.html` — 전체 통합 대시보드(IA·대시보드)
- `institution_portal.html` — 기관 관리자 포털 /portal (명단관리·구독플랜·이용리포트 3탭, 과목별 좌석·SA 채번)

> 목업과 본 문서가 충돌하면 본 문서(CLAUDE.md)가 우선. 목업은 레이아웃·동작 참조용.

---

## 18. 기술부채 & 출시 전 필수 항목 (v3.0 신설 — 단일 집결지)

> 의도적으로 미룬 항목과 출시 전 반드시 닫아야 할 항목을 한곳에 모은다. 보고서·세션에 흩어지지 않게 한다.
> 상태: 🔴 출시 전 필수 / 🟠 v1.5 전 필수 / 🟡 추적

| ID | 항목 | 내용 | 상태 | 조치 주체 |
|----|------|------|------|-----------|
| D1 | inquiries.privacy_agreed 컬럼 | 개인정보 동의 저장 공백(법적). 문의 폼은 동의받으나 DB 미저장 | 🔴 출시 전 필수 | CEO 승인 → ALTER |
| D2 | SES 발송 전환 | Gmail SMTP → SES 교체(도메인 인증 후). 현재 문의 답변 발송. **★ e2e(2026-06): EC2 Gmail SMTP 미설정으로 가입 인증코드 메일 미발송(users·코드는 생성되나 미수신). 9월 학생 가입 출시 블로커. 임시 Gmail SMTP 앱비번 또는 SES 전환. 인증코드 메일은 제거된 포털 초대메일과 별개로 반드시 발송.** | 🔴 출시 전 필수 | 도메인 인증 후 |
| D3 | ADMIN_SECRET_KEY 환경변수 | ✅ 코드 fail-closed 완료(미설정 시 기동 실패, Codex #6). Render 환경변수 설정 완료 확인됨(3회 검증). | ✅ 완료 | 확인 |
| D4 | users.subject_code 채번 | ✅ 완료(코드, 커밋 17bb18a). register()가 roster의 subject_code 캡처→users 채번, verify_email() 누락 거부, login·_authenticate NULL 폴백 제거 완료. 정원 검사도 subscriptions.max_seats 이전 완료(커밋 ddfab51). pytest 45/45 | ✅ 완료 | Lead Developer |
| D4b | 라이브 DB NULL subject_code 0건 확인 | 코드/시드상 사용자 0건이나, 출시 전 EC2에서 `SELECT COUNT(*) FROM users WHERE subject_code IS NULL` 1회 실행해 0건 최종 확인(존재 시 백필 필요). RDS는 EC2 전용 VPC라 코드 작업자 접속 금지(§12·§19) | 🔴 출시 전 필수 | CEO |
| D5 | institutions 옛 구독 컬럼 DROP | subscription_plan/start/end, max_users. 코드 미참조화 완료, 데이터만 잔존 | 🟠 v1.5 전 | CEO 승인 → DROP |
| D6 | 퀴즈 실제 생성 로직 | api_chat 항상 스트리밍 반환 → startQuiz JSON 파싱 실패 → 폴백 퀴즈. 실제 생성 미구현 | 🟠 v1.5 전 | Lead Developer |
| D7 | 미니맵/썸네일 파이프라인 | §4-2 "S3 사전 생성" 원칙 vs 현재 동적 생성. /minimap 라우트 부재 | 🟠 v1.5 전 | Lead Developer |
| D8 | 기관×모듈 매트릭스 | 2번째 모듈 출시 시점 구현. subject_codes.is_active(DB) 단일 진실 | 🟠 2번째 모듈 시 | Lead Developer |
| D9 | 리포트 집계 과목별 산출 (Codex #7) | 이용 리포트가 과목별 산출 → 기관 롤업이어야 한다(§9·§15-7). 현재 일부 집계가 과목 축을 충분히 분리하지 않음. (XLSX 수식 주입 방어는 별건으로 완료 — 2-2#4.) | 🟠 v1.5 전 | Lead Developer |
| D10 | 날짜 타임존 일관성 | ✅ 인증·접근창·만료·가입 경로는 `_today_kst`(KST)로 통일 완료(v3.1). 잔여 경로(리포트 기간 계산 등) 점검은 추적 | 🟡 추적(주요 경로 완료) | Lead Developer |
| D11 | DB 커넥션 release 전수 | get_db_conn/release_db_conn 누수 전수 카운트 미완 | 🟡 추적 | QA |
| D12 | 다중 과목 접근 (정책 확정 v3.2, Codex#3·Gemini#5) | ✅ 정책 확정: **이메일당 users 1계정, 과목 접근은 institution_rosters 행으로 표현, users.email 전역 UNIQUE**(§6-2). register가 이메일 전역 검사로 중복 계정/pending 생성 차단(앱 레이어). 잔여: ① DB 차원 email 전역 UNIQUE 제약 추가(별도 마이그레이션, 기존 데이터 점검 후) ② 단일 `users.subject_code` 게이트라 한 계정이 여러 과목을 동시에 여는 다과목 열람은 미구현 — v1.5(다과목 출시) 시 처리. **(구분: 수업 다대다 등록은 `course_enrollments`로 v1.0에서 지원한다 — 한 학생이 여러 수업에 등록 가능하며, 이는 과목 구독 다레코드(D12)와는 별개 축, §21.)** | 🟠 v1.5 전(정책은 확정) | Lead Developer |
| D13 | 온보딩 순서 운영 체크리스트 | §6-3 순서(구독 계약·입금 → institution_subject_access/subscriptions 생성 → roster 등록 → 학생 가입)를 운영 절차로 문서·교육. 코드는 강제하나(SUBSCRIPTION_INACTIVE), 베타·신규 계약 시 ② 선행 누락하면 학생이 가입 불가 → 운영 사고 방지. **추가(v3.9): 과목 이동 = 기존 과목 명단에서 삭제 후 새 과목에 추가(2단계). 자동 전환 없음(D12 단일 subject_code).** | 🔴 출시 전 필수 | CEO/운영 |
| D14 | Locust 부하 테스트 (7월 말) | 표적: 동시 가입·로그인 시 `FOR UPDATE` 좌석 잠금(over-seating/데드락), 동시 타일 요청 EC2 부하, 커넥션 풀 고갈(D11 연계), 로그인 폭주 시 계정잠금 동작. (타일 경로 DB 병목은 v3.2에서 토큰 인증 분리로 해소 — §8.) | 🟠 v1.5 전(7월 말) | Lead Developer/QA |
| D15 | 다중 기관 관리자 포털 접근 (Gemini#2) | 한 사람이 여러 기관의 관리자인 경우, 현재 포털 scope가 로그인 사용자의 단일 기관(`g.institution_id`)으로 고정돼 다른 기관 포털에 갇힌다. v1.0 범위 밖(드묾). **v1.5 과제: `/portal/<institution_id>` 또는 포털 내 기관 선택 드롭다운**으로 다중 기관 관리자 지원 | 🟡 v1.5 과제(기록만) | Lead Developer |
| D16 | EC2 정식 배포 이전 (9월 런칭 = EC2) | **결정 변경(v3.2): 과거 "9월 Render 런칭 → 구독 증가 시 AWS 이전" 합의를 폐기하고, 9월 정식 런칭부터 EC2로 간다.** RDS는 퍼블릭 액세스 '아니요'(VPC 프라이빗)이며 같은 VPC의 EC2(기존 t3.medium 타일서버)에서만 접속 가능. 정석 구조: EC2에서 Flask를 gunicorn+nginx+TLS로 구동(현재 Flask 개발서버·Render는 임시 개발 환경). 포털·기능 개발 완료 후 EC2 이전 → slide-atlas.net DNS를 EIP(3.34.35.58)로 전환 → Render 폐기. | 🔴 출시 전 필수 | CEO |
| D17 | 콘텐츠 비소비 관리자 역할 미커버 | 현재 모델은 '과목(subject) roster 행 유무'가 좌석·지위·콘텐츠 소비를 한 덩어리로 묶는다(§6-4). 그래서 "슬라이드는 안 보면서 명단 관리만 하는 교수/조교"(지위는 있으나 콘텐츠 비소비)를 표현하지 못한다 — subject+__ADMIN__으로 넣으면 불필요하게 좌석을 점유하고, __ADMIN__만 넣으면 position이 NULL이 된다. **v1.0 운영 회피책(CEO 확정): 해당 구성원을 '행정직원'으로 등록하도록 안내하고 "기술적 제약이며 곧 수정 예정"이라 설명한다.** v1.5에서 모델 확장(좌석 비점유 플래그 또는 __ADMIN__ 행 position 허용)으로 정식 처리, D12(다과목)와 함께 검토. **★ e2e(2026-06): 슬라이드를 볼 조교/교수를 과목 이용자 명단 등록 전에 기관관리자(__ADMIN__)로 먼저 지정하면, 가입 시 admin-only(subject_code/position NULL)로 굳어 행정직원처럼 인식되고, 이후 과목 명단에 올라도 기존 user의 position/subject_code가 자동 갱신되지 않음(가입 시점 캡처값 고정). 온보딩상 관리자(조교)가 명단보다 먼저 가입하는 게 흔해 빈발. '과목 명단에도 함께 등록' 회피책은 슈퍼관리자 UI 부재·운영부담으로 비현실적이라 폐기. ★해결: P1(명단 관리) 구현 시 '명단 추가/업로드 시 동일 이메일의 기존 user가 있으면 position·subject_code 동기화'를 핵심 요구사항으로 포함. 설계 결정사항: ①좌석 재검사(NULL→과목 전환 시 좌석 1 점유, max_seats 초과 처리) ②다과목(D12) 동시 active 처리 ③role/position 경계(subject만 갱신, role 불변) ④일괄 업로드 성능·트랜잭션 ⑤명단 제거 시 subject_code 회수 방향. 인증·좌석 닿으므로 §12 풀 거버넌스(Codex/Gemini) 대상.** **✅ 해결(2026-06-05 v3.8): 포털 P1 `_sync_member`가 명단 추가/업로드 시 동일 이메일 기존 user의 position·subject_code를 동기화한다 — admin-only(NULL)→과목 전환(좌석 재검사 FOR UPDATE), 다른 과목 active는 보류(D12), 접근창 닫힘은 보류(fail-closed), role 불변(겸직 보존). 판정식은 register와 공통 헬퍼(active_window_subscription/active_seat_count)로 단일화(§0). 제거 시 좌석 회수·계정 보존. 잔여: 다과목 동시 active(D12)는 v1.5.** | ✅ P1 해결 / 잔여 D12 v1.5 | Lead Developer |
| D18 | institutions에 고객/소유자/공급사 혼재 | institutions 테이블이 구독 고객 학교 + 콘텐츠 소유자(SA) + 공급사(Happy Science 등)를 한 테이블에 담아, 공개 엔드포인트 GET /api/institutions가 셋을 모두 가입 드롭다운에 노출한다. **출시 전 필수: is_subscribable 플래그(또는 kind 컬럼)로 가입 드롭다운을 고객 학교로 한정**(SA·공급사 제외). 소싱처는 acknowledgement가 필요한 경우(예: 마히돌)에만 별도 노출. **v1.5: suppliers 테이블 분리 + slides.license_source FK화.** §6-1 license_source 설계와 정합. **★ e2e(2026-06): is_subscribable 플래그 방식으로 1차 구현했으나(institutions에 컬럼 추가 + GET /api/institutions WHERE is_subscribable=TRUE), 이는 슈퍼관리자가 기관마다 TRUE/FALSE를 수동 관리해야 해 운영부담·누락 위험이 크고, 구독 없는 학교(KU/SNU/YU 등)가 드롭다운에 남는 문제. ★재설계(P1): 드롭다운 노출 기준을 '플래그'가 아니라 '구독 존재 여부'로 변경 — /api/institutions가 subscriptions에 행이 있는(=슈퍼관리자가 구독 플랜을 입력한) 기관만 반환(status 무관, 무료 베타도 구독 레코드 있으므로 포함). 이러면 SA·공급사는 구독 없어 자동 제외, 새 학교는 구독 입력 즉시 자동 노출, 플래그 관리 불필요. is_subscribable 컬럼은 폐기(죽은 컬럼으로 두거나 DROP). §11 공급사 비공개·§6-3 구독 선행 원칙과 정합. 현재 EC2에는 is_subscribable=TRUE 필터가 배포된 상태이며 SA·HS·MU만 FALSE 처리됨 — 임시 상태.** **✅ 드롭다운 기준 교체 완료(2026-06-05 v3.8): `GET /api/institutions`가 `SELECT DISTINCT i.id, i.name_ko FROM institutions i JOIN subscriptions s ON s.institution_id=i.id ORDER BY i.name_ko`로 변경 — 구독 행 보유 기관만 노출(status 무관). SA·공급사는 구독 없어 자동 제외, 새 학교는 구독 입력 즉시 자동 노출. 코드의 is_subscribable 참조 0건(죽은 컬럼). 잔여(v1.5): is_subscribable 컬럼 DROP + suppliers 테이블 분리.** | 🟠 v1.5(is_subscribable 컬럼 정리·suppliers 분리) ✅ 드롭다운 기준 교체 완료 | Lead Developer |
| D19 | 발송 실패 시 가입 트랜잭션 정책 미정의 | register 메일 발송 실패 시 users(pending)·email_verifications 잔존 → 재발송 반복 실패 시 pending 누적 + 같은 이메일 재가입 EMAIL_EXISTS 교착 가능. 정책 미정((가)남기고 재발송/(나)전체 롤백/(다)재가입을 기존 pending 재발송 우회). 현재 동작 코드 확인 후 확정. D2와 묶임. | 🟠 v1.5 전(D2 후속) | Lead Developer |
| D20 | 현재-접근창 테스트 구독 생성 수단 부재(개발 편의) | 가을 런칭 기준이라 기관 등록 시작학기 선택지가 2026 가을부터·갱신은 다음 학기만 → 개발/QA 시 '지금 접근창 열린' 테스트 구독을 UI로 못 만들어 psql로 access_open_date 임시 조정 필요(e2e 사용). | 🟡 추적(개발 편의) | Lead Developer/QA |
| D21 | 접근 모델 이원화(게이트 vs 가입) | `_slide_access_allowed`(슬라이드 단일 게이트)는 `institution_subject_access.granted=TRUE` **OR** 접근창 active 구독을 보는 반면, register·_authenticate·포털 sync는 **구독만** 본다(Gemini 발견). 정상 운영에선 구독 생성 시 institution_subject_access를 함께 INSERT해 불일치가 안 나지만, granted-OR 가지가 사실상 잉여(dead branch)다. 구독 단일화 방향으로 게이트 정리 검토. **게이트 변경은 슬라이드 접근 전반에 닿으므로 별도 §12 세션.** | 🟠 v1.5/별건 | Lead Developer |
| D22 | 좌석 mutex tie(동시성 코너) | 같은 (기관×과목)에 접근창 겹치는 active 구독이 2개 이상이고 `subscription_end`가 동률(tie)이면, FOR UPDATE가 `ORDER BY subscription_end DESC LIMIT 1`로 서로 다른 행을 잠가 마지막 좌석이 중복 통과할 여지(Codex). 정상 운영 미발생(과목당 구독 1개 — UNIQUE(institution_id,subject_code,start_term)이나 학기 다르면 복수 가능). 7월말 Locust(D14) 동시성 검증 대상. | 🟡 추적(D14) | Lead Developer/QA |

**✅ v3.1에서 닫힌 항목 (Codex 외부 검증 묶음 A·B, pytest 65/65)** — 표에서 별도 행 불요:
- **#1 SA 슬라이드 접근 / #2 과목 IDOR** → 단일 게이트 `_slide_access_allowed`로 통합, 기관일치 화석 제거(커밋 db6a1ae).
- **#3 access_open_date 접근창 집행**(커밋 01ab005) / **#5 특별계정 special_expires_at 만료 집행**(커밋 2c21b81).
- **#6 ADMIN_SECRET_KEY fail-closed** / **#4 구독 없는 가입·인증 거부(SUBSCRIPTION_INACTIVE)**(커밋 70dbfee).
- **2-2#3 문의 답변 실패 시 answered 금지+헤더/HTML 주입 방어**(57a5169) / **2-2#4 XLSX 수식 주입 방어**(06c50b9) / **2-2#5 admin 화면 XSS escaping**(202d598) / **2-2#2 타일 토큰 무중단 재발급**(24325ec).
- 직전(묶음 A 전): **FAIL1 만료 fail-closed**(0a34592) / **WARN2 roster is_verified 과목 한정**(087895c).

---

## 19. 인프라 접속 정보

### RDS PostgreSQL
| 항목 | 값 |
|------|------|
| 엔드포인트 | slideatlas-db.c94iwikwox6l.ap-northeast-2.rds.amazonaws.com |
| DB명 / 유저 / 포트 | slideatlas / slideatlas_admin / 5432 |
| 리전/AZ | ap-northeast-2 / ap-northeast-2c |
접속: EC2 Instance Connect → psql (로컬 psql 불필요). RDS Security Group은 EC2 IP만 인바운드 허용(VPC 내부 전용).

### EC2 SSH (Windows)
| 항목 | 값 |
|------|------|
| 고정 IP(EIP) | 3.34.35.58 (재시작해도 고정) |
| PEM | C:\Users\아무개\slideatlas-key.pem |
| 명령 | ssh -i "C:\Users\아무개\slideatlas-key.pem" ubuntu@3.34.35.58 |
| PowerShell | 반드시 비관리자 PowerShell |

> ⚠ RDS는 퍼블릭 액세스 '아니요'(VPC 프라이빗), EC2(같은 VPC)만 접속 가능. 외부(로컬·Render)에서 직접 접속 불가. 앱의 정식 구동 위치는 EC2 — §18 D16.

---

## 20. 환경·인프라 점검 (코드 검증 사각지대 — 별도 문서 포인터)

> **본문은 `docs/INFRA_CHECKLIST.md`(운영 매뉴얼급)에 있다. 이 섹션은 요약·포인터다.**
> 인프라·환경 운영 절차의 1차 기준은 그 문서이며, 인프라 영역에서 본 문서와 충돌 시
> `INFRA_CHECKLIST.md`가 우선한다.

**왜 별도 문서인가 (핵심 원칙)**: Codex·Gemini·Claude Code QA(§12)는 **git에 올라간 코드만** 본다.
코드 안에서 추론 가능한 결함(IDOR·인증 우회·권한 게이트·SQL 안전성)은 잘 잡지만,
**git 밖의 것 — 환경변수 실제 설정값, 인프라 구성(systemd·nginx·TLS·보안그룹·DNS·S3 정책),
라이브 DB 데이터 상태, 배포 환경 — 은 구조적으로 못 본다.**

> ★ **실제 사고(2026-06)**: JWT_SECRET_KEY가 Render에 설정 안 됐는데, 코드·프론트·백 외부검증을
> 다 돌렸어도 아무도 못 잡았다. **코드엔 결함이 없었기 때문**(코드는 환경변수를 *읽는 법*만 알 뿐
> 그게 *실제로 있는지*는 모름). 같은 세션에서 어드민 해시 앞부분 잘림, reboot 후 타일서버 미기동도
> 코드 검증으로는 안 잡히는 환경/인프라 문제였다. → **"코드가 맞다 ≠ 배포가 맞다."**

**검증 책임 분리**:
- 코드 로직 → Codex·Gemini·Claude QA (§12)
- 환경변수·인프라·라이브 데이터·배포 환경 → **사람이 `INFRA_CHECKLIST.md`로 점검** (AI 대체 불가)
- 부하·동시성 → Locust (§18 D14)

**INFRA_CHECKLIST.md 구성**: A 사각지대 개념지도 / B 런칭 전 종합 체크리스트(환경변수·자동기동·
TLS·DNS·RDS·S3·라이브데이터·옛서버제거·스모크테스트) / C 정기점검(주간·월간·학기경계) /
D 사고대응 Runbook(로그인오류·전체다운·타일·TLS·보안) / E 책임경계 / F 부록(타일서버 systemd 등록·
삼켜진 예외 드러내기·어드민 비번 재설정·재시작 기본기).

**운영 규칙**:
- **Codex/Gemini가 OK해도 `INFRA_CHECKLIST.md` B절을 통과 못 하면 런칭 금지.**
- 모든 인프라 명령은 EC2(Instance Connect)에서 **CEO가 직접 실행**, AI SSH 직접 실행 금지(§12).
- 런칭 전 B절은 "AI가 확인했다"로 대체 불가 — **명령 출력/콘솔을 사람 눈으로 대조**.
- 관련: §12(QA 거버넌스) · §18(기술부채, 특히 D2 SES·D3 시크릿·D4b 라이브 NULL·D14 Locust·D16 EC2) · §19(접속정보).

---

## 21. 교수 수업 페이지(LMS) — v1.0 정식 범위

> **포지셔닝**: "땡시 대비, 집에서 한국어로." Histology Guide류(영어·무료) 대비 차별점은
> **한국어 + 국가고시 연계 + 교수 지정 커리큘럼**이다. LMS가 v1.0의 핵심 과금 근거다.

### 21-1. 모델 (지위 ⊥ 역할 — 두 별개 축)
- **지위(position) 4개**: 교수 / 조교 / 학생 / 행정직원. roster에 기관 관리자가 등록한다.
- **역할(role) 2개**: `viewer` / `admin`. **position과 role은 별개의 두 축**이다.
- **admin은 별도 지위가 아니라 4개 지위 누구에게나 얹히는 플래그**다(겸직, §6-4).
- **행정직원**: 슬라이드 열람·즐겨찾기 **제외**, 기관×과목 구독 TO(좌석)에서도 **제외**(좌석 0, 콘텐츠 비소비). admin이 얹히면 roster 관리·리포트만 수행한다. 행정직원은 subject roster 행을 갖지 않고 admin-only 계정(position NULL)으로 표현한다.
- **슬라이드 접근은 과목 구독만**(§8 단일 게이트 유지). **수업(course)은 접근 게이트가 아니라 학습 경로/커리큘럼**이다. **수업 미등록이어도 구독 과목 슬라이드는 전체 열람 가능.**

### 21-2. 수업 구조
- 수업은 **특정 과목(`subject_code`) 안에서만** 개설된다. **수업 = 페이지 1개**(예: "조직학 실습 2026-2학기").
- 구조: **수업 → 주차 → 슬라이드** (주차 안에 추가 계층 없음).
- 주차는 교수가 자유 구성. **빈 주차 허용**(시험·출장 등) + **빈 주차 사유 메모**(`empty_reason`).

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

> ★ **기능 권한 분기는 `role`이 아니라 `position` 기반**이다(수업 개설 = position∈{교수, 조교}).
> `role`은 viewer/admin만 가른다(포털 접근 여부). roster 관리·리포트만 role='admin'에 종속.

### 21-4. 교수/조교 편집 화면
- **수업 개설 모달**: 수업명 + 과목 + 학기. 개설 즉시 **같은 기관의 해당 과목 구독 학생에게 노출**.
- **조교 지정**: 수업별 개별 위임. `position='조교'`인 구성원만 검색 노출("지위가 '조교'인 구성원만 표시됩니다"). 이미 지정된 사람은 비활성.
- **주차 관리**: 추가(제목) / 삭제(휴지통) / 펼침·접힘. 빈 주차 사유 메모.
- **슬라이드 배치**: 주차 "+" → 선택 모달(체크박스 다중, 이름/ID 검색, **중복 허용**), 제거는 X.

### 21-5. 학생 수업 탭
- **내 수업 탭**: 등록 목록 + "등록 해지". 없으면 "전체 수업 탭에서 등록하세요".
- **전체 수업 탭**: 기관 내 공개 수업 전체 + "내 수업 등록". 등록된 수업은 등록됨 뱃지(비활성).
- **수강신청 승인 불필요**(자유 등록). 한 학생이 **여러 수업 등록 가능**(`course_enrollments` 다대다, 과목 구독과 별개 축).

### 21-6. 수업 접근 범위
- 수업 노출 대상 = **그 과목을 구독한 기관의, 그 과목 좌석 viewer**. 과목 구독 모델에 정합 — **기관 전체가 아니라 과목 단위**다.

### 21-7. 즐겨찾기 vs 수강
- **즐겨찾기(★)**: 개인 북마크(뷰어 상단 ★, 마이페이지 목록). **수업과 무관.** (`favorites` 테이블)
- **수강**: 교수가 개설한 수업에 등록 → 커리큘럼(주차)으로 학습. (`course_enrollments`)

### 21-8. 마이페이지
- 프로필(이름·이메일·소속·지위 — **소속/지위는 읽기전용**) · 비밀번호 변경 · 즐겨찾기 목록 · 열람 기록(날짜별).

### 21-9. 스키마·마이그레이션
- 테이블: `courses` / `course_weeks` / `course_week_slides` / `course_assistants` / `course_enrollments` / `favorites` (§7) + `users.position` 컬럼 + `users.role` 기본값 `viewer`.
- 마이그레이션 파일: `db/lms_and_viewer_role_migration.sql` (멱등·트랜잭션, **실행은 CEO가 EC2에서 직접** — §12·§20).

---

*최종 업데이트: 2026-05-31 v3.1 | 변경(Codex 외부 검증 묶음 A·B 반영, pytest 65/65): §6-1 'SA=소유자 표시일 뿐 공용/기본제공 아님'·HST는 첫 런칭 과목일 뿐 기본제공 아님 명문화 / §6-3 온보딩 순서 원칙 신설(구독 선행, 없으면 SUBSCRIPTION_INACTIVE) / §8 슬라이드 접근 단일 게이트(`_slide_access_allowed`, 기관일치 화석 제거)·접근창 집행·특별계정 만료·ADMIN_SECRET_KEY fail-closed·타일토큰 재발급·문의답변/XLSX/XSS 방어 / §12 5대 체크리스트 단일 게이트·온보딩 반영 / §15-10 answered 발송성공 시에만 / §16 KST 접근창·베타 6개월무료→전환 모델 일반화·HST 자동부여 표현 정정 / §18 D3·D10 완료, D9(Codex #7)·D12(2-2#1) 유지, D13 온보딩 체크리스트·D14 Locust(7월말) 신설, v3.1 종결항목 요약 | 직전: v3.0 | 다음: D9·D12(v1.5) / D1·D2·D4b·D13 출시 전 / D14 부하테스트(7월 말)*

*최종 업데이트: 2026-06-03 v3.2 | §20 신설(환경·인프라 점검 — 코드검증 사각지대, docs/INFRA_CHECKLIST.md 포인터). 계기: EC2 이전 완료 + JWT_SECRET_KEY 미설정·어드민 해시 잘림·reboot 후 타일서버 미기동 등 코드검증으로 안 잡히는 사고 경험*

*최종 업데이트: 2026-06-04 v3.3: LMS 섹션 복원·role student→viewer·가입 두 트랙·courses 외 6테이블 추가*

*최종 업데이트: 2026-06-04 v3.4: §6-4 position 단일 출처(subject roster 행) 확정·§7 institution_rosters.position 컬럼 추가(커밋 bf777d3, RDS 적용 완료)·§21-1 행정직원=admin-only(position NULL) 명문화. 2단계 B 선행 블로커 종결.*

*최종 업데이트: 2026-06-04 v3.4: 2단계 B 가입 폼에서 이름칸 제거(옵션 A), 표시 이름은 roster.name 단일 출처. register 두 트랙 재구성(role 입력 제거→roster __ADMIN__/subject 트랙으로 role·position·subject_code 결정), GET /api/institutions 공개 드롭다운, 에러코드 NOT_ON_ROSTER/SEAT_FULL/MULTI_SUBJECT_AMBIGUOUS 정렬(pytest 101).*

*최종 업데이트: 2026-06-04 v3.5: 2단계 B 종결 — register 두 트랙 재구성·구독/좌석 면제 기준을 role→subject_code로 4경로(register·verify·login·_authenticate) 일관화(Codex 발견 1·2·4 + 라운드2, pytest 109). D17(콘텐츠 비소비 관리자 한계·행정직원 회피책) 신설.*

*최종 업데이트: 2026-06-04 v3.6: D18 신설(institutions 고객/소유자/공급사 혼재 → 가입 드롭다운 한정 출시 전 필수, suppliers 분리는 v1.5). §6-1 공급사=license_source 비공개 원칙 명시.*

*최종 업데이트: 2026-06-04 v3.7: e2e 발견 기록 — D2 보강(인증메일 미발송, 출시 블로커), D17 보강(관리자 선가입 시 position NULL 고정 → P1 user 동기화로 해결), D18 재검토(드롭다운 기준을 is_subscribable 플래그 → 구독 존재 여부로 재설계, 컬럼 폐기 예정), D19(발송실패 가입 트랜잭션), D20(테스트 구독 UI). admin 로그인 라우팅·is_subscribable 임시 필터 적용(별도 커밋).*

*최종 업데이트: 2026-06-05 v3.9: 포털 P1 외부검증(Codex 정밀추적+Gemini 구조) 반영. High2·Med3 필수 수정 — ① 타 기관 IDOR 차단(_sync_member·_remove_member의 user 조회·UPDATE에 institution_id 스코프) ② 포털 명단 저장형 XSS 차단(이메일 validator allowlist 강화 + 템플릿 inline onclick 제거→data-* 이벤트 위임) ③ seat_full이면 roster upsert도 skip(분기 A 명세 정합) ④ xlsx 안전 파싱(read_only 스트리밍·zip 압축폭탄 선검사·실측 바이트 상한, ★xlsx 포맷 유지) ⑤ 겸직 is_verified 두 행(subject+__ADMIN__) 갱신(WARN2 유지). §18 D21(접근모델 이원화)·D22(좌석 mutex tie) 신설, D13 과목이동 2단계 명문화. tests/test_portal_p1.py 신규 케이스 포함 전체 pytest 149 passed. **다음: Codex+Gemini 재검증 1라운드 → CEO 승인 → 머지.***

*최종 업데이트: 2026-06-05 v3.8: 기관 포털 P1(명단 관리) 구현 + D18 드롭다운 기준 교체. §9 포털 P1 섹션 신설(GET/POST/DELETE /portal/api/roster + 업로드). D17 ✅ P1 sync 해결(`_sync_member`가 register와 공통 헬퍼로 position·subject_code 동기화, 4분기·role 불변·FOR UPDATE 좌석·제거 회수). D18 ✅ 드롭다운=구독 보유 기관(JOIN subscriptions), is_subscribable 코드 참조 0건(컬럼 정리는 v1.5). auth/auth.py에 `active_window_subscription`/`active_seat_count` 공통 헬퍼 추출(§0 단일진실). tests/test_portal_p1.py 17건 신규, 전체 pytest 127 passed. 내부 보안검증(security-reviewer) FAIL 0건. **다음: Codex 자유탐색+체크리스트 → Gemini → CEO 승인(§12 풀 거버넌스).** P2·P3는 다음 세션.*

> **v3.1 핵심**: 이번 세션에서 Codex 외부 검증이 찾은 출시 블로커(묶음 A·B)를 모두 코드 수정·push했고(pytest 65/65), 문서를 그 코드 상태에 정렬했다. 접근 격리는 **오직 과목 구독(단일 게이트)**, 온보딩은 **구독 선행**, 만료·가입은 **접근창(KST)·fail-closed**가 v3.1의 골격이다.
