# portal.html 사이드바 셸 + 구독 플랜·이용 리포트 디자인 이식 보고

> 2026-06-13 · 범위: `templates/portal.html`(시각만) + `server_render.py` /portal 라우트(is_teacher 인자 1개). 기준=`portal_plans_report_design.html`. **기능·데이터·fetch·함수·이벤트·Jinja 100% 보존**(`<script>` 블록 HEAD와 byte-identical).

## 변경 요약
- **server_render.py /portal**: render 인자에 `is_teacher` 1개 추가(아래 b).
- **portal.html**: ① 사이드바 마크업 교체(디자인 셸) ② #tab-plan 마크업(page-title만·디자인 카드) ③ #tab-report 마크업(page-title만·디자인 KPI/카드) ④ 디자인 `<style>` 블록 추가(셸+플랜+리포트, #tab-plan/#tab-report 스코프 격리). **명단 탭 본문(#tab-roster)·전체 `<script>` 무변경.**

## (a) '학습 홈' 노출 조건 = `{% if has_slides %}` — has_slides 적합함
- `/portal` 라우트(server_render.py L937): **`has_slides = g.subject_code is not None`**. 즉 **이 사용자 본인의 과목 구독(콘텐츠 접근권) 보유 여부**다. 주석도 "겸직(subject_code 보유)만 콘텐츠 접근권 → 노출, 순수 admin-only(subject NULL=좌석0·비소비)는 숨김".
- → **'기관에 배포 슬라이드 존재'가 아니라 '이 사용자의 슬라이드 접근 권한'을 정확히 반영**. 따라서 학습 홈 게이트로 적합. 행정직원(subject 없음)=미노출. **새 판정 신설 없이 기존 has_slides 재사용**(§0).
- 렌더 검증: has_slides=False → '학습 홈' 미노출, has_slides=True → 노출.

## (b) is_teacher를 portal 라우트에 넘긴 방식 = home(L865)과 동일 로직
- `/portal` 라우트의 기존 conn 블록(inst_name 조회) 안에 **단일 조회 추가**: `SELECT position FROM users WHERE id=%s` → `user_position`.
- `is_teacher = user_position in ('교수','조교')` 계산 후 `render_template('portal.html', ..., is_teacher=is_teacher)`.
- **/home(L865)의 `is_teacher = user_position in ('교수','조교')`와 글자까지 동일 기준(users.position)**. `_course_position`(수업 소유/위임, course 단위)이 아니라 **users.position**(home과 동일)을 씀 — role 단독·새 판정 없음(§0). 추가 커넥션 없이 기존 conn 재사용.
- 사이드바 '수업 관리'(→/teacher/courses) = `{% if is_teacher %}`. 렌더 검증: is_teacher=True→노출, False→미노출.
- **사용자별 결과(렌더 확인)**: 행정직원(subject·position 없음)=학습홈·수업관리 **둘 다 미노출** / admin겸직 교수·조교=**둘 다 노출** / admin겸직 학생=학습 홈만.

## (c) renderPlans/renderReport DOM 타겟 id 보존 방식 = 마크업 id 유지 + 출력 클래스 CSS 스타일링
**렌더 함수는 한 글자도 안 고침**(18종 + esc byte-identical, `<script>` 전체 IDENTICAL). 함수가 `.innerHTML`/`textContent`로 찾는 요소 id·삽입 컨테이너를 새 마크업에서 그대로 유지하고, **함수가 emit하는 클래스를 CSS로만 디자인 외관 부여**(명단 탭과 동일 전략):
- **renderPlans** → `#plan-list`에 `.plan-card`(.pc-main>.pc-name+.pc-meta, .pc-seat>.seatbar, statusBadge=.badge ok|exp|up|wait) innerHTML. → `#tab-plan .plan-card`를 `.sub-card` 외관(flex·큰 과목명·sky-wash 배지·우측 30px Montserrat 좌석수·게이지)으로 CSS 스타일. **id `plan-list` 유지**.
- **renderPlanSlides** → `#slide-tbody` innerHTML(5칸 tr + `<a class="act ghost">열람</a>`), `#slide-count` textContent, `#slide-search` 읽기. → 표·`.act`·`.search`·`.count` CSS 스타일. **id slide-panel/slide-panel-title/btn-xlsx/btn-csv/slide-search/slide-count/slide-tbody 전부 유지**(btn-xlsx/csv는 JS가 addEventListener로 바인딩).
- **renderReport** → `#k-reg·k-reg-sub·k-views·k-util·k-ai·k-avg·k-active` textContent, `#member-bars·views-chart·rank-list·ai-chart` innerHTML(.barrow/.rankrow). → KPI 카드(.kpi/.k-label/.k-val/.k-sub) 재구조화하되 **id 스팬 유지**, .barrow→460px(활성=navy, 나머지=`:not(:first-child)` mut), 하단 3섹션 .sec-narrow 560px. **id 24종 전수 보존(grep 1건씩 확인)**.
- 탭 전환 `switchTab`은 `.sidebar .nav-item[data-tab]`·`.tab-panel.active`·`#tab-<tab>` 그대로 — 새 사이드바 nav-item에 `data-tab`+`onclick="switchTab()"` 유지, 패널 id(#tab-roster/plan/report) 불변.

## 변경 1 — 사이드바 셸(세 탭 공통)
- 로고: **`<img src="/static/SlideAtlas_Navy_Hor_small.png">`**(height 28px, 정확히 이 경로) — 깨진 텍스트 "SLIDE" 제거.
- 기관 식별 2줄 위계: `.org-k` "기관 포털"(sky톤 대문자 letter-spacing) + `.org-n` **{{ institution_name }}**(흰색 14.5px/700). 기존 "기관 포털 · TEST" 한 줄 흐림 제거.
- **sticky 고정**: `.sidebar{position:sticky;top:0;height:100vh}` + `.main{overflow-x:hidden;overflow-y:visible}` → **메인(body)만 스크롤**, 사이드바 고정.
- nav 3항목(명단/플랜/리포트, data-tab·active 유지). 기존 nav '슬라이드 열람' 제거.
- `.nav-foot`(로그아웃 위 분리): 학습 홈(has_slides)·수업 관리(is_teacher)·로그아웃(doLogout, id=btn-logout 유지).

## 변경 2·3 — 플랜·리포트 패널(시각만)
- 둘 다 긴 부제(page-desc) 제거, page-title만.
- 플랜: 구독 요약(.sub-card 외관), 배포 슬라이드 카드(헤더+검색+표, 버튼 .btn).
- 리포트: 설정 한 줄(select+seg+엑셀·PDF), KPI 4카드(흰 카드·Montserrat 32px), 활동 막대 460px(활성 navy/나머지 mut), 하단 3섹션 560px 가둠, "데이터 없음" empty 유지.

## 토큰/검증
- lms.css 변수만(navy/sky/sky-deep/beige + --color-text-*/--color-border-* → #tab-plan/#tab-report 로컬 별칭). 사이드바 muted 텍스트는 `rgba(255,255,255,..)`(흰색+투명도, 기존 lms 사이드바와 동일 계열) — `--navy-soft`(lms=다크네이비 hover) 의미 충돌 회피 위해 디자인의 #9AA8C2 미사용.
- Tabler 아이콘 lms 서브셋만 사용(없는 글리프 대체: chart-line→chart-bar, home→microscope, school→users-group, printer→file-type-pdf).
- **초록(#2A9D8F·#1D9E75·#5DCAA5)·#1a2238·system-ui 0건.**

| 검증 | 결과 |
|------|------|
| 18 함수 + esc + 전체 `<script>` vs HEAD | **byte-IDENTICAL** |
| DOM 타겟 id 24종 | 전수 보존(1건씩) |
| fetch 9종·data-tab 3·{{institution_name}}·{{has_slides}} | present |
| Navy 로고 경로 | 정확히 1건 |
| 초록/#1a2238/system-ui | 0 |
| JS 문법 / Jinja parse / server_render.py 구문 | OK / OK / OK |
| 사이드바 sticky·org 2줄·학습홈/수업관리 게이트 | 렌더 확인 OK |

## ⚠ 참고 (지시 충돌 처리)
- **{{ institution_id }}**: 변경 1.2가 "기관 포털 · TEST(=institution_id) 한 줄 제거"를 명시 → 사이드바에서 institution_id 표시 제거(2줄 위계는 institution_name). 결과적으로 템플릿에서 {{ institution_id }} 참조 0건. **라우트는 institution_id를 계속 render 인자로 전달(미사용·무해)** — 절대불변의 "변수 그대로 사용"은 변경 1.2(구체 지시)가 우선이라 표시만 제거. 다시 노출 원하시면 알려주세요.
- 명단 탭은 셸(사이드바·.main 패딩·sticky) 변경만 공유받고 본문 #tab-roster 구조·기능 무변경.

> 실측: CEO EC2 배포 후 /portal 3탭 전환·구독 요약/배포 슬라이드 표·KPI·활동막대(460)/하단(560)·사이드바 sticky·학습홈/수업관리 노출 확인(§20).
