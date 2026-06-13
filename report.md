# portal.html 디자인 토큰 전환 보고서 — system-ui/#1a2238 → 브랜드 navy/sky

> 작성: 2026-06-13 · 작업: claude · **레이아웃·HTML·JS·로직 무수정 — `<head>`(색·폰트·컴포넌트 스킨)만 교체**
> 범위: `templates/portal.html` 1파일. 라이브 상단탭 레이아웃 유지(목업 사이드바로 되돌리지 않음).

## 변경 요약 (git diff --stat)
```
templates/portal.html | 96 +++++++++++++++++------------------
1 file changed, 52 insertions(+), 44 deletions(-)
```
- **모든 diff 헝크가 `<head>` 영역(7~89행)에 한정.** `<body>`~`</html>`(마크업+`<script>` 전체)는 **HEAD와 바이트 동일**(`diff` 검증 IDENTICAL).

## 변경 내용
1. **`<head>`**: `lms.css` 링크 + Montserrat·Noto Sans KR Google Fonts(+preconnect 2줄) 추가. 인라인 `<style>`은 공통 리셋/토큰/폰트(lms.css 제공)는 재정의하지 않고 **portal 고유 컴포넌트 스타일만** 남겨 색·폰트만 토큰으로 치환.
2. **색 치환** (초록·#1a2238·system-ui 완전 제거):
   - `#1a2238` → `var(--navy)`, hover `#2a3656` → `var(--navy-soft)`
   - 배경 `#f5f6f8` → `var(--beige)`, 카드 흰색 → `var(--color-background-primary)`
   - 텍스트 `#1a2238/#5a6478/#7a8294` → `--color-text-primary/secondary/tertiary`
   - 경계 `#e3e6ec/#cdd2dc/#eef0f4` → `--color-border-tertiary/secondary`
   - 배지: `.ok`→sky-tint/sky-deep(active), `.wait`→`#F1EFE8/#5F5E5A`(pending), `.exp`→`--color-background-danger/--color-text-danger`, `.up`→`#E6F1FB/#0C447C`(student blue) — 모두 lms.css 기존 값
   - 좌석바: 정상 `#1c7a4d`(초록) → `var(--sky)`, 초과 `.warn` `#c0392b` → `var(--color-text-danger)`
   - 차트 막대 `#1a2238` → `var(--navy)`, 게이지/좌석 정상 → `var(--sky)`
   - 탭 active 밑줄 → `var(--sky)`(글자=`var(--navy)`)
3. **폰트**: body `system-ui`(BlinkMacSystemFont…) → `var(--font-sans)`. KPI 숫자 `.k-val` → `var(--font-display)`(Montserrat). 입력/버튼/탭/세그먼트에 `font-family:var(--font-sans)` 명시.
4. **버튼**: `button.act`=navy/white(hover navy-soft), `button.ghost`=흰 배경+border-secondary(hover bg-secondary 추가). 클래스명·구조는 그대로 두고 색만 매핑(HTML 무수정 원칙 — lms `.btn` 클래스로 교체하면 마크업 변경이라 동일 톤 재현 방식 채택).
5. 추가 보강(스킨 한정): `input:focus/select:focus` 보더 `var(--sky)`, `button.ghost:hover`.

## 충돌 회피 (중요)
- lms.css가 **bare `table/th/td/body`** 를 스타일(`td{padding:0}` 등). 인라인 `<style>`이 lms.css `<link>` **뒤**에 오므로 동일 specificity에서 portal 규칙이 승리 → portal의 표/카드/배지 규칙을 **삭제하지 않고 recolor만** 해 레이아웃 회귀(예: td padding 0 됨)를 방지.
- portal `#toast`(ID)는 lms `.toast`(class)와 무충돌. `select` bare는 lms가 미스타일이라 충돌 없음.

## 절대 불변 확인 (전수 검증)
- `<body>`+`<script>` **HEAD와 바이트 동일** (`diff` IDENTICAL).
- 잠금 함수 18종(loadRoster·renderMembers·renderAdmins·addMember·delMember·uploadMembers·downloadTemplate·onWorkSubjectChange·fillSubjectSelects·loadPlans·renderPlans·selectPlanSubject·renderPlanSlides·exportSlides·loadReport·renderReport·doLogout·esc) 전수 present.
- fetch 경로 전수 present(/portal/api/roster GET·POST·DELETE·/upload·/template, /plans·/plans/slides·/export, /report·/report/export, /api/auth/logout).
- `data-tab="roster|plan|report"`·member-tbody 위임·work-subject 컨텍스트·toast 동작 그대로.
- Jinja `{{ institution_name }}`·`{{ institution_id }}`·`{% if has_slides %}` 보존.

## 검증 결과
| 항목 | 결과 |
|------|------|
| 초록·#1a2238·system-ui·옛 헥스 grep | **0건** |
| lms.css + 폰트 링크 | present(5 매치) |
| body/script vs HEAD | **IDENTICAL** |
| 잠금 함수·fetch·data-tab·Jinja | 전수 present |
| Jinja parse | OK |
| 렌더 스모크(샘플 vars) | len 31310, navy/sky 토큰 적용, green leftover 0, has_slides 블록·탭 3개 정상 |

> 남은 확인(브라우저 실측 권장): 3개 탭 전환, 명단 추가/삭제(tbody 위임), 과목 컨텍스트(work-subject), 플랜·리포트 지연 로드. (정적 렌더·grep·Jinja 파스·바이트 diff까지 통과, 실서버 기동 미수행.)
