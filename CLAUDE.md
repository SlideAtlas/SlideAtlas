# SlideAtlas — CLAUDE.md

> 이 파일은 Claude(AI 어시스턴트)가 새 세션 시작 시 프로젝트 컨텍스트를 즉시 파악하기 위한 참조 문서입니다.
> 코드 수정 시 이 파일도 함께 업데이트해 주세요.

---

## 프로젝트 개요

- **서비스명**: SlideAtlas
- **URL**: https://slideatlas.onrender.com
- **목적**: 의과대학용 디지털 병리·조직학 WSI(Whole Slide Image) 뷰잉 + AI 튜터링 플랫폼
- **법인**: 아틀라스랩 주식회사(Atlas Lab Co., Ltd.) — 대표이사 김보람 (Boram Kim)
- **연계 법인**: 라미인터네셔널(기존 운영 법인), 보람바이오텍(부친, 20년 의대 슬라이드 납품)
- **GitHub**: https://github.com/SlideAtlas/SlideAtlas

---

## 기술 스택

| 구성 요소 | 내용 |
|-----------|------|
| 백엔드 | Python Flask |
| WSI 처리 | OpenSlide + DeepZoom |
| 뷰어 | OpenSeadragon |
| 배포 | Render Starter ($7/월) |
| 스토리지 | AWS S3 (`ap-northeast-2`, 버킷: `slideatlas-slides`) |
| 타일서버 | AWS EC2 (`slideatlas-tileserver`, t3.small) + titiler |
| AI | Claude API (`/api/chat` 엔드포인트) |
| 데이터 | `slides.json` + `institutions.json` (현재), PostgreSQL RDS 예정 |
| 인증 | 현재 없음 → JWT 예정 (W4) |

**EC2 정보**
- Host: `ec2-13-209-99-51.ap-northeast-2.compute.amazonaws.com`
- 타일서버: `~/tileserver/main.py` (rasterio 기반, nohup 실행)
- 슬라이드 파이프라인: SVS → COG TIFF → S3 → titiler

---

## 파일 구조

```
SlideAtlas/
├── server_render.py          # Flask 메인 앱 (라우트 + HTML 인라인)
├── slides.json               # 슬라이드 메타데이터 (id, title, institution 등)
├── institutions.json         # 기관 정보
├── requirements.txt
└── README.md
```

> 현재 단일 파일(server_render.py) 구조. W3(RDS 마이그레이션) 이후 분리 예정.

---

## 주요 라우트

| 라우트 | 설명 |
|--------|------|
| `/` | 랜딩페이지 |
| `/slides` | 슬라이드 목록 (slides.json 동적 렌더링) |
| `/viewer/<slide_id>` | 슬라이드별 독립 WSI 뷰어 |
| `/admin` | 관리자 페이지 (슬라이드 추가/수정/삭제) |
| `/api/chat` | Claude API 중계 엔드포인트 |

---

## AI 튜터 구조

- 뷰어 내 탭 3개: **구조가이드** / **질문하기** / **퀴즈**
- `/api/chat` → Flask → Anthropic API (서버사이드 중계)
- 환경변수: `ANTHROPIC_API_KEY` (Render 설정)
- 마크다운 렌더링 적용
- Knowledge Base: 현재 시스템 프롬프트 방식 (MVP), 향후 기관별 KB 예정

---

## 슬라이드 ID 체계

```
{기관코드}-{과목코드}-{순번}
예: SA-PATH-0002, YU-HST-001
```

---

## 비즈니스 모델 (확정)

**구독 구조 (기관 단위, 연간)**

| 플랜 | 금액 |
|------|------|
| 베이스 (조직학 89종+, 학교 무제한 계정) | 연 400만원 / 학기 250만원 |
| +인체병리 모듈 | +150만원 |
| +기생충 모듈 | +100만원 |
| +수의병리 모듈 | +100만원 |
| +발생학 모듈 | +80만원 |
| +구강조직 모듈 | +80만원 |
| +파트너기관 모듈 | +100~200만원 |
| AI튜터 토큰풀 | +50만원/년 |

**타겟**: 의대 40개 + 치대 11 + 한의대 12 + 약대 37 + 수의대 10 + 간호대/보건전문대 200+

---

## 사용자 인증 정책 (설계 확정, 미구현)

1. 도메인 기반 자가인증 (기관 이메일 화이트리스트)
2. 6개월 재인증 (학기마다)
3. 동시접속 1기기 제한 (새 기기 로그인 시 기존 세션 강제 종료)
4. 계정 공유 발견 시 해당 계정 세션 종료 (기관 해약 아님)

---

## 콘텐츠 현황

| 소스 | 상태 |
|------|------|
| TCGA 오픈소스 | MVP 활용 중 |
| 3DHISTECH 샘플 DCM (소장 H&E) | MVP 활용 중 |
| Henan Zhizao (중국) | 협상 종료 (디지털 라이선스 거절) |
| Xinxiang Hongye Edu. (Lily Zhao) | RFP 발송 완료 (SlideAtlas-RFP-2026-002) |
| Xinxiang Xinxin Educational | RFP 발송 완료 |
| Xinxiang Vic Science | RFP 발송 완료 |

**스캐닝**: 뷰웍스 유료 스캐닝 서비스 활용 예정 (스캐너 직접 구매 대신)

---

## 주요 미해결 사항

- [ ] 중국 업체 3곳 RFP 응답 대기 중
- [ ] RDS(PostgreSQL) 마이그레이션 (W3 예정)
- [ ] JWT 인증 구현 (W4 예정)
- [ ] 구독 플랜 접근 제어 (W5 예정)
- [ ] 관리자 페이지: SVS 업로드 시 MPP 자동 읽기 미구현 (현재 수동 입력)

---

## 로드맵 (현행)

| 주차 | 기간 | 핵심 작업 |
|------|------|-----------|
| W2 | 5/12~16 | 법인설립 + 도메인 + RFP 발송 |
| W3 | 5/19~23 | RDS 마이그레이션 + JWT 설계 |
| W4 | 5/26~30 | 중국 계약 + JWT 인증 구현 |
| W5 | 6/2~6 | 슬라이드 업로드 + 홍보자료 배포 + 구독 접근제어 |
| W6 | 6/9~20 | 베타 오픈 + 초창패 추경 대응 |

**핵심 목표**: 9월 가을학기 2~3개교 구독 확보 (첫 매출)

---

## 영업 네트워크

| 연결 | 역할 |
|------|------|
| 경희대 의료원 신경외과 교수 (군대 고참) | 의향서 + 해부학/병리학 교수 소개 |
| 연세대 소아과 교수 (교회 형님) | 연대 내 타겟 교수 소개 루트 |
| 단국대 서민 교수 (기생충학, 부친 지인) | 의향서 + 콘텐츠 파트너십 가능성 |
| 보람바이오텍 지방의대 납품망 교수들 | 의향서 + 실제 구독 타겟 |

**의향서 목표**: 3~5개 (초창패 심사 보완용)

---

## 개발 원칙

- 코딩은 AI(Claude) 활용, 시스템 원리 파악 방식
- W1~W2: 단일 파일 복붙 방식
- W3~: Claude Code 전환 권장 (다중 파일 동시 수정 시)
- 새 기능 추가 시 이 파일(CLAUDE.md) 업데이트 필수

---

## 연락처 / 계정

- 법인 이메일: boram@atlaslab.co.kr
- S3 리전: ap-northeast-2
- Render 환경변수: `ANTHROPIC_API_KEY` 등록 완료
