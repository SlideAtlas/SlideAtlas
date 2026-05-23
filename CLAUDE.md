# CLAUDE.md — SlideAtlas 프로젝트 메모리 v2.2

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
- **핵심 기능**: WSI 뷰어 터치 최적화 (핀치줌·스와이프 패닝), 태블릿 레이아웃 별도 설계
- **설계 원칙**: v1.0부터 PWA 전환 고려한 구조로 설계

### v2.0 — 글로벌 플랫폼 (2027년 이후)
- **콘텐츠**: Liverpool 열대의학, 아마존·아프리카 기생충학 특수 컬렉션
- **교수 업로드**: 강의노트·PPT 업로드 기능 오픈, 조회수 기반 로열티
- **AI 튜터**: Vector DB (multilingual-e5) + RAG + 다국어 출력
- **구조**: 유튜브식 콘텐츠 마켓플레이스, Fleet Learning 구조

### v2.x — 네이티브 앱 (2027년 Q3~Q4)
- **방향**: React Native 또는 Flutter — 투자 유치 후 팀 구성 시 결정

> **설계 원칙**: v2.0 기능은 v1.0 범위에서 제외. 단, 코드 모듈 경계는 처음부터 v2.0 확장 고려.

---

## 3. 현재 기술 스택

| 구분 | 내용 |
|------|------|
| 백엔드 | Python Flask |
| 뷰어 | OpenSeadragon |
| 배포 | Render Starter ($7/월) → **9월 런칭 전 Standard 전환 필수** (콜드스타트 방지) |
| 저장소 | AWS S3 (ap-northeast-2, 버킷: slideatlas-slides) |
| 타일서버 | AWS EC2 t3.large (slideatlas-tileserver, ec2-13-209-99-51.ap-northeast-2) |
| 타일엔진 | titiler + 커스텀 타일서버 (~/tileserver/main.py, rasterio 기반) |
| 파이프라인 | SVS/DCM/TIFF → COG TIFF → S3 → titiler |
| 데이터 관리 | slides.json + institutions.json → **RDS PostgreSQL 마이그레이션 예정** |
| AI 연동 | Claude API (/api/chat), 구조가이드/질문하기/퀴즈 탭 |
| 버전 관리 | GitHub (SlideAtlas/SlideAtlas) |

---

## 4. 슬라이드 변환 파이프라인 (핵심 인프라)

### 4-1. 고정 변환 스펙 (모든 슬라이드 공통)

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
③ extract_minimap()   → minimap.png 추출 → S3
④ extract_thumbnail() → MPP 기준 20x 해당 오버뷰에서 thumbnail.jpg → S3
⑤ generate_kb_json()  → Claude API 호출로 knowledge_base JSON 자동 생성
⑥ run_qc()           → 기술 QC (타일 응답·흰타일 비율·줌 레벨 정합성)
⑦ update_db()        → status = ready, 전체 메타데이터 DB INSERT
```

**지원 입력 포맷**: SVS, TIFF, DCM, NDPI, VSI

### 4-3. 모듈 구조

```
pipeline/
├── models.py              # ConversionJob, ConversionResult (변경 금지)
├── trigger_adapter.py     # v1.0: HTTP / v1.5: SQS / v2.0: Lambda
├── conversion_engine.py   # 변환 엔진 핵심 로직
└── storage_adapter.py     # S3 이동, RDS 업데이트, 상태 갱신
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

## 5. 슬라이드 메타데이터 및 knowledge_base

### 5-1. 배치 업로드 엑셀 컬럼

```
slide_id | title_ko | title_en | organ | stain | species | subject_code | description
```

### 5-2. knowledge_base JSON — 생성 및 품질 관리

**생성 방식**: 파이프라인 완료 후 Claude API 자동 생성 → 대학원생 검수 → 서비스 노출
**원칙**: AI 생성 JSON을 검수 없이 학생에게 직접 노출하지 않는다.

**강화된 생성 프롬프트**:
```python
prompt = f"""
당신은 한국 의대 조직학 교수입니다.
슬라이드: {title} ({organ}, {stain}, {species})

아래 항목을 JSON으로 작성하세요:
- key_structures: 반드시 찾아야 할 구조 5개
- exam_points: 국가고시/학교 시험 빈출 포인트 3개
- common_confusions: 학생들이 자주 헷갈리는 것 (A vs B 구별법 형태)
- clinical_relevance: 임상적 의미 1~2문장
- zoom_guide: 저배율→고배율 순서로 무엇을 먼저 봐야 하는지

국가고시 기출 수준의 정확도로 작성하세요.
"""
```

**품질 향상 3단계**:
1. 강화된 프롬프트로 AI 생성
2. 의대 대학원생 인턴이 검수·수정 (관리자 페이지 JSON 편집 UI 필요)
3. 실제 학생 질문 패턴을 access_logs에서 분석 → knowledge_base 반영 (v2.0 RAG의 씨앗)

**v2.0 전환 시**: system_prompt에 Vector DB 검색 결과 추가만으로 업그레이드 완료.

---

## 6. 슬라이드 ID 체계

형식: `{기관코드}-{과목코드}-{순번}`

**기관코드**: SA, HS, YU, SNU, KU, MU, AJOU 등 (관리자 페이지에서 추가)
**과목코드**: HST, PATH, PARA, ANAT, EMBRY (관리자 페이지에서 추가)

---

## 7. DB 스키마 (v1.0 기준)

```sql
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
  -- pending | converting | qc_check | ready | ready_no_mpp | failed
  conversion_log TEXT,
  qc_passed_at TIMESTAMP,
  educational_qc_status VARCHAR(20) DEFAULT 'pending',
  -- pending | passed | needs_review | rejected  ← 기술 QC와 별도 관리
  educational_qc_note TEXT,
  is_public BOOLEAN DEFAULT FALSE,
  knowledge_base JSONB,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE access_logs (
  id SERIAL PRIMARY KEY,
  user_id INT REFERENCES users(id),
  slide_id VARCHAR(50) REFERENCES slides(id),
  accessed_at TIMESTAMP DEFAULT NOW(),
  session_id VARCHAR(100)
);
```

> **educational_qc_status 원칙**: 기술 QC(타일 200 OK)와 교육적 QC(교수 눈높이 품질)는 별도 컬럼으로 관리.
> 학생에게 노출되는 슬라이드는 두 QC 모두 통과해야 한다.

---

## 8. 보안 아키텍처

- **Presigned URL**: TTL 5분, 만료 후 타일 접근 불가, S3 버킷 퍼블릭 접근 전면 차단
- **동적 워터마킹**: Pillow, 투명도 15~20%, 대각선 반복 패턴, 사용자 ID·기관명 삽입
- **브라우저 캐시**: `Cache-Control: no-store, no-cache`
- **서버사이드 캐시**: 동일 user_id + tile_key 조합은 메모리/Redis 캐시 TTL 5분 적용
  - 보안 유지하면서 동시접속 성능 확보하는 핵심 구조
- **동시접속 제어**: 새 기기 로그인 시 기존 session_token 무효화
- **멀티테넌시**: institution_id 기반 Row Level 격리

**타일 서빙 구조 (보안 + 성능 균형)**:
```
요청 → 유료 콘텐츠 여부 판단
         ↓                    ↓
   [유료 콘텐츠]         [공개 슬라이드]
   동적 워터마킹          S3 직접 서빙
   서버사이드 캐시         CloudFront 캐시 가능
   (user_id+tile_key)
   TTL 5분
```

---

## 9. 관리자 포털 구조

### 슈퍼관리자 (/admin)
- 기관 추가/수정/삭제, 구독 플랜/만료일 관리
- 슬라이드 업로드: 엑셀 배치 or 개별 → 파이프라인 자동 시작
- 파이프라인 모니터링: conversion_status + educational_qc_status 실시간 표시
- knowledge_base JSON 편집 UI (대학원생 검수용)

### 기관 관리자 (/portal)
- 학생 명단: xlsx/csv 업로드 → DB 등록
- 개별 학생 추가/삭제, 라이선스 현황

---

## 10. AI 튜터 구조 (v1.0)

```python
system_prompt = f"""
당신은 SlideAtlas의 조직학/병리학 AI 튜터입니다.
슬라이드: {slide.title_ko} ({slide.organ}, {slide.stain})
핵심 구조: {knowledge_base['key_structures']}
시험 포인트: {knowledge_base['exam_points']}
혼동 주의: {knowledge_base['common_confusions']}
임상 연관: {knowledge_base['clinical_relevance']}
관찰 순서: {knowledge_base['zoom_guide']}

당신은 보조 튜터입니다. 구조 복습과 질문 답변을 돕습니다.
진단·치료·처방 관련 질문에는 답변하지 마세요.
SlideAtlas 무관 질문에는 답변하지 마세요.
"""
```

**AI 튜터 포지셔닝 원칙**:
- "AI가 가르친다" → "AI가 구조 복습과 질문 답변을 보조한다"
- 초기 메시지에 "보조 학습 도구" 명시, 오답 가능성 안내 문구 UI 포함
- 진단/치료 질문 방어 테스트를 9월 런칭 Go Criteria에 포함

---

## 11. 콘텐츠 현황

| 공급사 | 상태 | 수량 | 비고 |
|--------|------|------|------|
| Happy Science (Linda Li) | 계약 진행 중 | 조직학 133종+ | 최우선 파트너 |
| TCGA 오픈소스 | 사용 중 | 일부 | MVP용 |
| 3DHISTECH 샘플 | 사용 중 | 1종 (소장 H&E) | MVP용 |
| Vic Science (Joy Xu) | 응답 대기 | - | RFP-002 발송 완료 |
| Hongye (Lily Zhao) | 응답 대기 | - | RFP-002 발송 완료 |

**외부 문서에 중국 제조사명 미기재 원칙** (공급망 보호).

**슬라이드 품질 주의 항목** (교육적 QC 특히 엄격히):
- Cochlea, Eye full section, Retina
- Tooth / periodontal ligament, Developing tooth
- Respiratory bronchiole, Peripheral nerve
- Bone ground section, Special stain 계열
- Liver Kupffer / PAS

---

## 12. QA 거버넌스

### 12-1. QA 5대 무조건 체크리스트

**① 보안 & 멀티테넌시**
- YU 계정으로 SNU 슬라이드 URL 조작 접근 차단 확인
- JWT 토큰 변조 공격 방어
- session_token 1기기 동시접속 제어
- Presigned URL TTL 정확히 5분
- 브라우저 캐시 no-store 헤더 확인

**② 파이프라인 안전성**
- COG TIFF 처리 시 파일 전체 메모리 로드 금지 (스트리밍 강제)
- QC 실패·ready_no_mpp 슬라이드 ready 전환 차단 확인
- educational_qc_status 미통과 슬라이드 학생 노출 차단

**③ 성능·부하 (locust 기반 자동화 테스트)**
- 동시 200명 접속 / 같은 슬라이드 집중 시나리오
- 동시 200명 접속 / 10개 슬라이드 분산 시나리오
- 첫 타일 응답 p95 < 2초
- 일반 패닝/줌 p95 < 800ms
- 30분 연속 사용 안정성
- AI 튜터 50명 동시 호출 시 rate-limit graceful handling
- 동적 워터마킹 단독 benchmark (타일 1개당 ms 측정)
- EC2 CPU/RAM 80% 초과 시 경보 확인
- 서버사이드 캐시 hit rate 측정

**④ 비즈니스 로직**
- subscription_end 경과 사용자 접근 차단
- /api/chat 진단·치료 질문 방어벽 작동
- AI 튜터 탈옥 질문 방어

**⑤ DB 마이그레이션 & 라이선스 격리**
- 마이그레이션 스크립트 트랜잭션 처리, 중간 에러 시 전면 Rollback
- is_public=FALSE 슬라이드 비구독 기관 노출 차단

### 12-2. 워크플로우 통제 규칙
- 내부 핑퐁 max 3회: 초과 시 CEO 판단 대기
- 인프라 변경: RDS, EC2, S3 설정 변경은 CEO 명시적 승인 없이 절대 실행 불가

---

## 13. 9월 런칭 Go Criteria

아래 조건을 **모두** 만족해야 9월 유료 런칭 진행:

```
1. 핵심 조직학 슬라이드 최소 80종 이상 ready 상태
2. P1 슬라이드 educational_qc_status passed 비율 90% 이상
3. locust 200명 동시접속 부하테스트 30분 통과
4. 첫 타일 p95 응답시간 2초 이하
5. 기관 관리자 학생 명단 업로드 실사용 테스트 완료
6. AI 튜터 진단/치료 질문 방어 테스트 통과
7. 개인정보처리방침·이용약관·보안 설명서 준비 완료
8. 장애 대응 runbook 준비 완료
9. 비상 복구 권한 (동생 또는 신뢰 인력) 위임 완료
```

---

## 14. 구독 플랜 전략

**런칭 전략 (얼리버드 2단계)**
- 1차: 2026년 9월 — 얼리버드 200만원 ("2026 가을학기 초기 파트너 조건"으로 명확히)
- 2차: 2027년 3월 — 정식가 400만원 전환 (계약서에 2년차 정가 명시 필수)

**가격 커뮤니케이션 원칙**
- 400만원 숫자를 앞에 내세우지 않는다 — 맥락 없는 숫자는 비싸 보임
- 학교 전체(학생+교수+조교) 무제한 사용 맥락에서 제시
- 기존 유리슬라이드 구매 비용 대비 절감액으로 프레이밍 (충남대: 연 1,800만원 → 400만원)
- 1년차부터 월별 사용 리포트 제공 → 갱신 시 "얼마나 썼는지" 근거 제시
- 1년차 말 성과보고서 제공

---

## 15. 런칭 타임라인 (2026년)

| 기간 | 목표 |
|------|------|
| ~7월 말 | 개발 완성 (JWT 인증, 기관 포털, 파이프라인, 동적 워터마킹, 서버사이드 캐시) |
| 7월 말 | locust 부하테스트 스크립트 작성 및 1차 실행 |
| 8월 | 충남대 베타 — 200명 전면 오픈, 무료 1년, 격주 교수 피드백 미팅 |
| 8월 | educational QC 체크리스트 작성, 대학원생 검수 시작 |
| 8월 말 | Go Criteria 전항목 점검, 미달 항목 집중 수정 |
| 9월 | 전면 오픈 — 지방의대·치대·수의대·한의대 집중 영업 |
| 10월 | 대한해부학회 추계학술대회 부스 참가 |

**베타 검증 핵심 항목**
- 동시접속 피크 (실습 수업 시간 전체 동시 접속)
- 슬라이드 첫 로딩 속도
- 기관 관리자 포털 UX (IT 비전문가 기준)
- AI 튜터 실제 학생 질문 패턴 및 오답 수집

---

## 16. 시장 세분화 및 영업 우선순위

**공략 순서**

| 순위 | 타겟 | 규모 | 전략 |
|------|------|------|------|
| 1 | 지방 의대 | ~30개교 | 충남대 레퍼런스, 아버지 납품 네트워크 |
| 1 | 치대·수의대 | ~21개교 | 경쟁자 없는 블루오션 |
| 2 | 한의대 | 12개교 | 동국대 → 도미노 |
| 3 | 약대·보건대·간호대 | 250개교+ | 카탈로그 배포 일괄 공략 |
| 후순위 | 서울 대형 의대 | ~10개교 | 레퍼런스 10개 확보 후 재공략 |

**경쟁사 현황 (Aperio/Leica)**
- 웹뷰어 + 클라우드 SaaS 기술적으로 존재하나 임상·연구소 용도 설계
- 자교 보유 슬라이드만 업로드 가능, AI 튜터 없음, 콘텐츠 큐레이션 없음
- 실제 학생이 교외에서 자유롭게 접속하는 환경 대부분 미구축
- SlideAtlas 차별점: ①큐레이션 콘텐츠 ②어디서든 접속 ③AI 튜터 동시 제공

**학회 부스 전략 (대한해부학회 추계, 매년 10월)**
- 모니터 2대: 1대 WSI 뷰어 풀스크린 / 1대 AI 튜터 체험용
- "직접 써보세요" 체험형 운영 — 설명보다 데모
- 9월 오픈 후 충남대 레퍼런스 + 실사용 피드백 기반으로 문구 확정
- 가격 수치 노출 자제 — 맥락 없는 숫자는 역효과

**영업 패키지 (9월 전 준비)**
- 교수용 1장 제안서
- 행정팀용 견적서 템플릿
- 보안·개인정보 설명서 PDF
- 교육용 SaaS 계약서
- 무료 파일럿 → 유료 전환 조건 명시

---

## 17. 리스크 평가 (v2.2 기준)

### 치명적 리스크 평가

단일 치명 리스크는 현재 낮음.
다만 아래 4가지가 동시에 발생할 경우 2026년 9월 런칭에 치명적 영향을 줄 수 있음.

**2026년 8~9월 런칭 구간 핵심 복합 리스크**:
1. 콘텐츠 라이선스 및 슬라이드 공급 품질
2. 첫 수업 장애 및 성능 문제
3. 교수 관심의 실제 유료 계약 전환 실패
4. 1인 운영 과부하

### Top 리스크 매트릭스

| 순위 | 리스크 | 가능성 | 영향 | 우선 액션 |
|------|--------|--------|------|-----------|
| 1 | 콘텐츠 라이선스/권리 | 중 | 매우 높음 | 계약서 Exhibit A 상세화 |
| 2 | 슬라이드 교육적 품질 | 높음 | 높음 | educational_qc_status + 대학원생 검수 |
| 3 | 첫 수업 장애 | 중~높음 | 매우 높음 | locust 부하테스트, 비상 fallback |
| 4 | 영업→계약 전환 지연 | 높음 | 높음 | 행정팀용 문서 패키지 |
| 5 | AI 튜터 오답/신뢰 | 높음 | 중~높음 | 검수 루프, "보조 도구" 포지셔닝 |
| 6 | 1인 운영 과부하 | 높음 | 높음 | runbook, 비상권한 위임 |
| 7 | 보안/개인정보 | 중 | 높음 | 보안 문서 선준비 |
| 8 | 인프라 비용/성능 | 중 | 높음 | 워터마킹 benchmark, 서버사이드 캐시 |
| 9 | 유료전환/갱신 | 중 | 높음 | 사용률 리포트 자동화 |
| 10 | 경쟁/대체재(관성) | 높음 | 중 | "콘텐츠+AI+운영" 포지셔닝 |

### 치명적 복합 시나리오

**시나리오 A**: 슬라이드 품질 불량 + 타일 로딩 지연 → 8월 베타에서 "수업에 못 쓰겠다" 판단 → 9월 레퍼런스 약화

**시나리오 B**: 교수 반응 좋음 → 행정팀 보안/계약 검토 지연 → 학기 시작 지나감 → "내년 예산으로"

**시나리오 C**: AI 튜터 오답을 교수님이 발견 → "학생에게 위험하다" 인식 → WSI 뷰어까지 평가절하

**시나리오 D**: 중국 계약+스캔+개발+베타+영업 동시 진행 → 작은 장애 대응 지연 → 영업 기회 놓침

---

## 18. 운영 인력 계획

- **8월 베타까지**: 보람님 1인 + 자동화 모듈
- **9월 런칭 시**: 의대·치대 대학원생 파트타임 인턴 1명 (월 80~150만원)
  - 역할: CS 응대, 슬라이드 educational QC 검수, knowledge_base JSON 수정
  - 채용 루트: 충남대 베타 적극 참여자 → 9월 파트타임 제안
- **정규직 채용**: 구독 5개교 이상 + 초창패 수령 후
- **인건비 트리거**: "구독 5개교 달성 또는 초창패 수령 시 파트타임 채용" 조건 사전 설정

### 최소 운영 백업 (8월 베타 전 완료)
- AWS/Render/S3 emergency access → 동생 또는 신뢰 인력 위임
- 서버 재시작 runbook (Notion 저장)
- 장애 공지 템플릿
- 기관 관리자 계정 생성 매뉴얼
- 학생 일괄 등록 매뉴얼
- 중국 공급사별 계약/인보이스 폴더 정리

### 자동화 가능 영역 (Claude Code/Cowork)
- 견적서·세금계산서 초안 자동 생성
- 서버 장애 알림 (5분 주기 → 카카오톡/문자)
- CS 이메일 자동 분류·응대 초안 (Gmail MCP)
- 구독 만료 리마인드 자동 발송 (60·30·7일 전)
- 월별 사용률 리포트 자동 생성

---

## 19. 개발 원칙 & 주의사항

- **AWS 자격증명**: nohup 컨텍스트에서 인라인 `$(aws configure get ...)` 치환 실패 → 환경변수 먼저 export 후 실행
- **Windows SCP**: PEM 권한 설정은 비관리자 PowerShell에서 icacls 처리
- **한국어 PDF**: reportlab/weasyprint 한글 폰트 임베딩 한계 → Adobe Illustrator 직접 작업
- **중국어 문서**: Node.js docx 패키지, SimSun TextRun 별도 분리 필요
- **COG 변환 배치**: SVS 1장당 5~15분, 133장 = 최대 30시간 → EC2 밤새 배치 실행
- **매출 우선 원칙**: 정부지원보다 9월 매출 데이터 확보 최우선
- **모듈 경계 원칙**: `ConversionJob` / `ConversionResult` 데이터 계약 변경 금지
- **Render 콜드스타트**: Starter 슬립 모드 → 9월 전 Standard 전환 필수
- **동적 워터마킹 성능**: Pillow 처리 타일당 ms 반드시 benchmark — 200명 동시접속 시 병목 가능
- **educational QC 원칙**: 기술 QC 통과 ≠ 서비스 가능. educational_qc_status passed 필수

---

## 20. 주요 외부 연락처

- Happy Science: Linda Li / info@ihappysci.com / WhatsApp +86 188 3816 1683
- Vic Science: Joy Xu / joy@vicscience.com
- Hongye: Lily Zhao / Lianhonglianli@163.com
- 성원애드피아: 명함 인쇄 (아르미 울트라화이트 310g 양면)
- 대한해부학회 추계학술대회: 매년 10월, 부스 신청 6~7월 예상 (사무국 확인 필요)

---

*최종 업데이트: 2026-05-23 v2.2*
*주요 변경: 치명적 리스크 평가 수정, educational_qc_status 추가, knowledge_base 품질 관리 강화, locust 부하테스트 QA 편입, 9월 Go Criteria 확정, 타일 서버사이드 캐시 구조 추가*
