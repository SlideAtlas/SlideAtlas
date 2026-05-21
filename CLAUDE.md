# CLAUDE.md — SlideAtlas 프로젝트 메모리 v2.0

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

### v1.0 — 한국 런칭 (현재 목표)
- **타겟**: 국내 지방의대·수의대·약대·한의대·보건대
- **콘텐츠**: 아틀라스랩이 직접 라이선스 계약한 컬렉션만 제공 (교수 업로드 없음)
- **AI 튜터**: 슬라이드 메타데이터 + `knowledge_base` JSON → Claude API (VectorDB 없음)
- **구독 플랜**: 조직학 베이스 플랜 → 병리·기생충 모듈 추가 방식, 연 350~600만원
- **마일스톤**: 9월 가을학기 2~3개교 구독 확보 → 초창패 추경 신청

### v1.5 — 콘텐츠 확장·국내 안착
- **콘텐츠**: 병리·기생충 모듈, Mahidol 열대의학 컬렉션 라이선스
- **AI 튜터**: 자문 교수 1인 영입 → knowledge_base JSON 검수·보완
- **영업**: 국내 10~15개교 확보, 매출 레퍼런스 구축

### v2.0 — 글로벌 플랫폼
- **콘텐츠**: Liverpool 열대의학, 아마존·아프리카 기생충학 특수 컬렉션
- **교수 업로드**: 강의노트·PPT 업로드 기능 오픈, 조회수 기반 로열티
- **AI 튜터**: Vector DB (multilingual-e5) + RAG + 다국어 출력
- **구조**: 유튜브식 콘텐츠 마켓플레이스, Fleet Learning 구조

> **설계 원칙**: v2.0 기능(VectorDB, 교수 업로드, 다국어, 로열티 정산)은 v1.0 범위에서 제외.
> 단, 코드 모듈 경계는 처음부터 v2.0 확장을 고려해 설계한다.

---

## 3. 현재 기술 스택

| 구분 | 내용 |
|------|------|
| 백엔드 | Python Flask |
| 뷰어 | OpenSeadragon |
| 배포 | Render Starter ($7/월) |
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
                    ↘            ↘
                     failed       failed
```

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
  conversion_status VARCHAR(20) DEFAULT 'pending',  -- pending/converting/qc_check/ready/failed
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
```

---

## 8. 보안 아키텍처

- **Presigned URL**: TTL 5분, 만료 후 타일 접근 불가, S3 버킷 퍼블릭 접근 전면 차단
- **동적 워터마킹**: v1.0 런칭 시 포함. 사용자 ID·기관명을 타일마다 투명하게 삽입 (Pillow, 투명도 15~20%, 대각선 반복 패턴). Happy Science 등 라이선스 콘텐츠 유출 시 추적 가능.
- **브라우저 캐시 완전 차단**: 타일 응답 헤더에 `Cache-Control: no-store, no-cache` 적용. 고객 로컬에 타일 파일 저장 불가. 뷰어 종료 시 메모리에서도 소멸.
- **서버사이드 캐시**: EC2 메모리 캐시로 동일 유저·동일 타일 재처리 방지 (보안 위험 없음, 서버에만 존재)
- **동시접속 제어**: 새 기기 로그인 시 기존 session_token 무효화 (기관 해약 아닌 세션 종료만)
- **도메인 기반 자가인증**: 기관 이메일 도메인 검증 + 6개월 재인증
- **멀티테넌시**: institution_id 기반 Row Level 격리
- **라이선스 격리**: is_public=FALSE 슬라이드는 어떤 경로로도 직접 URL 접근 불가

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

## 12. QA 거버넌스

### QA 5대 체크리스트 (하나라도 미통과 시 Reject)

**① 보안 & 멀티테넌시**
- YU 계정으로 SNU 슬라이드 URL 조작 접근 차단 확인
- JWT 토큰 변조 공격 방어
- session_token 1기기 동시접속 제어
- Presigned URL TTL 정확히 5분

**② 파이프라인 안전성**
- COG TIFF 처리 시 파일 전체 메모리 로드 금지 (스트리밍 강제)
- QC 실패 슬라이드가 ready 상태로 전환되지 않는지 확인
- 미니맵·썸네일 S3 경로가 DB에 정확히 저장되는지 확인

**③ 비즈니스 로직**
- subscription_end 경과 사용자 접근 차단 및 결제 유도 팝업
- /api/chat 탈옥 질문 시 방어벽 작동

**④ DB 마이그레이션 안전성**
- 마이그레이션 스크립트 트랜잭션 처리
- 중간 에러 시 전면 Rollback

**⑤ 라이선스 격리**
- is_public=FALSE 슬라이드 비구독 기관 노출 차단
- Happy Science 라이선스 콘텐츠 외부 유출 경로 차단

### 워크플로우 규칙
- Dev ↔ QA 핑퐁 최대 3회, 초과 시 CEO 판단 대기
- 인프라 변경(RDS, EC2, S3)은 CEO 명시적 승인 후 실행
- 반복 수정 시 전체 재작성보다 diff 기반 수정 우선

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

*최종 업데이트: 2026-05-21 v2.0 | 다음 업데이트: Happy Science 계약 완료 시점*
