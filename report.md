# portal.html 명단 관리 탭 — 확정 디자인 재이식 보고서

> 작성: 2026-06-13 · 작업: claude · 범위: `templates/portal.html`의 **#tab-roster 시각(마크업·CSS)만** 교체
> 기준: `c:\Users\…\Downloads\portal_roster_design.html`(확정 디자인). 색/폰트는 인라인 :root 대신 **lms.css 토큰** 사용(#tab-roster 스코프 로컬 변수로 디자인 토큰명 매핑).
> 원칙: 기능·fetch·JS·동선·플랜/리포트 탭은 현 portal.html 그대로 — **18개 데이터/렌더 함수 + esc + fetch 경로 byte-identical**.

## 반영한 7개 차이 (확정 디자인과 일치)
1. **page-desc 제거** — 로스터 탭은 제목 "명단 관리"만(`.page-head>.page-title` 24px navy). (plan/report desc는 유지 → page-desc 2건 잔존은 정상.)
2. **과목 선택 통합** — 독립 카드 삭제. "이용자 추가" 카드 첫 줄 `.subject-row`(라벨 "과목 선택" + `#work-subject`)로 흡수. "명단은 과목별…/먼저 과목을…식별자는 이메일" 안내문 전부 제거.
3. **이용자 추가 헤더 정리** — "이용자 추가"만(우측 "— 조직학(HST)" 부제 = `#ctx-subject-label`은 JS 안전을 위해 DOM 유지하되 `display:none`). "선택한 과목으로…동기화됩니다" 안내문 제거. 입력 한 줄(이름·지위·이메일·[추가 navy]).
4. **일괄 등록 줄 축약** — "엑셀·CSV 일괄 등록" + [양식 다운로드 outline][파일 선택(native)][업로드 navy] 우측 정렬(`.upload-row`).
5. **명단표 디자인** — `.tcard`(보더 최소화), 행높이 19px·구분선 line-soft·헤더 대문자 11.5px. 인증 배지 = **dot+pill**(`.badge.ok`=sky-wash, `.badge.wait`=gray; dot은 `::before`로 — 라이브 배지에 dot 요소가 없어 CSS로 부여). "이용자 명단" 옆 카운트(`#member-count`)=Montserrat sky-deep.
6. **기관 관리자 접이식** — 네이티브 `<details>`(JS 0). 헤더 "기관 관리자" + "총 N명" pill + chevron(open 시 90° 회전). "읽기 전용·운영팀 문의" 문구 제거, 펼치면 읽기전용 표만.
7. **요약 4셀 바** — `.summary`(grid 1.7/1.15/1/1.05) 좌석 게이지/지위 배지/인증/만료. **데이터=현 renderRosterStats() 그대로**(출력 클래스 `.seat-row/.stat-bar/.stat-fill/#cnt-*/#expire-*`에 CSS로 디자인 외관 부여).

## 절대 불변 — 검증 통과
- **18개 함수 byte-identical**(renderMembers·renderAdmins·addMember·delMember·uploadMembers·downloadTemplate·onWorkSubjectChange·fillSubjectSelects·renderRosterStats·renderPlans·selectPlanSubject·renderPlanSlides·exportSlides·loadReport·renderReport·loadRoster·loadPlans·doLogout) + **esc identical**.
- fetch 경로 9종 전수 present. **plan+report+toast 블록 HEAD와 IDENTICAL**(미수정).
- member-tbody 이벤트 위임·work-subject 컨텍스트·switchTab·interceptor·Jinja({{ institution_name }}·{{ institution_id }}·has_slides)·사이드바 로고 보존. 프론트 institution_id 미전송(IDOR 0).
- JS-touched id 20종 전수 존재. JS 문법 OK(node --check), Jinja parse OK, 렌더 스모크 OK, 초록·#1a2238·system-ui 0.

## 프리즈된 JS 제약으로 인한 의도적 처리(보고)
- **삭제 버튼**: 라이브 `<button class="del">삭제</button>`(텍스트) → CSS `font-size:0`+`::before`(\eb41 트래시)로 **아이콘 외관**, 텍스트는 a11y용 DOM 유지·위임 그대로.
- **명단 행 셀**: renderMembers가 `.u-name/.u-email/.role.prof` 클래스를 안 붙이므로 `td:nth-child()`로 근사(이름 bold·이메일 Montserrat). **교수만 sky-deep 강조는 미적용**(타깃 클래스 부재).
- **검색창 생략**: 라이브에 명단 검색 핸들러가 없어 디자인의 검색 입력을 넣으면 **죽은 컨트롤**("끊긴 핸들러 0" 위반) → 기능형 필터 2개(과목·지위)만 유지.
- **#expire-bar 제거**: 확정 디자인의 만료 셀엔 게이지 없음. renderRosterStats의 `expire-bar` 접근은 `if(bar)` 가드라 안전(no-op).
- **관리자 '총 N명' pill**: 라이브에 admin 카운트 데이터 훅이 없음 → **더미 금지** 준수 위해 **additive MutationObserver**(#admin-tbody 렌더 감지 → 실제 행 수 표기, 빈 상태 행 제외)로 구현. 프리즈 함수·fetch 무수정.
- **숫자 부분 볼드**: 지위/인증 셀은 renderRosterStats가 "학생 1명"처럼 textContent 전체를 세팅 → 숫자만 Montserrat-bold 분리는 미적용(셀 단위 폰트만).

## ⚠ 확인 필요 (지시와 현 상태 불일치)
- 지시 '불변'은 사이드바 로고를 `SlideAtlas_Navy_Hor_small.png`로 적었으나, **현 라이브는 `SlideAtlas_White_Hor_trans.png`**(네이비 사이드바엔 흰 로고가 보임 — 네이비 로고는 안 보임). "현 상태 보존" 원칙·시인성에 따라 **현 White 로고를 유지**했습니다. Navy로 바꿔야 하면 알려주세요.
- 사이드바·플랜·리포트 탭은 이번 범위(명단 탭만)에서 제외 — 확정 디자인의 사이드바(텍스트 로고·org 위계·sky 액티브 바)는 미반영. 필요 시 후속 작업으로.

## 검증 결과
| 항목 | 결과 |
|------|------|
| 제거 문구 6종 grep | **0건** |
| 초록·#1a2238·system-ui | **0건** |
| body institution_id(IDOR) | **0건** |
| 함수 18종 + esc vs HEAD | **IDENTICAL** |
| fetch 9종 / plan·report 블록 | present / **IDENTICAL** |
| JS-touched id 20종 | 전수 present |
| JS 문법 / Jinja parse / 렌더 | OK / OK / OK |

> 실측: CEO가 EC2 배포 후 /portal 명단 탭에서 확정 디자인과 동일한 모양 + 명단 추가/삭제·과목 컨텍스트·양식 다운로드·플랜/리포트 로드 정상 확인(§20). 본 작업은 정적 렌더·grep·함수 byte-diff·JS 문법까지 통과, 실서버 기동 미수행.
