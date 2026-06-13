# portal.html 목업 기준 전면 재제작 보고서 — 좌측 사이드바 셸 + 라이브 기능 100% 보존

> 작성: 2026-06-13 · 작업: claude · 범위: `templates/portal.html` 1파일
> 원칙: docs/mockups/institution_portal.html의 **레이아웃·컴포넌트(껍데기)** 채택 + 현 portal.html의 **기능·fetch·동선(알맹이) 100% 보존**. 목업 더미 JS(하드코딩 members/PLANS/RANKS·prompt 관리자 추가·simulateUpload 등) 전량 폐기.

## 레이아웃 (목업 채택)
- **상단 탭 → 좌측 네이비 사이드바**(`.portal`/`.sidebar`/`.nav-item`, lms.css 기존 클래스).
  · 사이드바 항목: 명단 관리 / 구독 플랜 / 이용 리포트 (3개) + 로고·「기관 포털 · {{ institution_id }}」.
  · `{% if has_slides %}` "슬라이드 열람"(→/home) nav-item로 has_slides 변수·동선 보존.
  · `.nav-bottom` = **로그아웃만**(doLogout). **'내 계정' 메뉴 없음**(포털 3탭 완결·D27).
- 메인: 목업 `.page-title`/`.page-desc` + `.stats-row`(통계 카드 3) + `.section-card`(card-header/card-title) 구조.
- 탭 전환 = nav-item 클릭 → `switchTab()`로 `.tab-panel.active` 토글(목업 패턴) + 플랜/리포트 1회 지연 로드.

## 기능 = 라이브 100% 보존 (검증)
- **핵심 데이터/렌더 함수 14종 HEAD와 바이트 IDENTICAL**: renderMembers·renderAdmins·addMember·delMember·uploadMembers·downloadTemplate·onWorkSubjectChange·fillSubjectSelects·renderPlans·selectPlanSubject·renderPlanSlides·exportSlides·loadReport·renderReport.
- loadRoster·loadPlans는 **additive 1줄(`renderRosterStats();`)만** 추가(fetch·판정·shape 불변).
- fetch 경로 전수 보존: /portal/api/roster(GET·POST·DELETE)·/upload·/template, /plans·/plans/slides·/export, /report·/report/export, /api/auth/logout.
- 보안 보존: member-tbody **이벤트 위임**(인라인 onclick에 email 미보간·data-* 사용), esc() XSS, interceptor.js(CSRF 자동), id-bound 리스너 6종(plan-list·btn-xlsx·btn-csv·rep-period·rep-xlsx·member-tbody).
- Jinja: {{ institution_name }}·{{ institution_id }}·{% if has_slides %} 보존.

## CLAUDE.md 최신 반영
1. **과목 컨텍스트화(§9 v3.23)**: 행별 과목 드롭다운 없음. 상단 **work-subject** 컨트롤로 추가/업로드/양식다운로드 적용, 추가 입력 3칸(이름·지위·이메일), 명단 표 과목은 **표시만**.
2. **양식 다운로드(§9 v3.22)**: 실제 GET /portal/api/roster/template?format=xlsx&subject_code=<선택과목>(downloadTemplate), 미선택 시 안내 토스트.
3. **로그아웃(§21 v3.23)**: 실제 doLogout(POST /api/auth/logout → /login).
4. **기관 관리자 읽기 전용**: 목업 관리자 추가(prompt)/삭제(슬롯) **전부 제거**(addAdmin·openAdminDelModal·admin-slot 0건). renderAdmins 표 + "추가/변경은 SlideAtlas 운영팀 문의" 안내만.
5. **삭제 = 과목 단위**: delMember 문구·동작 그대로("과목 등록 제거 → 좌석 1석 반환·접근 차단", confirm 유지).
6. **데이터 전량 라이브 API**: 하드코딩 배열(const members/PLANS/RANKS·let members) 0건 — 전부 fetch 응답 렌더.
7. **통계 카드(stats-row) 수치 = 라이브 계산**: 새 `renderRosterStats()`가 지위별·인증=MEMBERS, 좌석 게이지=PLANS(과목별 used/max·소진율·초과 시 danger), 만료 D-day=PLANS(가장 가까운 subscription_end·access_open_date→end 경과 게이지). 데이터 없으면 graceful("불러오는 중…"/"구독 정보 없음"). 통계용으로 init에서 loadPlans 1회 eager 로드(planLoaded 가드 — 탭 전환 시 재요청 없음).

## 토큰/폰트
- lms.css 링크 + Montserrat·Noto Sans KR(+preconnect). 셸·컴포넌트(.portal/.sidebar/.nav-item/.section-card/.stats-row/.badge-*/.btn/.table/.role-select 등)는 lms.css 사용.
- 인라인 `<style>`은 **라이브 렌더 함수가 emit하는 클래스 전용**(badge ok/wait/exp/up·del·muted·plan-card/pc-*·seatbar·seg·kpi/k-*·barrow·rankrow·act/ghost) — lms.css에 없어 토큰으로 정의. 초록·#1a2238·system-ui 0건.

## 검증 결과
| 항목 | 결과 |
|------|------|
| 초록·#1a2238·system-ui grep | **0건** |
| 더미배열(const members/PLANS/RANKS·let members) | **0건** |
| 관리자 추가/삭제(addAdmin·openAdminDelModal·admin-slot·simulateUpload·prompt) | **0건** |
| '내 계정' 메뉴 | **0건** |
| fetch 경로 10종 | 전수 present |
| 데이터/렌더 함수 14종 vs HEAD | **IDENTICAL** |
| loadRoster/loadPlans | additive 1줄(renderRosterStats)만 |
| JS 문법(node --check) | **OK** |
| Jinja parse + render | OK (사이드바·section-card 12·stats-row·has_slides 정상) |

> 남은 확인(브라우저 실측 권장): 사이드바 탭 전환, 명단 추가/삭제(tbody 위임)·과목 컨텍스트, 통계 카드 수치(좌석 게이지·지위·만료), 플랜/리포트 로드. (정적 렌더·grep·Jinja 파스·JS 문법·함수 바이트 비교까지 통과, 실서버 기동 미수행.)
