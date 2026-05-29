# CLAUDE.md — SlideAtlas 프로젝트 메모리 v2.6

> 이 파일은 Claude Code 세션 시작 시 반드시 읽어야 하는 프로젝트 컨텍스트 파일입니다.
> 모든 에이전트(오케스트레이터, 개발, QA)는 이 파일을 기준으로 작업합니다.

---

## 1. 프로젝트 개요

**제품명**: SlideAtlas
**운영사**: 아틀라스랩 주식회사 (Atlas Lab Co., Ltd.)
**대표**: 김보람 (Boram Kim)
**URL**: slide-atlas.net (공식 도메인, 2025.05 확정)
**도메인**: atlaslab.co.kr (가비아)
**이메일**: boram@atlaslab.co.kr

**한 줄 정의**: 의과대학·치과대학·수의대·한의대·약대·간호대·보건전문대·전문대 내 관련학과들(임상병리학과 등)을 대상으로 한 디지털 병리/조직학 WSI(Whole Slide Image) 구독 SaaS 플랫폼.

**핵심 비즈니스 모델**: 오프라인 슬라이드 납품(보람바이오텍, 20년 의대 납품 이력) 네트워크를 디지털 구독 SaaS로 전환. 장비 불필요(WinMedic 등 경쟁사 대비 차별점).

**핵심 포지셔닝**: "땡시(조직학 실습시험) 대비, 집에서 한국어로" — 교수가 주차별로 배치한 슬라이드를 학생이 집에서 WSI로 복습하며 실습시험 준비.

**경쟁 구도**: Histology Guide(무료 조직학 WSI), WinMedic(스캐너+플랫폼 수직통합, 장비 수천만원) vs SlideAtlas(콘텐츠 구독 SaaS, 장비 불필요) = 장비판매 vs Netflix

---

## 2. 버전별 개발 로드맵

### v1.0 — 한국 런칭 (2026년 9월 목표)
- **타겟**: 국내 지방의대·수의대·약대·한의대·보건대
- **콘텐츠**: 아틀라스랩이 직접 라이선스 계약한 컬렉션만 제공 (교수 업로드 없음)
- **AI 튜터**: 슬라이드 메타데이터 + `knowledge_base` JSON → Claude API (VectorDB 없음)
- **구독 플랜**: TO 기반 4종 플랜 (Department/Standard/Campus/Institution)
- **모바일**: 반응형 웹 (OpenSeadragon 터치 기본 지원 + CSS 미디어쿼리)
- **마일스톤**: 9월 가을학기 2~3개교 구독 확보 → 초창패 추경 신청

### v1.5 — 콘텐츠 확장·국내 안착 (2026년 말)
- **콘텐츠**: 병리·기생충 모듈, Mahidol 열대의학 컬렉션 라이선스
- **AI 튜터**: 자문 교수 1인 영입 → knowledge_base JSON 검수·보완
- **영업**: 국내 10~15개교 확보, 매출 레퍼런스 구축

### v1.5M — 모바일 PWA 출시 (2027년 1분기)
- **방향**: PWA(Progressive Web App) — 브라우저에서 설치, 앱스토어 불필요
- **핵심 기능**: WSI 뷰어 터치 최적화 (핀치줌·스와이프 패닝), 태블릿 레이아웃 별도 설계
- **설계 원칙**: v1.0부터 PWA 전환 고려한 구조로 설계

### v2.0 — 글로벌 플랫폼 (2027년 이후)
- **콘텐츠**: Liverpool 열대의학, 아마존·아프리카 기생충학 특수 컬렉션
- **교수 업로드**: 강의노트·PPT 업로드 기능 오픈, 조회수 기반 로열티
- **AI 튜터**: Vector DB (multilingual-e5) + RAG + 다국어 출력
- **플랜 고도화**: 콘텐츠 모듈(기생충학·특수 컬렉션) 추가 시 플랜 구조 재검토

### v2.x — 네이티브 앱 (2027년 Q3~Q4)
- **방향**: React Native 또는 Flutter — 투자 유치 후 팀 구성 시 결정

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
| 파이프라인 | TIFF/SVS/DCM → COG TIFF → S3 → titiler |
| 데이터 관리 | slides.json + institutions.json → **RDS PostgreSQL 마이그레이션 예정** |
| AI 연동 | Claude API (/api/chat), 구조가이드/질문하기/퀴즈 탭 |
| 버전 관리 | GitHub (SlideAtlas/SlideAtlas) |

---

## 4. 슬라이드 수급 및 변환 파이프라인

### 4-1. 슬라이드 수급 표준 워크플로우 (확정)

```
물리 슬라이드 구매 (Yulin 등 공급사)
  → 뷰웍스(Viewworks) 스캔 → TIFF 파일 수령
  → EC2에서 COG TIFF 변환 (밤새 배치, 1장당 5~15분)
  → AWS S3 업로드
  → 어드민에서 엑셀로 메타데이터 일괄 등록 (B+C 방식)
  → 파이프라인 일괄 시작 (generate_kb_json + QC 자동 실행)
  → 어드민 파이프라인 모니터에서 진행 확인
  → educational QC 통과 후 서비스 노출
```

**웹 UI 업로드**: 1~2장 긴급 개별 추가용 보조 기능으로만 유지. 대량 업로드에는 사용하지 않는다.

### 4-2. 고정 변환 스펙 (모든 슬라이드 공통)

```
타일: 256×256 px
압축: JPEG Q=85
오버뷰: 7레벨 고정 (2, 4, 8, 16, 32, 64, 128)
MPP: 원본에서 추출, 없으면 0.5 기본값, DB에 저장
좌표계: 픽셀 기준, 북서쪽 원점
BigTIFF: 파일 크기 4GB 초과 시 자동 적용
```

### 4-3. 파이프라인 실행 순서

```
① extract_meta()      → MPP, 해상도, 포맷, 스캐너 정보 추출·검증
② convert_cog()       → COG TIFF 변환 (표준 스펙 고정)
③ extract_minimap()   → minimap.png 추출 → S3
④ extract_thumbnail() → MPP 기준 20x 해당 오버뷰에서 thumbnail.jpg → S3
⑤ generate_kb_json()  → Claude API 호출로 knowledge_base JSON 자동 생성
⑥ run_qc()           → 기술 QC (타일 응답·흰타일 비율·줌 레벨 정합성)
⑦ update_db()        → status = ready, 전체 메타데이터 DB INSERT
```

**지원 입력 포맷**: TIFF (뷰웍스 스캔 표준), SVS, DCM, NDPI, VSI

### 4-4. 모듈 구조

```
pipeline/
├── models.py              # ConversionJob, ConversionResult (변경 금지)
├── trigger_adapter.py     # v1.0: HTTP / v1.5: SQS / v2.0: Lambda
├── conversion_engine.py   # 변환 엔진 핵심 로직
└── storage_adapter.py     # S3 이동, RDS 업데이트, 상태 갱신
```

### 4-5. QC 자동 검증 항목

| 항목 | 기준 | 실패 시 |
|------|------|---------|
| 타일 HTTP 응답 | 저·중·고배율 3레벨 모두 200 | status = failed |
| 흰 타일 비율 | 샘플 타일 흰색 픽셀 < 95% | status = failed |
| DZI 레벨 수 | 원본 해상도 기반 예상값과 일치 | status = failed |
| MPP 범위 | 0.1 ~ 1.0 μm/px | 경고 로그, 계속 진행 |
| 최소 해상도 | 5,000 px 이상 | status = failed |

### 4-6. 상태 머신

```
pending → converting → qc_check → ready
                    ↘            ↘
                     failed       ready_no_mpp
```

---

## 5. 슬라이드 메타데이터 및 knowledge_base

### 5-1. 배치 업로드 엑셀 컬럼 (B+C 방식)

```
slide_id | title_ko | title_en | organ | stain | species | subject_code | description | s3_key
```

- S3에 파일 먼저 업로드 후 s3_key 기입
- 엑셀 업로드 → DB 일괄 INSERT → 파이프라인 자동 시작

### 5-2. knowledge_base JSON — 생성 및 품질 관리

**생성 방식**: 파이프라인 완료 후 Claude API 자동 생성 → 대학원생 검수 → 서비스 노출
**원칙**: AI 생성 JSON을 검수 없이 학생에게 직접 노출하지 않는다.

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
"""
```

---

## 6. Educational QC 운영 전략

### 6-1. QC 2단계 구조

**기술 QC** (파이프라인 자동화) — 섹션 4-5 참조.
**Educational QC** (대학원생 수작업) — 기술 QC 통과 슬라이드에 한해 실시.
- educational_qc_status: `pending` → `passed` / `needs_review` / `rejected`
- 학생에게 노출되는 슬라이드는 두 QC 모두 통과해야 한다.

### 6-2. 대학원생 작업 범위 및 조건

- 슬라이드 뷰어에서 각 슬라이드 열람 후 품질 판정
- AI 생성 knowledge_base JSON 검수 및 오류 수정
- 결과물: 엑셀 (slide_id별 QC 판정 + JSON 수정 내용)
- 기간: 1개월 / 인건비: 150만원

---

## 7. 슬라이드 ID 체계

형식: `{기관코드}-{과목코드}-{순번}`

**기관코드**: SA, HS, YU, SNU, KU, MU, AJOU 등 (관리자 페이지에서 추가)
**과목코드**: HST, PATH, PARA, ANAT, EMBRY (관리자 페이지에서 추가)

---

## 8. DB 스키마 (v1.0 기준)

```sql
CREATE TABLE institutions (
  id VARCHAR(20) PRIMARY KEY,
  name_ko VARCHAR(100),
  name_en VARCHAR(100),
  domain VARCHAR(100),
  subscription_plan VARCHAR(20),   -- 'department'|'standard'|'campus'|'institution'
  subscription_start DATE,
  subscription_end DATE,
  base_to INT,                     -- 플랜 기본 TO
  extra_blocks INT DEFAULT 0,      -- 추가 블록 수 (블록당 50명)
  max_users INT,                   -- base_to + extra_blocks*50
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  institution_id VARCHAR(20) REFERENCES institutions(id),
  email VARCHAR(200) UNIQUE NOT NULL,
  password_hash VARCHAR(255),
  role VARCHAR(20) DEFAULT 'student',
  -- 'student' | 'assistant' | 'professor' | 'institution_admin' | 'super_admin' | 'special'
  last_login TIMESTAMP,
  session_token VARCHAR(255),
  is_special BOOLEAN DEFAULT FALSE,  -- 특별 계정 (TO 미포함, 무상 무한 접근)
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
  educational_qc_status VARCHAR(20) DEFAULT 'pending',
  educational_qc_note TEXT,
  is_public BOOLEAN DEFAULT FALSE,
  knowledge_base JSONB,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE plan_slides (
  plan VARCHAR(20),                -- 'department'|'standard'|'campus'|'institution'
  slide_id VARCHAR(50) REFERENCES slides(id),
  display_order INT DEFAULT 0,
  PRIMARY KEY (plan, slide_id)
);

-- 현재: 모든 플랜 동일 슬라이드. 추후 콘텐츠 모듈 추가 시 plan별 분리 예정.

CREATE TABLE access_logs (
  id SERIAL PRIMARY KEY,
  user_id INT REFERENCES users(id),
  slide_id VARCHAR(50) REFERENCES slides(id),
  accessed_at TIMESTAMP DEFAULT NOW(),
  session_id VARCHAR(100)
);

CREATE TABLE ai_chat_logs (
  id SERIAL PRIMARY KEY,
  user_id INT REFERENCES users(id),
  slide_id VARCHAR(50) REFERENCES slides(id),
  tab VARCHAR(20),                 -- 'guide'|'chat'|'quiz'
  created_at TIMESTAMP DEFAULT NOW()
);

-- 교수 수업 페이지
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
```

---

## 9. 보안 아키텍처

- **Presigned URL**: TTL 5분, S3 버킷 퍼블릭 접근 전면 차단
- **동적 워터마킹**: Pillow, 투명도 15~20%, 대각선 반복 패턴, 사용자 ID·기관명 삽입
- **브라우저 캐시**: `Cache-Control: no-store, no-cache`
- **서버사이드 캐시**: 동일 user_id + tile_key 조합, TTL 5분
- **동시접속 제어**: 새 기기 로그인 시 기존 session_token 무효화 (특별 계정 포함)
- **멀티테넌시**: institution_id 기반 Row Level 격리

---

## 10. 구독 플랜 구조 (v1.0)

### 10-1. 플랜 4종 (TO 기반)

| 플랜 | 타겟 | 기본 TO | 추가 블록 | 상위 플랜 기준 |
|------|------|---------|-----------|--------------|
| Department | 소규모 과 단위 (한의대 단일과 등) | 50명 | +50명/블록 (최대 1블록) | 100명 초과 → Standard |
| Standard | 약대·보건전문대 | 150명 | +50명/블록 (최대 1블록) | 200명 초과 → Campus |
| Campus | 의과대학·수의대·치대 | 300명 | +50명/블록 (최대 1블록) | 350명 초과 → Institution |
| Institution | 대형 기관·복수 캠퍼스 | 500명+ | 별도 협의 | — |

### 10-2. 플랜 원칙

- **콘텐츠 동일**: v1.0에서는 모든 플랜이 동일한 슬라이드에 접근 (TO만 다름)
- **추가 블록**: 50명 단위, 블록당 추가금 (금액 미확정)
- **가격**: 미확정 — 실제 판매하면서 확정
- **얼리버드**: 플랜별 적용 여부 미확정
- **콘텐츠 모듈 추가 시**: 기생충학·특수 컬렉션 등 추가되면 플랜 구조 고도화 검토

### 10-3. 런칭 전략 (참고)
- 1차: 2026년 9월 — 얼리버드 조건 (금액 미확정, "2026 가을학기 초기 파트너 조건"으로 명확히)
- 2차: 2027년 3월 — 정식가 전환 (계약서에 2년차 정가 명시 필수)

---

## 11. AI 튜터 구조 (v1.0)

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

---

## 12. 콘텐츠 현황

| 공급사 | 상태 | 수량 | 비고 |
|--------|------|------|------|
| Happy Science (Mallen Zhang / Linda Li) | 계약 진행 중 | 조직학 143종 전체 커버 가능 | $20/장, 로열티 없음 |
| Yulin (Jessy) | 물리 슬라이드 구매 협의 중 | 32종 예정 | 뷰웍스 스캔 후 TIFF 수령 |
| TCGA 오픈소스 | 사용 중 | 일부 | MVP용 |
| 3DHISTECH 샘플 | 사용 중 | 1종 (소장 H&E) | MVP용 |

**외부 문서에 중국 제조사명 미기재 원칙** (공급망 보호).

---

## 13. QA 거버넌스

### 13-1. QA 5대 무조건 체크리스트

**① 보안 & 멀티테넌시**
- institution_id 기반 슬라이드 접근 격리 확인
- JWT 토큰 변조 공격 방어
- session_token 1기기 동시접속 제어 (특별 계정 포함)
- Presigned URL TTL 정확히 5분
- 브라우저 캐시 no-store 헤더 확인

**② 파이프라인 안전성**
- COG TIFF 처리 시 파일 전체 메모리 로드 금지 (스트리밍 강제)
- QC 실패·ready_no_mpp 슬라이드 ready 전환 차단 확인
- educational_qc_status 미통과 슬라이드 학생 노출 차단

**③ 성능·부하 (locust 기반)**
- 동시 200명 접속 / 같은 슬라이드 집중 시나리오
- 첫 타일 응답 p95 < 2초 / 패닝·줌 p95 < 800ms
- 동적 워터마킹 benchmark (타일 1개당 ms 측정)

**④ 비즈니스 로직**
- subscription_end 경과 사용자 접근 차단
- TO 초과 시 신규 인증 차단 (기관 포털 게이지 연동)
- 지위 대조: 엑셀 지위와 가입 시 선택 지위 불일치 시 인증 차단
- /api/chat 진단·치료 질문 방어벽 작동

**⑤ DB 마이그레이션 & 라이선스 격리**
- 마이그레이션 스크립트 트랜잭션 처리, 중간 에러 시 전면 Rollback
- is_public=FALSE 슬라이드 비구독 기관 노출 차단

---

## 14. 9월 런칭 Go Criteria

```
1. 핵심 조직학 슬라이드 최소 80종 이상 ready 상태
2. P1 슬라이드 educational_qc_status passed 비율 90% 이상
3. locust 200명 동시접속 부하테스트 30분 통과
4. 첫 타일 p95 응답시간 2초 이하
5. 기관 관리자 학생 명단 업로드 실사용 테스트 완료 (지위 컬럼 포함)
6. AI 튜터 진단/치료 질문 방어 테스트 통과
7. 개인정보처리방침·이용약관·보안 설명서 준비 완료
8. 장애 대응 runbook 준비 완료
9. 비상 복구 권한 (동생 또는 신뢰 인력) 위임 완료
10. 교수 수업 페이지 생성 및 주차별 슬라이드 배치 기능 실사용 테스트 완료
```

---

## 15. 런칭 타임라인 (2026년)

| 기간 | 목표 |
|------|------|
| ~7월 말 | 개발 완성 (JWT 인증, 기관 포털, 파이프라인, 동적 워터마킹, 교수 수업 페이지) |
| 7월 말 | locust 부하테스트 1차 실행 |
| 8월 | 충남대 베타 — 200명 전면 오픈, 무료 1년 |
| 8월 | educational QC 체크리스트 작성, 대학원생 검수 시작 |
| 8월 말 | Go Criteria 전항목 점검 |
| 9월 | 전면 오픈 — 지방의대·치대·수의대·한의대 집중 영업 |
| 10월 | 대한해부학회 추계학술대회 부스 참가 |

---

## 16. 시장 세분화 및 영업 우선순위

| 순위 | 타겟 | 규모 | 전략 |
|------|------|------|------|
| 1 | 지방 의대 | ~30개교 | 충남대 레퍼런스, 아버지 납품 네트워크 |
| 1 | 치대·수의대 | ~21개교 | 경쟁자 없는 블루오션 |
| 2 | 한의대 | 12개교 | 동국대 → 도미노 |
| 3 | 약대·보건대·간호대 | 250개교+ | 카탈로그 배포 일괄 공략 |
| 후순위 | 서울 대형 의대 | ~10개교 | 레퍼런스 10개 확보 후 재공략 |

---

## 17. 리스크 평가

| 순위 | 리스크 | 가능성 | 영향 | 우선 액션 |
|------|--------|--------|------|-----------|
| 1 | 콘텐츠 라이선스/권리 | 중 | 매우 높음 | 계약서 Exhibit A 상세화 |
| 2 | 슬라이드 교육적 품질 | 높음 | 높음 | educational_qc_status + 대학원생 검수 |
| 3 | 첫 수업 장애 | 중~높음 | 매우 높음 | locust 부하테스트, 비상 fallback |
| 4 | 영업→계약 전환 지연 | 높음 | 높음 | 행정팀용 문서 패키지 |
| 5 | AI 튜터 오답/신뢰 | 높음 | 중~높음 | 검수 루프, "보조 도구" 포지셔닝 |
| 6 | 1인 운영 과부하 | 높음 | 높음 | runbook, 비상권한 위임 |

---

## 18. 운영 인력 계획

- **8월 베타까지**: 보람님 1인 + 자동화 모듈
- **9월 런칭 시**: 대학원생 파트타임 인턴 1명 (월 150만원, 1개월)
  - 역할: educational QC 검수 + knowledge_base JSON 수정
  - 채용 루트: 군대 고참 형님 → 서울대 기초조직학 교수 → 대학원생 소개
- **정규직 채용**: 구독 5개교 이상 + 초창패 수령 후

### 자동화 가능 영역
- 견적서·세금계산서 초안 자동 생성
- 서버 장애 알림 (5분 주기 → 카카오톡/문자)
- CS 이메일 자동 분류·응대 초안 (Gmail MCP)
- 구독 만료 리마인드 자동 발송 (60·30·7일 전)
- 월별 사용률 리포트 자동 생성

---

## 19. 개발 원칙 & 주의사항

- **AWS 자격증명**: nohup 컨텍스트에서 인라인 치환 실패 → 환경변수 먼저 export 후 실행
- **Windows SCP**: PEM 권한 설정은 비관리자 PowerShell에서 icacls 처리
- **COG 변환 배치**: TIFF 1장당 5~15분, 143장 = 최대 35시간 → EC2 밤새 배치 실행
- **매출 우선 원칙**: 정부지원보다 9월 매출 데이터 확보 최우선
- **모듈 경계 원칙**: `ConversionJob` / `ConversionResult` 데이터 계약 변경 금지
- **Render 콜드스타트**: Starter 슬립 모드 → 9월 전 Standard 전환 필수
- **동적 워터마킹 성능**: Pillow 처리 타일당 ms 반드시 benchmark
- **educational QC 원칙**: 기술 QC 통과 ≠ 서비스 가능. educational_qc_status passed 필수

---

## 20. 주요 외부 연락처

- Happy Science: Mallen Zhang (GM) / Linda Li / info@ihappysci.com
- Yulin: Jessy
- 성원애드피아: 명함 인쇄 (아르미 울트라화이트 310g 양면)
- 대한해부학회 추계학술대회: 매년 10월, 부스 신청 6~7월 예상

---

## 21. 사용자 플로우 개관

### 21-1. 사용자 유형 및 진입 구조

| 유형 | 진입 후 목적지 | 비고 |
|------|--------------|------|
| 학생 / 조교 / 교수 | 홈 화면 (수업 탭 / 전체 탭) | 지위별 권한 차이 있음 |
| 기관 관리자 | 기관 포털 (/portal) | 슈퍼관리자가 이메일 등록 후 접근 |
| 슈퍼관리자 | 어드민 대시보드 (/admin) | 아틀라스랩 내부 전용 |

### 21-2. 사용자 지위 체계 (확정)

**지위 3종**: 학생(student) / 조교(assistant) / 교수(professor)

**등록 방식**: 기관 관리자 엑셀 업로드 컬럼: `이메일 | 이름 | 지위(학생/조교/교수)`
가입 시 본인이 선택한 지위 + 엑셀 지위 대조 → 일치 시 인증 완료, 불일치 시 차단

**지위별 권한**:

| 지위 | 슬라이드 열람 | AI 튜터 | 수업 페이지 열람 | 수업 페이지 생성/편집 |
|------|-------------|---------|----------------|-------------------|
| 학생 | ✅ | ✅ | ✅ (소속 기관) | ❌ |
| 조교 | ✅ | ✅ | ✅ | ✅ (위임받은 수업만) |
| 교수 | ✅ | ✅ | ✅ | ✅ (본인 수업) |
| 기관관리자 | ✅ (TO 내 포함, 동시접속 차단 적용) | ✅ | ✅ | ❌ |

### 21-3. 홈 화면 구조

로그인 후 첫 화면: **수업 탭 / 전체 탭** 분리

- **수업 탭**: 소속 기관 교수 수업 목록 자동 표시 + 교수가 공유한 링크로도 접근 가능
- **전체 탭**: 구독 플랜 내 전체 슬라이드 목록 (과목 탭 분류)

### 21-4. 학생/조교/교수 플로우

```
slideatlas.net 접속
  → 로그인 / 회원가입 선택
      ├── 기존 회원: 이메일 + 비밀번호 → 인증 → 홈
      └── 신규 가입: 정보 입력 + 지위 선택(학생/조교/교수)
              → 이메일 인증 → 기관 명단 대조 (이메일 + 지위 동시 대조)
              ├── 일치: 계정 활성화 → 마이페이지 자동 생성 → 홈
              └── 불일치: "과 사무실 문의" 안내 → 관리자 명단 수정 → 재대조
  → 홈 (수업 탭 / 전체 탭)
  → 슬라이드 뷰어
  → AI 튜터 (구조가이드 / 질문하기 / 퀴즈)
  → 마이페이지 (즐겨찾기 / 열람기록)
```

### 21-5. 회원가입 핵심 정책

- 누구나 가입 시도 가능. 단, 명단 이메일 + 지위 모두 일치해야 계정 활성화.
- **순서 중요**: 기관관리자 명단 업로드 → 학생 가입. 계약 시 기관에 반드시 안내.
- 소속 기관·지위: 마이페이지에서 읽기 전용. 변경 필요 시 관리자 경유.
- 명단 수정 후 재가입 불필요 — 이미 입력한 정보로 자동 재대조.

### 21-6. 마이페이지 구성

- 프로필 정보 (이름·이메일·소속·지위 — 소속/지위 읽기 전용)
- 비밀번호 변경
- 즐겨찾기 목록 (슬라이드 카드 형태)
- 열람 기록 (날짜별 정렬, 재방문 버튼)

### 21-7. 구독 인원 기관 관리 정책

- TO 이하: 자유롭게 등록 가능
- TO 초과(N+1번째~): 인증 자체 차단 → "현재 정원이 초과됐습니다. 과 사무실에 문의하세요"
- 기관 포털 표시: TO 게이지 (예: 185 / 200명) 항상 표시
- 내부 관리(휴학·졸업생 정리)는 기관 자율 — SlideAtlas가 관여하지 않는다

### 21-8. 교수 수업 페이지 플로우

```
교수 로그인 → "내 수업" 메뉴
  → 수업 생성 (과목명, 학기)
  → 주차 추가 (예: 3주차 - 결합조직)
  → 슬라이드 추가 (전체 목록 중 선택, 순서 설정)
  → 조교 위임 (수업별 개별)
  → 학생에게 수업 페이지 링크 공유

학생/조교 접속
  → 수업 탭에서 소속 기관 수업 목록 자동 표시
  → 또는 교수가 공유한 링크로 직접 접근
  → 주차별 슬라이드 열람 → 뷰어 + AI 튜터 + 퀴즈
```

---

## 22. 기관관리자 포털 설계 스펙

### 22-1. 사이드바 구조

```
관리
  ├── 명단 관리       ← 메인 기능
  ├── 구독 플랜       ← 플랜별 슬라이드 목록 열람
  └── 이용 리포트     ← 보고자료용 통계

────────────────
  내 계정 (마이페이지 링크)
  로그아웃
```

> **"관리자 설정" 탭 없음** — 비밀번호 변경 등은 마이페이지에서 처리 (모든 사용자 공통)

### 22-2. 명단 관리

**엑셀 업로드 (메인 방식)**
- 컬럼: `이름 | 이메일 | 지위`
- 업로드 후 기존 명단에 추가 (덮어쓰기 아님)
- 양식 다운로드 버튼 제공

**인라인 편집**
- 업로드된 명단 전체가 항상 편집 가능 상태
- 이름·이메일: 텍스트 입력, 변경 시 상단/하단 저장 바 활성화
- 지위: 드롭다운 (학생/조교/교수 3종)
- 변경사항 생기면 "변경사항 저장" / "되돌리기" 버튼 활성화
- 변경 없으면 버튼 비활성 (실수 저장 방지)

**명단 다운로드**
- "명단 다운로드" 버튼 → `{기관명}_명단_{날짜}.csv` 다운로드
- UTF-8 BOM 처리 (엑셀 한글 깨짐 방지)
- 컬럼: 번호/이름/이메일/지위/인증상태

**삭제 확인 모달 문구 (확정)**
```
OOO 학생을 명단에서 삭제하시겠습니까?
삭제하면 이 구성원의 슬라이드 접근 권한이 즉시 차단됩니다.
재등록이 필요한 경우 명단에 다시 추가하십시오.
```

**개별 추가**: "+ 개별 추가" 버튼 → 빈 행 추가 후 커서 포커스

**검색·필터**: 이름/이메일 검색 + 지위 필터

**TO 게이지 (상단 통계 카드)**
- 등록 인원 / 전체 TO 숫자 + 진행률 바
- 90% 미만: 초록 / 90~99%: 주황 / 100%+: 빨간색 자동 전환
- TO 초과 시: "⚠ TO 초과 — 신규 인증 차단 중" 문구 표시

**기관관리자 등록**
- 최대 5명
- 슈퍼관리자가 최초 등록, 기관관리자 포털에서 추가 가능
- TO에 포함, 동시접속 차단 적용

### 22-3. 구독 플랜 탭

- 구독 중인 플랜 카드 목록 (플랜명 + 만료일 D-day)
- D-day 색상: 30일 이상 초록, 30일 이하 주황, 만료 빨간
- 카드 클릭 → 해당 플랜 슬라이드 목록 표시
  - 슬라이드 카드 검색·카테고리 필터
  - **슬라이드 클릭 → 뷰어 새 탭으로 이동** (기관관리자도 TO 내 열람 가능)
  - 엑셀 다운로드 (UTF-8 BOM CSV)
  - PDF 다운로드 (브라우저 인쇄 미리보기)

### 22-4. 이용 리포트 탭

**목적**: 구독료 정당화 도구 + 내부 보고자료

**표시 항목**
- 기간 선택: 최근 1개월 / 3개월 / 6개월 / 전체
- KPI 4종: 등록 구성원 / 슬라이드 총 조회수 / AI 튜터 호출 횟수 / 1인당 평균 조회수
- 월별 슬라이드 조회수 바 차트
- 구성원 활동 현황 (활성/비활성/미인증 도넛 차트)
- 인기 슬라이드 TOP 10 (클릭 시 뷰어 새 탭 이동)
- AI 튜터 월별 호출 바 차트

**PDF 리포트 자동 생성**
- SlideAtlas 로고 + 기관명 + 기간 헤더
- KPI 요약 → 월별 현황 → 인기 슬라이드 순으로 구성
- 브라우저 인쇄 미리보기 방식 (별도 라이브러리 불필요)
- 파일명: `SlideAtlas_{기관명}_이용리포트_{날짜}.pdf`

---

## 23. 슈퍼관리자 어드민 설계 스펙

### 23-1. 사이드바 구조

```
메인
  ├── 대시보드       ← 매출/갱신 현황
  ├── 기관 관리      ← 계약·플랜·만료일
  ├── 슬라이드 관리  ← 업로드·변환·QC
  └── 접근 제어      ← 플랜별 슬라이드 설정

분석
  └── 이용 리포트    ← 기관별 전체 조회

계정
  └── 특별 계정      ← 자문위원 등
```

### 23-2. 대시보드

- KPI 4종: 구독 기관 수 / 연간 구독료 합계 / 만료 임박 기관 수 / 전체 등록 구성원
- 월별 신규 구독 매출 바 차트
- 갱신 예정 기관 리스트 (D-day 색상 구분: 빨강 ≤14일, 주황 ≤30일, 초록 나머지)
- 전체 구독 기관 현황 테이블 (만료 임박 행 노란 배경 하이라이트)

### 23-3. 기관 관리

- 기관 추가/수정 모달: 기관명·플랜·TO·추가블록·구독시작일·만료일·기관관리자 이메일·구독료
- 기관별 검색, 만료 임박 필터
- 기관관리자 이메일 등록 (최대 5명)

### 23-4. 슬라이드 관리 (B+C 방식)

**주요 방식: S3 직접 업로드 + 어드민 메타데이터 등록**
```
S3에 TIFF 파일 업로드 (AWS CLI 또는 S3 콘솔)
  → 어드민에서 엑셀 업로드 (slide_id·s3_key·메타데이터)
  → 파이프라인 일괄 시작
  → 파이프라인 모니터에서 진행 확인
```

**보조 방식**: 웹 UI 1~2장 개별 업로드 (긴급 추가용)

**파이프라인 모니터**
- 슬라이드별 conversion_status 실시간 표시
- 변환 중: 점 깜빡임 애니메이션
- 실패: 빨간 점 + 오류 로그 표시
- 전체 슬라이드 테이블: 기술 QC + educational QC 상태 동시 표시

### 23-5. 접근 제어

**플랜 카드 방식**
- 플랜 카드 목록 (Department / Standard / Campus / Institution + "새 플랜 추가" 카드)
- 카드 클릭 → 편집 화면 진입
- 편집 화면: 좌측(현재 포함 슬라이드 + 삭제) / 우측(전체 슬라이드 + 추가)
- 중복 추가 가능 (이미 추가됨 표시만, 차단 안 함)
- 카테고리 필터 (조직학/병리학/기생충학)
- 변경사항 생기면 저장 바 활성화 → "수정 완료" 클릭 시 반영
- 저장 안 한 채로 뒤로 가면 확인 팝업

### 23-6. 이용 리포트 (슈퍼관리자)

- 기관 선택 버튼으로 기관 전환
- 기관관리자가 보는 것과 동일한 리포트 표시
- 기관별 PDF 리포트 생성 가능

### 23-7. 특별 계정

- 자문위원·파트너 등 무상 무한 접근 계정
- **TO 미포함** (기관 인원 카운트에서 제외)
- **동시접속 차단 적용** (일반 사용자와 동일)
- 슈퍼관리자가 ID(이메일) + 임시 PW 직접 발급
- 임시 PW 자동 생성 (랜덤 10자리, 특수문자 제외)
- 첫 로그인 후 비밀번호 변경 안내
- PW 재발급 버튼 (기존 계정 임시 PW 재생성)

---

## 24. 뷰어 화면 설계 스펙

### 24-1. 전체 레이아웃

```
┌──────────────────────────────────────────────────────────────┐
│              상단 툴바 (44px, 네이비 #0F1F3D)                   │
│  ← 목록  │  [슬라이드 제목 bold white] / [H&E teal] / [배율 amber]  │  ★  │
├──────────────────────────────────┬───────────────────────────┤
│                                  │   AI 튜터 패널             │
│    슬라이드 뷰어 영역              │   (300px, 흰 배경)         │
│    (OpenSeadragon)               │                           │
│                                  │   [슬라이드 메타데이터]      │
│  [미니맵]              [5.02mm]  │   [탭: 구조가이드/질문/퀴즈] │
│                       ◁ 토글버튼 │   [AI 응답 영역]            │
│        [하단 배율 바]             │   ─────────────────────── │
│  − 0.6× + │전체│1×│4×│10×│20×│40×│   [툴바: 거리측정/스냅샷/보정] │
└──────────────────────────────────┴───────────────────────────┘
```

### 24-2. 상단 툴바

- **슬라이드 제목**: 15px, font-weight 700, #ffffff
- **염색법 (H&E 등)**: 13px, font-weight 600, #5DCAA5 (teal)
- **현재 배율**: 13px, font-weight 600, #EF9F27 (amber) — 배율 변경 시 실시간 업데이트
- **즐겨찾기 (★)**: 우측 끝, 클릭 시 amber 활성화

### 24-3. 슬라이드 뷰어 영역

- OpenSeadragon 기반 / 마우스 휠: 줌 / 드래그: 이동 / 터치: 핀치줌·스와이프
- **좌하단 미니맵**: 파이프라인에서 minimap.png 사전 생성 → S3 저장 → OSD 로드
- **우하단**: 현재 물리 거리 표시 (예: 5.02 mm)

### 24-4. 하단 배율 바

- 위치: 뷰어 하단 중앙 플로팅 (반투명 다크 배경)
- 구성: `−` | 현재배율(활성) | `+` | 구분선 | `전체` `1×` `4×` `10×` `20×` `40×`
- 현재 선택 배율: 초록(#1D9E75) 강조
- 배율 변경 시: 상단 툴바 배율 + 패널 배율 뱃지 동시 업데이트

### 24-5. AI 튜터 패널

- 너비: 300px (전체 화면의 약 32%), 흰 배경
- **패널 토글**: 패널 좌측 중앙 ◁/▷ 화살표 버튼 — 숨김/열림, 방향 반전
- 패널 숨김 시 뷰어 전체 너비 사용

**메타데이터 영역**
- 슬라이드 제목: 16px, font-weight 500
- 슬라이드 ID + 계통: 12px, tertiary color
- 뱃지 3종: 염색법(초록 #E1F5EE), 계통(파랑 #E6F1FB), 배율(주황 #FAEEDA)

**탭 3종**: 구조 가이드 / 질문하기 / 퀴즈
- 활성 탭: teal 하단 보더 + font-weight 500

**AI 응답 영역**
- Atlas AI 아바타(초록 원형) + 이름
- 본문: 13px, line-height 1.7
- Observe 박스: 연초록 배경(#E1F5EE) + 좌측 3px teal 보더
- 핵심 키워드 teal bold 하이라이트

**패널 하단 툴바** (항상 노출)
- 거리 측정 / 스냅샷 / 이미지 보정

### 24-6. 거리 측정 툴

1. 패널 하단 "거리 측정" 버튼 클릭 → 버튼 초록 활성화 + 커서 십자선(+)
2. 시작점 좌클릭 → 점 표시
3. 이동 시 점선 + 실시간 거리 미리보기
4. 끝점 좌클릭 → 실선 확정, 라벨 고정
5. 반복 측정 가능
6. **우클릭 → 모든 측정선 즉시 전체 삭제** (trade-off 인지: 재측정 어렵지 않음)
7. 버튼 재클릭 또는 ESC → 이동 모드 복귀

```
실제 거리 = pixel_distance × MPP(μm/px)
100μm 미만 → μm / 100μm 이상 → mm 자동 전환
```

- `ready_no_mpp` 슬라이드: 버튼 비활성화 + "MPP 정보 없음" 툴팁
- 버튼이 패널 하단 툴바에 항상 노출 → 기능 존재 자체를 자연스럽게 인식

### 24-7. 스냅샷

- 저장 내용: 뷰어 화면 + 측정선(있을 경우) + 동적 워터마크
- 형식: PNG
- 파일명: `SlideAtlas_{slide_id}_snapshot.png`
- 구현: `canvas.toBlob()` — 보이는 그대로 저장
- 워터마크: 사용자 이메일 + SlideAtlas 브랜드, 대각선 반복, 투명도 18~22%

### 24-8. v2.0 예정 기능 (현재 범위 외)

- 어노테이션 영역 지정 + 저장
- 동기화 멀티뷰
- 강의 포인터 (프레젠테이션 모드)
- Apple Pencil / S펜 마킹 (네이티브 앱 전환 후)

---

*최종 업데이트: 2026-05-29 v2.6*
*주요 변경: 섹션 10(구독 플랜 구조 확정), 섹션 22(기관관리자 포털 전체 설계), 섹션 23(슈퍼관리자 어드민 전체 설계), 섹션 24(뷰어 설계, 구 섹션 23에서 번호 조정), 슬라이드 수급 파이프라인 B+C 방식 확정, 사용자 플로우 지위 체계·홈 화면 구조 확정, DB 스키마 plan_slides·ai_chat_logs 추가*

---

## 25. 교수 수업 페이지 상세 설계 스펙

### 25-1. 개요 및 구조

**개설 주체**: 교수 + 조교 (교수가 위임한 수업에 한해 조교도 편집 가능)
**수업 단위**: 수업 1개 = 페이지 1개 (예: 조직학 실습 2026-2학기)
**구조**: 수업 → 주차 목록 → 주차 클릭 → 슬라이드 목록 → 슬라이드 클릭 → 뷰어

```
수업 (조직학 실습 2026-2학기)
  └── 1주차 - 상피조직
  └── 2주차 - 결합조직
        └── 슬라이드 목록 (클릭 → 뷰어 새 탭)
```

**주차 안 추가 계층 없음** — 주차 안에는 슬라이드만. 단순함 우선.

### 25-2. 학생 접근 방식

- **자동 표시**: 같은 기관(institution_id) 소속 전체 학생에게 수업 목록 자동 노출
- **링크 접근**: 교수가 공유한 URL로도 접근 가능 (같은 기관 내 인증된 사용자 한정)
- **두 경로 모두 허용**

### 25-3. 학생 수업 탭 구조 (확정)

**내 수업 탭**
- 학생이 직접 등록한 수업 목록
- 수업 카드 우측 "등록 해지" 버튼
- 등록 수업 없을 시 "전체 수업 탭에서 등록하세요" 안내

**전체 수업 탭**
- 기관 내 개설된 모든 공개 수업 목록
- 수업 카드 우측 "내 수업 등록" 버튼
- 이미 등록된 수업은 "등록됨" 뱃지 표시 (버튼 비활성)

### 25-4. 교수/조교 편집 화면

**수업 개설 모달**
- 입력: 수업명, 학기 선택
- 개설 즉시 기관 내 전체 학생에게 노출

**조교 지정**
- 수업별 개별 지정 (전체 수업 권한 아님)
- 검색 대상: 지위가 **"조교"** 인 등록 구성원만 표시
- 안내 문구: "지위가 '조교'인 구성원만 표시됩니다"
- 이미 지정된 조교: "이미 지정됨" 표시 + 선택 비활성

**주차 관리**
- 주차 추가: 주차 제목 입력 (예: 3주차 - 결합조직)
- 주차 삭제: 주차 우측 휴지통 버튼
- 주차 펼침/접힘: 클릭으로 토글

**슬라이드 배치**
- 주차 우측 "+" 버튼 → 슬라이드 선택 모달
- 체크박스 다중 선택 → "추가" 클릭 → 반영
- 슬라이드 검색 가능 (이름/ID)
- 이미 추가된 슬라이드도 중복 추가 가능 (차단 안 함)
- 슬라이드 제거: 행 우측 X 버튼

### 25-5. DB 연관 테이블

섹션 8 DB 스키마 참조:
- `courses`: 수업 기본 정보 (professor_user_id, institution_id, title, semester)
- `course_weeks`: 주차 (course_id, week_number, title)
- `course_week_slides`: 주차별 슬라이드 (course_week_id, slide_id, display_order)
- `course_assistants`: 수업별 조교 위임 (course_id, user_id)
- 학생 수업 등록: `course_enrollments` 테이블 추가 필요

```sql
CREATE TABLE course_enrollments (
  course_id INT REFERENCES courses(id),
  user_id INT REFERENCES users(id),
  enrolled_at TIMESTAMP DEFAULT NOW(),
  PRIMARY KEY (course_id, user_id)
);
```

### 25-6. 권한 정리

| 작업 | 학생 | 조교 | 교수 |
|------|------|------|------|
| 수업 목록 열람 | ✅ | ✅ | ✅ |
| 수업 등록/해지 | ✅ | ✅ | — |
| 슬라이드 열람 | ✅ | ✅ | ✅ |
| 수업 개설 | ❌ | ✅ (위임 시) | ✅ |
| 주차 추가/삭제 | ❌ | ✅ (위임 시) | ✅ |
| 슬라이드 배치 | ❌ | ✅ (위임 시) | ✅ |
| 조교 지정 | ❌ | ❌ | ✅ |
| 수업 삭제 | ❌ | ❌ | ✅ |

*최종 업데이트: 2026-05-29 v2.6 추가*
*섹션 25 신규: 교수 수업 페이지 상세 설계 (조교 지정, 학생 수업등록/해지, 내 수업 탭 구조)*
