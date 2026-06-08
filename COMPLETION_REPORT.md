# COMPLETION_REPORT — 학생 공통 셸 + 로그인 후 홈(/home) 1단계 (2026-06-08)

작업일: 2026-06-08 | 작업자: Lead Developer | 기준: CLAUDE.md §8·§21
상태: **구현·pytest 회귀 0·내부 QA 완료.** 접근 게이트·인증 로직 불변이라 외부검증 불요(지시).

## 1. 범위
viewer 사용자가 로그인하면 도착할 새 홈(`/home`)을 신설한다. 수업 탭/전체 탭 2탭 셸 + 학생 공통 헤더(로고·탭·마이페이지 링크·로그아웃). 전체 탭은 기존 슬라이드 그리드 재활용, 수업 탭은 빈 상태 placeholder(데이터는 3단계).

**불변 보장**: `_slide_access_allowed`(server_render.py:431)·`_visible_slides`(:472)·auth 인증 로직 **무수정** — 슬라이드 접근 정책은 이번에 손대지 않음. 전체 탭 목록은 기존 `_visible_slides(load_slides())`를 그대로 호출(새 필터 로직 없음).

## 2. 변경/신규 파일
| 파일 | 종류 | 내용 |
|------|------|------|
| `server_render.py` | 수정 | `/slides` 라우트를 `redirect('/home')`로 교체 + `GET /home` 라우트 신설(`@page_login_required`) |
| `templates/home.html` | **신규** | 학생 공통 셸(헤더+2탭). standalone, slides.html 카드 마크업·스타일 이식 |
| `static/js/login_terminal.js` | 수정 | 로그인 후 목적지 기본값 `/slides`→`/home`(admin-only→`/portal` 유지) |
| `templates/viewer.html` | 수정 | 뷰어 nav "← 목록"(`/slides`)→"← 홈"(`/home`) |
| `templates/slides.html` | **잔존(미삭제)** | 진입은 redirect로만, 파일은 보존(지시) |

## 3. 새 라우트
- `GET /home` (`@page_login_required`):
  - `g.role=='admin' AND g.subject_code IS NULL`(순수 admin-only, 콘텐츠 비소비자) → `redirect('/portal')`.
  - 그 외(viewer·겸직) → `home.html`. 전체 탭 슬라이드 = `_visible_slides(load_slides())`(불변). 표시명(`institution_rosters.name`)·과목명(`subject_codes.name_ko`)·`is_admin`·계통(organ) 옵션 전달.
- `GET /slides` (`@page_login_required`): 본문을 `redirect('/home')`로 교체(북마크·`?next=/slides` 보존).

> 데코레이터는 지시문의 `@login_required`(JSON 401) 대신 **`@page_login_required`**(인증 실패 시 `/`로 redirect)를 사용 — `/home`은 HTML 페이지이며 기존 `/slides`·`/portal`과 동일 컨벤션. JSON 401은 페이지에 부적합.

## 4. 로그인 목적지 before/after
| 사용자 | before | after |
|--------|--------|-------|
| viewer(일반) | `/slides` | **`/home`** |
| 겸직 admin(subject_code 보유) | `/slides` | **`/home`** |
| 순수 admin-only(subject_code 없음) | `/portal` | `/portal` (유지) |
| `?next=…` 지정 | next(없으면 `/slides`) | next(없으면 **`/home`**) |

(`login_terminal.js`: `_nextUrl` 기본값·fallback 2곳 `/slides`→`/home`. `_postLoginDest`는 admin-only만 `/portal` 분기, 나머지 `_nextUrl`.)

## 5. home.html 구성
- **공통 학생 헤더**: 로고+Beta 배지 / 탭 토글 `[수업 | 전체]` / 우측 = (겸직 admin이면)관리자 포털 + **마이페이지**(`href=/mypage`, 4단계 구현 예정 — 링크만) + **로그아웃** 버튼.
- **전체 탭**(기본): slides.html 카드 그리드 마크업·스타일 이식. 제목/ID 클라이언트 검색창 + 계통(organ) 드롭다운 필터만 동작화(`data-search`·`data-organ` 속성 + `applyFilter()` 숨김 토글, 실시간 카운트). 과한 사이드바 필터 생략.
- **수업 탭**: 빈 상태 UI("아직 등록된 수업이 없습니다" + 안내문). 정적(데이터 3단계).
- `interceptor.js` 로드(향후 fetch 대비, CSRF 자동 주입). `esc()` XSS 헬퍼는 portal.html 정의 인라인 복사(현재 서버 렌더라 미사용, 3단계 수업 fetch 대비).
- **로그아웃**: `fetch('/api/auth/logout', {method:'POST'})`(interceptor가 CSRF 자동 주입) → 성공/실패 무관 `/login` 이동.

## 6. 검증 (내부 QA)
- **pytest 205 passed, 회귀 0**(인증·슬라이드·포털 P1~P3 전수). 접근/인증 로직 불변 → 외부검증 불요(지시).
- `server_render.py` AST 파싱 OK / `home.html` Jinja 파싱 OK.
- 멀티테넌시: scope는 `g`(로그인 사용자 기관·과목)만 사용, 외부 입력으로 슬라이드 노출 안 넓힘. 전체 탭은 `_visible_slides` 결과만 렌더.

## 7. 한계·미완 (숨기지 않음)
- **마이페이지**: 링크(`/mypage`)만 — 라우트·화면은 4단계.
- **수업 탭**: 정적 빈 상태 — courses 연동은 3단계.
- **portal.html "슬라이드 보기 →"** 링크는 여전히 `/slides`(→`/home` redirect로 바운스). 동작 정상이라 이번 범위 밖으로 두되, 향후 `/home` 직접 링크로 정리 가능.
- **서버측 viewer redirect**(`/viewer/<id>`의 slide-not-found·미허용 시 `redirect('/slides')`)는 그대로 — `/slides`→`/home` 바운스로 동작 정상이라 미수정.
- CLAUDE.md 미수정(지시 — §21·D27 일괄 갱신은 묶음 종료 시).

## 8. 배포 / 남은 게이트
- 커밋·push origin/main까지 수행(지시). **EC2 git pull + 재기동은 CEO**(신규 마이그레이션 없음, 인프라 변경 없음).
