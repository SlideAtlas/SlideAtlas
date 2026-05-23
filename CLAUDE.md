# CLAUDE.md — SlideAtlas 프로젝트 메모리 v2.1

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
- **개발 전제**: 투자 유치 후 전문 모바일 개발팀 구성

> **설계 원칙**: v2.0 기능(VectorDB, 교수 업로드, 다국어, 로열티 정산)은 v1.0 범위에서 제외.
> 단, 코드 모듈 경계는 처음부터 v2.0 확장을 고려해 설계한다.

---

## 3. 현재 기술 스택

| 구분 | 내용 |
|------|------|
| 백엔드 | Python Flask |
| 뷰어 | OpenSeadragon |
| 배포 | Render Starter ($7/월) → 런칭 전 Standard 전환 필요 |
| 저장소 | AWS S3 (ap-northeast-2, 버킷: slideatlas-slides) |
| 타일서버 | AWS EC2 t3.large (slideatlas-tileserver, ec2-13-209-99-51.ap-northeast-2) — 동적 워터마킹 처리 포함 (~$60/월) |
| 타일엔진 | titiler + 커스텀 타일서버 (~/tileserver/main.py, rasterio 기반) |
| 파이프라인 | SVS/DCM/TIFF → COG TIFF → S3 → titiler |
| 데이터 관리 | slides.json + institutions.json → **RDS PostgreSQL 마이그레이션 예정** |
| AI 연동 | Claude API (/api/chat), 구조가이드/질문하기/퀴즈 탭 |
| 버전 관리 | GitHub (SlideAtlas/SlideAtlas) |

---

## 4. 슬라이드 변환 파이프라인 (핵심 인프라)

### 4-1. 설계 원칙

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

### 4-3. 모듈 구조 (SQS/Lambda 이식성 보장)

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
    slide_id: str
    s3_input_key: str
    institution_id: str
    original_format: str

@dataclass
class ConversionResult:
    slide_id: str
    status: str             # 'ready' | 'failed'
    s3_cog_key: str
    mpp: float
    width: int
    height: int
    qc_passed: bool
    error_log: str | None
```

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
                    ↘            ↘
                     failed       ready_no_mpp
```

---

## 5. 슬라이드 메타데이터 입력 방식

### 5-1. 배치 업로드 (100장 이상)
엑셀 파일(.xlsx)과 슬라이드 파일을 함께 업로드. 엑셀 컬럼:
```
slide_id | title_ko | title_en | organ | stain | species | subject_code | description
```

### 5-2. 개별 추가 (1~2장)
관리자 페이지에서 파일 업로드 후 메타데이터 직접 입력 폼 제공.

### 5-3. knowledge_base JSON 자동 생성
```json
{
  "key_structures": ["villus", "Lieberkuhn crypt", "goblet cell"],
  "exam_points": ["villus height ratio", "cell distribution pattern"],
  "common_confusions": ["jejunum vs ileum — Peyer's patches 유무로 구분"]
}
```

---

## 6. 슬라이드 ID 체계

형식: `{기관코드}-{과목코드}-{순번}`

**기관코드**: SA, HS, YU, SNU, KU, MU, AJOU 등 (관리자 페이지에서 추가)
**과목코드**: HST, PATH, PARA, ANAT, EMBRY (관리자 페이지에서 추가)

---

## 7. DB 스키마 (v1.0 기준)

```sql
CREATE TABLE subject_codes (
  code VARCHAR(10) PRIMARY KEY,
  name_ko VARCHAR(50),
  name_en VARCHAR(50),
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
  s3_minimap_key VARCHAR(500),
  s3_thumbnail_key VARCHAR(500),
  mpp FLOAT,
  width INT,
  height INT,
  stain VARCHAR(50),
  organ VARCHAR(100),
  species VARCHAR(50) DEFAULT 'human',
  license_source VARCHAR(100),
  original_format VARCHAR(20),
  conversion_status VARCHAR(20) DEFAULT 'pending',
  conversion_log TEXT,
  qc_passed_at TIMESTAMP,
  is_public BOOLEAN DEFAULT FALSE,
  knowledge_base JSONB,
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
```

---

## 8. 보안 아키텍처

- **Presigned URL**: TTL 5분, 만료 후 타일 접근 불가, S3 버킷 퍼블릭 접근 전면 차단
- **동적 워터마킹**: v1.0 런칭 시 포함. 사용자 ID·기관명을 타일마다 투명하게 삽입 (Pillow, 투명도 15~20%, 대각선 반복 패턴)
- **브라우저 캐시 완전 차단**: `Cache-Control: no-store, no-cache`
- **동시접속 제어**: 새 기기 로그인 시 기존 session_token 무효화
- **도메인 기반 자가인증**: 기관 이메일 도메인 검증 + 6개월 재인증
- **멀티테넌시**: institution_id 기반 Row Level 격리

---

## 9. 관리자 포털 구조

### 슈퍼관리자 (/admin)
- 기관 추가/수정/삭제, 계약 상태/구독 플랜/만료일 관리
- 슬라이드 관리: 파일 업로드(엑셀 배치 or 개별) → 파이프라인 자동 시작
- 파이프라인 모니터링: conversion_status 실시간 표시

### 기관 관리자 (/portal)
- 학생 명단: xlsx/csv 업로드 → DB 등록
- 개별 학생 추가/삭제, 라이선스 현황 표시

---

## 10. AI 튜터 구조 (v1.0)

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

**v2.0에서 RAG로 전환 시**: system_prompt에 Vector DB 검색 결과를 추가하는 것만으로 업그레이드 완료.

---

## 11. 콘텐츠 현황

| 공급사 | 상태 | 수량 | 비고 |
|--------|------|------|------|
| Happy Science (Linda Li) | 계약 진행 중 | 조직학 133종+ | 최우선 파트너 |
| TCGA 오픈소스 | 사용 중 | 일부 | MVP용 |
| 3DHISTECH 샘플 | 사용 중 | 1종 (소장 H&E) | MVP용 |
| Vic Science (Joy Xu) | 응답 대기 | - | RFP-002 발송 완료 |
| Hongye (Lily Zhao) | 응답 대기 | - | RFP-002 발송 완료 |

**주의**: 외부 문서에 중국 제조사명 미기재 원칙 (공급망 보호).

---

## 12. QA 거버넌스 — 3단계 검증 구조

### QA 5대 무조건 체크리스트 (하나라도 미통과 시 Reject)

**① 보안 & 멀티테넌시**
- YU 계정으로 SNU 슬라이드 URL 조작 접근 차단 확인
- JWT 토큰 변조 공격 방어
- session_token 1기기 동시접속 제어
- Presigned URL TTL 정확히 5분
- 브라우저 캐시 no-store 헤더 적용 확인

**② 파이프라인 안전성**
- COG TIFF 처리 시 파일 전체 메모리 로드 금지 (스트리밍 강제)
- QC 실패·ready_no_mpp 슬라이드가 ready 상태로 전환되지 않는지 확인

**③ 비즈니스 로직**
- subscription_end 경과 사용자 접근 차단
- /api/chat 탈옥 질문 시 방어벽 작동

**④ DB 마이그레이션 안전성**
- 마이그레이션 스크립트 트랜잭션 처리, 중간 에러 시 전면 Rollback

**⑤ 라이선스 격리**
- is_public=FALSE 슬라이드 비구독 기관 노출 차단

### 워크플로우 통제 규칙
- 내부 핑퐁 max 3회: Dev ↔ QA 한 이슈당 최대 3회. 초과 시 CEO 판단 대기
- 인프라 변경 금지: RDS, EC2, S3 설정 변경은 CEO 명시적 승인 없이 절대 실행 불가

---

## 13. 구독 플랜 전략

**런칭 전략 (얼리버드 2단계)**
- 1차: 2026년 9월 가을학기 — 얼리버드 200만원 (1년 한정)
- 2차: 2027년 3월 봄학기 — 정식가 400만원 전환
- 얼리버드 계약서에 "2년차부터 정가 적용" 명시 필수

**가격 커뮤니케이션 원칙**
- 400만원 숫자를 앞에 내세우지 않는다
- 학교 전체(학생+교수+조교) 무제한 사용 맥락에서 제시
- 기존 유리슬라이드 구매 비용 대비 절감액으로 프레이밍 (충남대 사례: 연 1,800만원 → 400만원)

---

## 14. 런칭 타임라인 (2026년)

| 기간 | 목표 |
|------|------|
| ~7월 말 | 개발 완성 (JWT 인증, 기관 포털, 파이프라인, 동적 워터마킹) |
| 8월 | 충남대 베타 — 200명 전면 오픈, 무료 1년 제공, 버그 수집 |
| 8월 베타 검증 항목 | 동시접속 피크, 슬라이드 첫 로딩 속도, 기관 관리자 포털 UX, AI 튜터 오답 패턴 |
| 9월 | 전면 오픈 — 지방의대·치대·수의대·한의대 집중 영업 |
| 10월 | 대한해부학회 추계학술대회 부스 참가 (매년 10월, 2026년 일정 확인 필요) |

**베타 운영 원칙**
- 충남대 담당 교수님과 격주 피드백 미팅 운영
- 버그 수집보다 "불편했던 순간" 직접 청취 우선
- 9월 런칭 1주 전 부하테스트 필수

---

## 15. 시장 세분화 및 영업 우선순위

**공략 순서**

| 순위 | 타겟 | 학교 수 | 이유 |
|------|------|---------|------|
| 1 | 지방 의대 | ~30개교 | 아버지 납품 이력, 충남대 레퍼런스 활용 |
| 1 | 치대·수의대 | ~21개교 | 경쟁자 없는 블루오션, 납품 이력 있음 |
| 2 | 한의대 | 12개교 | 진입 쉬움, 동국대 레퍼런스 → 도미노 가능 |
| 3 | 약대·보건대·간호대 | 250개교+ | 볼륨 타겟, 카탈로그 배포로 일괄 공략 |
| 후순위 | 서울 대형 의대 | ~10개교 | Aperio/Leica 기도입, 레퍼런스 확보 후 재공략 |

**경쟁사 현황 (Aperio/Leica)**
- 기술적으로 웹뷰어 + 클라우드 SaaS 존재하나, 임상 병리과·연구소용 설계
- 교육용 도입 시 학교 자체 서버 구축 또는 별도 클라우드 계약 필요
- 자교 보유 슬라이드만 업로드 가능, AI 튜터 없음, 콘텐츠 큐레이션 없음
- 실제 학생들이 교내 외부에서 자유롭게 접속하는 환경은 대부분 미구축
- SlideAtlas 차별점: ①큐레이션 콘텐츠 ②어디서든 접속 ③AI 튜터 3가지 동시 제공

**학회 부스 전략**
- 대형 모니터 2대: 1대는 WSI 뷰어 풀스크린, 1대는 AI 튜터 탭 (교수님이 직접 질문 입력)
- "직접 써보세요" 체험형 운영 — 설명보다 데모
- 부스 문구: 9월 오픈 후 충남대 레퍼런스 + 실제 피드백 기반으로 확정
- 가격 노출 자제 — 맥락 없는 숫자는 역효과

---

## 16. 운영 리스크 및 대응

### 치명적 리스크 평가
- **치명적 리스크 없음** — 수요 검증 완료(보람바이오텍 20년 납품), 기술 작동 확인, 충남대 반응 확보
- 가장 위험한 시나리오: Happy Science 계약 완전 결렬 + 대체 공급사 모두 실패 → TCGA + Yulin 물리구매+스캐닝으로 대응 가능, 치명적 수준 아님

### 운영 단계 주요 리스크

**즉시 대응 필요**
- 첫 수업 당일 장애: 런칭 1주 전 부하테스트 필수, EC2 t3.medium 업그레이드, Render Standard 전환
- 로그인 불가 (개강 첫날): 기관 관리자 온보딩 개강 2주 전 완료 기준 설정

**런칭 전 준비**
- AI 튜터 오답: 자문 교수 1인 knowledge_base 검수, 면책 문구 UI 명시
- Happy Science 계약 범위 분쟁: 계약서에 허용 국가·기관 수·모듈별 단가 명확히 기재
- 인프라 런웨이 문서화: EC2·S3·Render 복구 절차 Notion 저장, 동생 비상 접근 권한 설정

**운영 중 관리**
- 구독 갱신 이탈: 계약서에 담당자 2인 이상 명기, 만료 60·30·7일 전 자동 리마인드
- 사용률 저조: 온보딩 시 커리큘럼 연동 가이드 제공, 월별 사용률 리포트 기관 관리자 발송

### 자동화 가능 영역 (Claude Code/Cowork 활용)
- 견적서·세금계산서 초안 자동 생성 (기관명+금액 입력 → PDF)
- 서버 장애 알림 (EC2/Render 5분 주기 체크 → 카카오톡/문자)
- CS 이메일 자동 분류·응대 초안 (Gmail MCP 연동)
- 구독 만료 리마인드 자동 발송
- 월별 사용률 리포트 자동 생성

**자동화 불가 영역 (사람 필요)**
- 기관 관리자 전화 응대
- 계약서 협상·서명
- AI 튜터 오답 검수 (의학 도메인 지식 필요)
- 장애 복구 판단·실행

### 운영 인력 계획
- 8월 베타까지: 보람님 1인 운영 (자동화 모듈로 보조)
- 9월 런칭 시: 의대·치대 대학원생 파트타임 인턴 1명 (월 80~150만원, 도메인 지식 보유)
- 채용 루트: 충남대 베타 참여자 중 적극적인 대학원생 → 9월 파트타임 제안
- 정규직 채용: 구독 5개교 이상 + 초창패 수령 후 고려
- 인건비 트리거: "매출 N개교 달성 또는 초창패 수령 시 파트타임 채용"으로 조건 미리 설정

---

## 17. 개발 원칙 & 주의사항

- **AWS 자격증명**: nohup 컨텍스트에서 인라인 `$(aws configure get ...)` 치환 실패 → 환경변수 먼저 export 후 실행
- **Windows SCP**: PEM 권한 설정은 비관리자 PowerShell에서 icacls 처리
- **한국어 PDF**: reportlab/weasyprint 한글 폰트 임베딩 한계 → Adobe Illustrator 직접 작업
- **중국어 문서**: Node.js docx 패키지, SimSun TextRun 별도 분리 필요
- **COG 변환 배치**: SVS 1장당 5~15분, 133장 = 최대 30시간 → EC2에서 밤새 배치 실행
- **매출 우선 원칙**: 정부지원(초창패 등)보다 9월 매출 데이터 확보가 최우선
- **모듈 경계 원칙**: `ConversionJob` / `ConversionResult` 데이터 계약은 어떤 이유로도 변경 금지
- **Render 콜드스타트**: Starter 플랜 슬립 모드 → 9월 런칭 전 Standard 플랜 전환 필수

---

## 18. 주요 외부 연락처

- Happy Science: Linda Li / info@ihappysci.com / WhatsApp +86 188 3816 1683
- Vic Science: Joy Xu / joy@vicscience.com
- Hongye: Lily Zhao / Lianhonglianli@163.com
- 성원애드피아: 명함 인쇄 (아르미 울트라화이트 310g 양면)
- 대한해부학회 추계학술대회: 매년 10월 개최, 부스 신청 6~7월 예상 (2026년 일정 사무국 확인 필요)

---

*최종 업데이트: 2026-05-23 v2.1 | 주요 변경: 런칭 타임라인 확정, 베타 전략, 시장 세분화, 운영 리스크, 자동화 계획, 학회 부스 전략 추가*
