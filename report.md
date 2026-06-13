# home.html 전면 정리 보고서 — 브랜드 navy/sky 전환 + 사이드바 필터 + /slides 은퇴

> 작성: 2026-06-13 · 작업: claude · **백엔드(server_render.py) 무수정 — templates만 수정**
> 범위: `templates/home.html`(전면 재스킨·레이아웃), `templates/base.html`·`templates/portal.html`(링크 1줄씩)

## 변경 요약 (git diff --stat)
```
templates/base.html     |   2 +-
templates/home.html     | 285 +++++++++++++++++----------------
templates/portal.html   |   2 +-
3 files changed, 193 insertions(+), 96 deletions(-)
```

## 변경 1 — 디자인 토큰 통일 (초록 → navy/sky)
- `<head>`: DM Mono `<link>` + SUIT `@import` 제거 → **Montserrat + Noto Sans KR** Google Fonts + `preconnect` 추가, `/static/css/lms.css` 링크 추가.
- `<style>`의 모든 색을 lms.css 변수로 치환:
  · 초록(#2A9D8F·#1D9E75·#5DCAA5·rgba(42,157,143,*)·rgba(29,158,117,*)) → `var(--sky)`/`var(--sky-deep)` (강조·링크·badge·hover 보더)
  · 배경 #F7F4EF → `var(--beige)`, 카드 흰색 → `var(--color-background-primary)`
  · 텍스트 #0F1F3D/#6B6560/#9B9490 → `--color-text-primary`/`secondary`/`tertiary`
  · 경계 #E5E0D8/#D8D3CA → `--color-border-tertiary`/`--color-border-secondary`
  · nav·footer 배경 navy 유지 = `var(--navy)`
- 폰트: body=`var(--font-sans)`, ID/뱃지/배율=`var(--font-mono)`, 제목=`var(--font-display)`(Montserrat).
- **검증: 초록 헥스/rgba·DM Mono·SUIT·#F7F4EF grep 0건.**

## 변경 2 — 전체 탭(#tab-all) 사이드바형 2단 레이아웃
- `.all-layout`(grid 220px + 1fr) = 좌측 `.filter-sidebar`(sticky) + 우측 `.all-main`(검색 + 결과 수 + 그리드).
- 사이드바 두 그룹:
  · **계통(System)**: `{{ organs }}`(서버 정식 계통 목록)로 체크박스 server-render.
  · **염색(Stain)**: 렌더된 카드 `data-stain` 고유값에서 **DOM 기반 동적 생성**(서버 무변경, `buildStainFilters()`, textContent로 XSS 방어).
  · 각 그룹 다중 선택, 그룹 내 OR·그룹 간 AND·검색어와 AND. 빈 그룹은 전체 통과.
- 카드 그리드 `.slides-grid` 반응형 `minmax(220px,1fr)` 유지, lms.css 톤(흰 카드 + `--color-border-tertiary` 보더 + hover 시 `--sky` 보더·상승).
- 카드에 `data-stain="{{ s.get('stain','') }}"` 추가(`data-organ`·`data-search` 유지).
- 모바일(<720px): 사이드바 단일 컬럼·static.

## 변경 3 — 필터 JS 확장
- 상단 계통 드롭다운(`#organ-select`) 제거. `applyFilter()`를 사이드바 체크박스 기반으로 재작성(검색어 + 계통 OR + 염색 OR, AND 결합).
- `checkedValues(group)`·`fillOrganCounts()`(계통 개수)·`buildStainFilters()`(염색 생성) 추가. `DOMContentLoaded`에서 개수 채움 + 염색 목록 생성.
- 표시 개수(`#visible-count`)·결과 0건 `#no-result` 안내 유지. 체크박스 onchange/검색창 oninput → applyFilter.

## 변경 4 — 카드 썸네일 통일
- stain별 분홍/파랑 그라데이션(thumb-he 등) 제거 → lms.css `.fav-thumb`/`.placed-thumb` 패턴(navy-tint→border 그라데이션 + 가운데 `<i class="ti ti-microscope">`)으로 교체(course/mypage 카드와 동일).
- 염색 구분은 썸네일 색이 아니라 **stain 뱃지**: `stain-badge` + `stain-he`/`stain-pas`/`stain-mt`(매핑: he→he, pas→pas, masson·silver→mt). "AVAILABLE / WSI·40×" 라벨 유지, 색만 브랜드로.

## 변경 5 — /slides 은퇴 (링크 정리만)
- `base.html`: '슬라이드 열람' → `navRequireLogin(event, '/home', '/login?next=/home')`.
- `portal.html`: 헤더 '슬라이드 보기 →' `href="/slides"` → `/home`.
- slides.html 파일·/slides 라우트는 미수정(링크만 끊음).
- **검증: base/portal에 `/slides` 링크 0건**(`/portal/api/plans/slides`는 별개 API라 제외).

## 절대 불변 확인 (전수 grep + 렌더)
- `showTab`/`loadCourseTab`/`buildChips`/`renderCourseLists`/`courseCardHTML`/`doLogout`/`esc()` **JS 본문 그대로**(applyFilter만 사양대로 재작성, 헬퍼 신규 추가).
- fetch 경로(`/api/courses/enrolled`·`/api/courses/available`·`/api/auth/logout`)·interceptor.js 로드 유지.
- 수업 탭(#tab-course) 마크업·동작 그대로(색/폰트만 스킨).
- Jinja 변수/블록 전부 보존: `{{ display_name }}`·`{{ subject_name }}`·`{{ is_teacher }}`·`{{ is_admin }}`·`{{ total }}`·`{{ organs }}`·`{% for s in slides %}`·`/viewer/{{ s.id }}`·`stain_class`·교수/admin 버튼 분기.
- nav(navy)·탭 토글 동작 유지.

## 검증 결과
| 항목 | 결과 |
|------|------|
| 초록 헥스/rgba grep (home.html) | **0건** |
| base/portal `/slides` 링크 | **0건** |
| Jinja parse (home/base/portal) | **OK** |
| 렌더 스모크(샘플 3~4종) | data-stain·stain-badge·organ 체크박스·microscope 정상, green leftover 0 |
| 뱃지 매핑 | H&E→he, PAS→pas, Masson→mt, Silver→mt ✓ |
| 잠금 함수/fetch/Jinja 변수 | 전수 present ✓ |

> 남은 확인(브라우저 실측 권장): 전체 탭에서 계통·염색 체크박스가 그리드를 실제로 거르고 검색과 동시 작동·결과 수 갱신, 수업 탭 정상, /home↔/viewer 이동. (정적 렌더·grep·Jinja 파스까지 통과, 실서버 기동 미수행.)
