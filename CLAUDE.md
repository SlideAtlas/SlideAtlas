# CLAUDE.md — SlideAtlas 프로젝트 메모리 v1.1

> 이 파일은 Claude Code 세션 시작 시 반드시 읽어야 하는 프로젝트 컨텍스트 파일입니다.
> 모든 에이전트(오케스트레이터, 개발, QA)는 이 파일을 기준으로 작업합니다.

---

## 1. 프로젝트 개요

**제품명**: SlideAtlas  
**운영사**: 아틀라스랩 주식회사 (Atlas Lab Co., Ltd.)  
**대표**: 김보람  
**URL**: slideatlas.onrender.com  
**도메인**: atlaslab.co.kr (가비아)  
**이메일**: boram@atlaslab.co.kr  

**한 줄 정의**: 의과대학·치과대학·수의대·한의대·약대·간호대를 대상으로 한 디지털 병리/조직학 WSI(Whole Slide Image) 구독 SaaS 플랫폼.

**핵심 비즈니스 모델**: 오프라인 슬라이드 납품(보람바이오텍, 20년 의대 납품 이력) 네트워크를 디지털 구독 SaaS로 전환. 연 400만원 구독료, 장비 불필요(WinMedic 등 경쟁사 대비 차별점).

**장기 비전**: 각 대학이 자체 WSI를 플랫폼에 제공하고 조회수 기반 로열티를 수령하는 유튜브식 콘텐츠 마켓플레이스. 세계 유일 글로벌 의료교육 학습 시스템.

---

## 2. 현재 기술 스택

| 구분 | 내용 |
|------|------|
| 백엔드 | Python Flask |
| 뷰어 | OpenSeadragon + OpenSlide + DeepZoom |
| 배포 | Render Starter ($7/월) |
| 저장소 | AWS S3 (ap-northeast-2, 버킷: slideatlas-slides) |
| 타일서버 | AWS EC2 t3.small → **t3.medium 업그레이드 예정** (slideatlas-tileserver, ec2-13-209-99-51.ap-northeast-2) |
| 타일엔진 | titiler + 커스텀 타일서버 (~/tileserver/main.py, rasterio 기반) |
| 파이프라인 | SVS → COG TIFF → S3 → titiler |
| 데이터 관리 | slides.json + institutions.json → **RDS PostgreSQL 마이그레이션 예정** |
| AI 연동 | Claude API (/api/chat), 마크다운 렌더링, 구조가이드/질문하기/퀴즈 탭 |
| 버전 관리 | GitHub (SlideAtlas/SlideAtlas) |

---

## 3. 슬라이드 ID 체계

형식: `{기관코드}-{과목코드}-{순번}`

**기관코드** (ICAO식):
- SA: SlideAtlas 자체
- HS: Happy Science (라이선스 콘텐츠)
- YU: 연세대학교
- SNU: 서울대학교
- KU: 고려대학교
- MU: Mahidol University
- AJOU: 아주대학교

**과목코드**:
- HST: 조직학 (Histology)
- PATH: 병리학 (Pathology)
- PARA: 기생충학 (Parasitology)
- ANAT: 해부학 (Anatomy)
- EMBRY: 발생학 (Embryology)

예시: `HS-HST-001`, `HS-PATH-004`

---

## 4. Target Architecture (v1.0 상업출시)

```
[사용자 브라우저]
    │
    ▼
[Render - Flask 앱]  ← 인증/세션/API 라우팅
    │
    ├─ /viewer/<slide_id>  → OpenSeadragon 뷰어
    ├─ /api/chat           → Claude API (탈옥 방어 프롬프트 포함)
    └─ /api/tiles/<slide_id>/<z>/<x>/<y>
                           → Presigned URL 발급 (TTL 5분, S3 직접 접근 차단)
    │
    ▼
[AWS RDS PostgreSQL]
    - institutions, users, subscriptions
    - slides, plan_slide_access, access_logs
    │
    ▼
[AWS S3] ← COG TIFF 원본 보관 (퍼블릭 접근 차단)
    │
    ▼
[AWS EC2 titiler - t3.medium]
    - S3에서 COG 읽어 타일 반환
    - Presigned URL로만 접근 허용 (직접 접근 차단)
```

---

## 5. DB 스키마 (v1.0 기준)

```sql
-- 기관
CREATE TABLE institutions (
  id VARCHAR(20) PRIMARY KEY,          -- 'YU', 'SNU' 등
  name_ko VARCHAR(100),
  name_en VARCHAR(100),
  domain VARCHAR(100),                 -- 'yonsei.ac.kr' 도메인 기반 자가인증
  subscription_plan VARCHAR(20),       -- 'basic', 'standard', 'premium'
  subscription_start DATE,
  subscription_end DATE,
  max_users INT,
  created_at TIMESTAMP DEFAULT NOW()
);

-- 사용자
CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  institution_id VARCHAR(20) REFERENCES institutions(id),
  email VARCHAR(200) UNIQUE NOT NULL,
  password_hash VARCHAR(255),
  role VARCHAR(20) DEFAULT 'student',  -- 'admin', 'professor', 'student'
  last_login TIMESTAMP,
  session_token VARCHAR(255),          -- 동시접속 1기기 제어용
  created_at TIMESTAMP DEFAULT NOW()
);

-- 슬라이드
CREATE TABLE slides (
  id VARCHAR(50) PRIMARY KEY,          -- 'HS-PATH-004' 등
  institution_id VARCHAR(20),          -- 콘텐츠 제공 기관 (NULL = AtlasLab 자체)
  subject_code VARCHAR(20),            -- 'HST', 'PATH' 등
  title_ko VARCHAR(200),
  title_en VARCHAR(200),
  description TEXT,
  s3_key VARCHAR(500),                 -- COG TIFF S3 경로
  thumbnail_url VARCHAR(500),
  mpp FLOAT,                           -- microns per pixel
  width INT,
  height INT,
  stain VARCHAR(50),                   -- 'H&E', 'PAS' 등
  organ VARCHAR(100),
  species VARCHAR(50) DEFAULT 'human',
  license_source VARCHAR(100),         -- 'HappyScience', 'TCGA' 등
  is_public BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP DEFAULT NOW()
);

-- 구독 플랜별 접근 가능 과목
CREATE TABLE plan_slide_access (
  plan VARCHAR(20),
  subject_code VARCHAR(20),
  PRIMARY KEY (plan, subject_code)
);

-- 접근 로그
CREATE TABLE access_logs (
  id SERIAL PRIMARY KEY,
  user_id INT REFERENCES users(id),
  slide_id VARCHAR(50) REFERENCES slides(id),
  accessed_at TIMESTAMP DEFAULT NOW(),
  session_id VARCHAR(100)
);
```

---

## 6. 보안 아키텍처 원칙

- **Presigned URL**: TTL 5분, 만료 후 타일 접근 불가, S3 버킷 퍼블릭 접근 전면 차단
- **동시접속 제어**: 새 기기 로그인 시 기존 session_token 무효화 (기관 해약 아닌 세션 종료만 적용)
- **도메인 기반 자가인증**: 기관 이메일 도메인 검증 + 6개월 재인증
- **멀티테넌시**: institution_id 기반 Row Level 격리, URL 조작으로 타 기관 데이터 접근 불가
- **라이선스 격리**: is_public=FALSE 슬라이드는 어떤 경로로도 직접 URL 접근 불가

---

## 7. 콘텐츠 현황

| 공급사 | 상태 | 수량 | 비고 |
|--------|------|------|------|
| Happy Science (Linda Li) | 계약 진행 중 | 조직학 133종+ | 최우선 파트너, 5월 신향 미팅 |
| TCGA 오픈소스 | 사용 중 | 일부 | MVP용 |
| 3DHISTECH 샘플 | 사용 중 | 1종 (소장 H&E) | MVP용 |
| Vic Science (Joy Xu) | 응답 대기 | - | RFP-002 발송 완료 |
| Hongye (Lily Zhao) | 응답 대기 | - | RFP-002 발송 완료 |

**주의**: 외부 문서에 중국 제조사명 미기재 원칙 (공급망 보호).

---

## 8. 🛡️ AI 에이전트 팀 거버넌스 및 QA 검증 규정 (v1.0)

### 8-1. 에이전트 구성

Claude Code 세션 내 오케스트레이터는 복잡한 상용화 기능 개발 시 반드시 두 서브에이전트를 이원화하여 운영한다.

**Lead Developer (개발 에이전트)**
- 역할: Flask 웹앱 + AWS RDS PostgreSQL 인프라 코드 작성
- 성향: 기능 구현 중심, 빠른 프로토타이핑, 효율적인 코드 지향
- 제약: 인프라 변경(RDS, EC2, S3)은 반드시 CEO 승인 후 실행

**Senior QA Engineer (검증 에이전트 — 레드팀)**
- 역할: 개발 에이전트 결과물을 해커 관점으로 공격, 예외 상황 발굴, 반려(Reject) 처리
- 성향: 극도로 보수적, 타협 없는 보안 및 상용화 품질 요구
- 권한: 5대 체크리스트 중 하나라도 미통과 시 무조건 반려

### 8-2. QA 5대 무조건 체크리스트

하나라도 통과 못하면 **Reject & Rework** 명령.

**① 보안 & 멀티테넌시**
- YU 계정으로 SNU 슬라이드/S3 경로에 URL 조작으로 접근 가능한지 확인
- JWT 토큰 변조 공격 방어 상태 검증
- session_token 기반 1기기 동시접속 제어 완전 작동 여부
- Presigned URL TTL이 정확히 5분으로 설정되었는지 확인

**② 대용량 생존성**
- COG TIFF 처리 시 파일 전체를 메모리에 올리는 로직 여부 감시 (스트리밍 강제)
- RDS PostgreSQL 동시 접속 시 커넥션 풀 폭발 방어 확인

**③ 비즈니스 로직 & 엣지케이스**
- subscription_end 1초 경과 사용자의 접근 시 결제 유도 팝업 및 차단 발동 확인
- /api/chat 탈옥(Jailbreak) 질문 시 시스템 프롬프트 방어벽 작동 확인 (SlideAtlas 무관 질문 차단)

**④ DB 마이그레이션 안전성**
- slides.json → RDS 이관 스크립트에 트랜잭션(Transaction) 처리 여부
- 중간 에러 발생 시 전면 Rollback 대책 존재 여부

**⑤ 라이선스 격리**
- is_public=FALSE 슬라이드가 어떤 경로(직접 URL, API, 타일서버)로도 비구독 기관에 노출되지 않는지 확인
- Happy Science 라이선스 콘텐츠가 계약 기관 외부에 유출되는 경로 존재 여부

### 8-3. 워크플로우 통제 규칙

- **Max Turns 3회**: Dev ↔ QA 핑퐁은 한 이슈당 최대 3회. 초과 시 즉시 중단 → 작업 로그 보존 → CEO 판단 대기
- **인프라 변경 금지**: RDS, EC2, S3 설정 변경은 CEO 명시적 승인 없이 절대 실행 불가
- **토큰 절약**: 반복 수정이 발생하는 경우 전체 재작성보다 diff 기반 수정 우선

### 8-4. 외부 고문단 — Gemini (레드팀 어드바이저)

**역할 정의**: Gemini는 Claude Code 에이전트 루프 외부에서 작동하는 독립 레드팀 고문이다. 실시간 개입 없음.

**활용 시점**:
1. **작업 착수 전**: 해당 기능의 설계 방향, 중점 검토 사항을 Gemini에게 질의 → 결과를 Claude Code 세션에 컨텍스트로 제공
2. **작업 완료 후**: Dev + QA가 완성한 결과물을 Gemini에게 제시 → "Claude가 놓친 것이 있는가?" 교차 검증 요청

**Gemini 컨텍스트 공유 원칙**:
- 유료 플랜 사용 시 CLAUDE.md + DB 스키마 + 아키텍처 다이어그램 공유
- 중국 공급사 계약 조건, 특정 대학 협상 내용은 공유 금지 (공급망 및 영업 보안)
- Gemini 조언은 참고용이며, 최종 판단은 항상 CEO(오케스트레이터)가 한다

---

## 9. 로드맵 (v1.0 상업출시 기준)

| 단계 | 기간 | 핵심 작업 |
|------|------|-----------|
| W1 | Happy Science 계약 완료 직후 | EC2 t3.medium 업그레이드, RDS 인스턴스 생성 |
| W1~2 | D+1~2 | slides.json → RDS 마이그레이션 스크립트 |
| W2 | D+2~3 | 133장 COG 변환 + S3 배치 업로드 자동화 |
| W2~3 | D+3~4 | JWT 인증 + 기관별 접근제어 |
| W3 | D+4~5 | Presigned URL 타일 보안 적용 |
| W3~4 | D+5~7 | 구독 플랜 UI + 관리자 기관 관리 탭 |
| W4 | D+7~ | 베타 서비스 오픈, 초창패 추경 대응 |

---

## 10. 주요 외부 연락처 (참고용)

- Happy Science: Linda Li / info@ihappysci.com / WhatsApp +86 188 3816 1683
- Vic Science: Joy Xu / joy@vicscience.com
- Hongye: Lily Zhao / Lianhonglianli@163.com
- 성원애드피아: 명함 인쇄 (아르미 울트라화이트 310g 양면)

---

## 11. 개발 원칙 & 주의사항

- **AWS 자격증명**: nohup 컨텍스트에서 인라인 `$(aws configure get ...)` 치환 실패 → 환경변수 먼저 export 후 실행
- **Windows SCP**: PEM 권한 설정은 비관리자 PowerShell에서 icacls 처리 (관리자 PowerShell은 계정 매핑 오류)
- **한국어 PDF**: reportlab/weasyprint/Cairo 모두 한글 폰트 임베딩 한계 → Adobe Illustrator 직접 작업
- **중국어 문서**: Node.js docx 패키지, SimSun TextRun 별도 분리 필요
- **COG 변환 배치**: SVS 1장당 5~15분, 133장 = 최대 30시간 → EC2에서 밤새 배치 실행
- **매출 우선 원칙**: 정부지원(초창패 등)보다 9월 매출 데이터 확보가 최우선

---

*최종 업데이트: 2026-05-16 | 다음 업데이트: Happy Science 계약 완료 시점*
