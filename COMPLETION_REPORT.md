# COMPLETION_REPORT — LMS 3단계-A 교수/조교 프론트(4화면) + 표시용 백엔드 (2026-06-11)

작업일: 2026-06-11 | 작업자: Lead Developer(Claude) | 기준: CLAUDE.md §21·§8·§9·§15-7
상태: **구현 완료 · 전수 pytest 258 passed(240→258, 회귀 0) · 보호 함수 무수정.**

## 1. 범위 / 불변
교수·조교 LMS 프론트 4화면(수업 목록·편집·조교·대시보드) + 화면 구동에 필요한 **읽기전용 표시 라우트만** 구현.
학생 홈·수업상세·마이페이지는 범위 밖(차기 세션).

**절대 무수정(git diff로 확인)**: `_slide_access_allowed`·`_visible_slides`·auth 인증·2단계 LMS 권한 헬퍼
(`_course_owner_or_assistant`·`_course_position`)·기존 course API 로직. server_render.py 변경 = **2661행 단일 추가 블록(+184, 삭제 0)**. CLAUDE.md·`.sql` 미수정.

## 2. 신규/변경 파일
| 파일 | 종류 | 내용 |
|------|------|------|
| `static/css/lms.css` | 신규 | 목업 디자인 시스템 추출·조립(Tabler 인라인 폰트·navy/sky·Noto Sans KR/Montserrat·모노폰트 sans 매핑). 4템플릿 공유 |
| `templates/teacher_courses.html` | 신규 | A-1 교수 수업 목록 |
| `templates/course_edit.html` | 신규 | A-2 수업 편집(주차 구성) |
| `templates/assistants.html` | 신규 | A-3 조교 지정 |
| `templates/course_dashboard.html` | 신규 | A-4 수업 대시보드 |
| `server_render.py` | 추가만 | 페이지 라우트 4 + 표시용 읽기 API 3 + 헬퍼 2 |
| `tests/test_lms_teacher_pages.py` | 신규 | 페이지/표시API 권한 가드 18건 |

## 3. 새 라우트 표
| 라우트 | 메서드 | 가드(재사용 헬퍼) | 용도 |
|--------|--------|-------------------|------|
| `/teacher/courses` | GET(page) | `_course_position`∈{교수,조교} 아니면 /home redirect | A-1 목록 셸 |
| `/teacher/course/<cid>` | GET(page) | `_page_course_role`(=`_course_owner_or_assistant`) None→403 | A-2 편집 셸 |
| `/teacher/course/<cid>/assistants` | GET(page) | 위 + role=='professor' 아니면 403 | A-3 조교 셸 |
| `/teacher/course/<cid>/dashboard` | GET(page) | `_page_course_role` None→403 | A-4 대시보드 셸 |
| `/api/courses/<cid>/available-slides` | GET | `_course_owner_or_assistant` + `_visible_slides` | 배치 모달 후보(메타만) |
| `/api/courses/<cid>/assistants` | GET | `_course_owner_or_assistant` | 현재 조교 목록 |
| `/api/courses/<cid>/assistant-candidates` | GET | 위 + professor | 조교 후보 검색(scope=g.*) |

> 신규 라우트는 **새 권한/접근 판정 로직을 만들지 않는다** — 전부 기존 헬퍼 재사용. 슬라이드 배치는
> 기존 `POST /weeks/<wid>/slides`가 `_slide_access_allowed`로 재검증(§8). available-slides는 표시 후보일 뿐
> 접근을 부여하지 않으며 타일·토큰을 발급하지 않는다(카탈로그 메타 id·title_ko·organ·stain만).

## 4. 화면별 — 호출한 기존 API
- **A-1**: `GET /api/courses/mine`(카드), `POST /api/courses`(개설). 개설 버튼=is_professor만.
- **A-2**: `GET /api/courses/<cid>`(주차+deployed 배치), `POST/DELETE /weeks`, `POST/DELETE /weeks/<wid>/slides`, 신규 `GET /available-slides`(모달). 빈 주차 사유=주차 추가 시 empty_reason.
- **A-3**: 신규 `GET /assistants`·`GET /assistant-candidates?q=`, 기존 `POST /assistants`·`DELETE /assistants/<uid>`.
- **A-4**: 기존 `GET /stats`(익명 집계 KPI), `GET /roster`(명단). `GET /api/courses/<cid>`(제목·학기).

## 5. §15-7 개인정보 — 대시보드 분리(절대 원칙)
대시보드는 **익명 집계(KPI·열람률)** 와 **등록 명단(이름·이메일·등록일)** 을 화면에서 물리적으로 분리(목업대로).
명단 테이블에는 접속·열람 등 활동 컬럼이 없고(기존 `/roster` 응답에도 없음), 활동은 익명 집계로만 노출.
이름과 활동을 같은 행에 절대 섞지 않음.

## 6. 검증
- 전수 pytest **258 passed**(기준 240 + 신규 18, 회귀 0).
- 신규 가드 테스트: 학생→/teacher/courses redirect(/home), 비편집자→/teacher/course/* 403, 위임조교→조교화면 403,
  타기관 수업 403, available-slides/candidates 비권한 403, candidates scope=g.* 단언, 응답 필드 누수 없음.
- server_render.py diff = 단일 추가 블록, 보호 def 변경 0(grep 확인).

## 7. 미해결 / 차기
- **주차 제목·빈주차 사유 인라인 수정**: PUT weeks 엔드포인트 부재 → 읽기전용 표시(제목은 생성 시 캡처). 새 mutate API는 3단계-A 범위 밖(차기).
- **대시보드 주차별 열람률**: 기존 `/stats`는 전체 집계만 제공 → 전체 배치 열람률 1개 바로 표시(주차별 분해 미제공, /stats 무수정 원칙).
- **top-bar 로고**: 지시대로 `SlideAtlas_Navy_Hor_small.png` 사용 — 네이비 톱바 위 네이비 로고라 대비 확인 필요(필요 시 White 변형으로 교체, 1줄 변경).
- **커밋 구조**: 4화면이 공유 CSS·공유 백엔드 헬퍼로 상호의존 → 단계별 4커밋은 누적(stacked)이며 최종 tip(A-4)에서 전수 258 green.
- CLAUDE.md 미수정(묶음 끝 일괄 반영 예정).
