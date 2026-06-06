# COMPLETION_REPORT — 기관 포털 P3(이용 리포트) (2026-06-06 v3.13 · 포털 3탭 완성)

작업일: 2026-06-06 | 작업자: Lead Developer | 기준: CLAUDE.md §0·§8·§9·§15-7·§18 D9·§17
상태: **구현·내부 QA(a·b·c·d+빈데이터)·pytest 183 passed 완료 — 배포 push까지(EC2 pull·restart는 CEO)**

## 1. 범위
- 포털 3탭 중 **마지막 P3(이용 리포트)만** 구현. **읽기 전용**(집계 표시 + 내보내기), 인증·좌석·쓰기 게이트 신설 없음.
- P1(명단)·P2(구독 플랜)·인증·좌석·register/verify/_authenticate **일절 미변경**.
- **이로써 포털 3탭(명단·구독플랜·이용리포트) 완성.**

## 2. CEO 확정 설계 (착수 전 1회 승인)
- 슈퍼관리자 reports 엔드포인트 직접 호출 금지 → **포털 전용 읽기 래퍼**(SQL·집계 로직만 재사용). **학교 선택 드롭다운 없음**(자기 기관 고정).
- 단일 진실(§0): 집계 원천 = `access_logs`·`chat_logs`·`users`·`subscriptions`. `institutions` 옛 컬럼 0건. 활성 정의 = `status='active'`(P1·P2·`active_seat_count` 일치).
- 과목 격리: `subject_code`='all'(합산) 또는 `_subscribed_subjects` 중 하나, 비구독 → **403**.
- 과목축 분리→기관 롤업(§18 D9): active_users·max_seats·소진율 (기관×과목) 산출, all은 합(SUM).
- **구성원 활동(활성/비활성/미인증) = status 기반**(CEO 확정): 활성=active / 미인증=pending_verification / 비활성=그 외. 새 활동 판정식 도입 안 함.
- PDF는 서버 생성 금지(§13-1) → 클라이언트 `window.print()`. 서버 export는 XLSX만.

## 3. 변경 파일
- `server_render.py` (+약 290줄, 읽기 라우트만):
  - `_portal_report_range(period)` — 1m/3m/6m=today-30/90/180d, all=무필터(날짜 필터일 뿐).
  - `_empty_report()` — 구독 0 시 ANY(빈배열) 회피용 0 구조.
  - `_portal_report_data(cur, inst_id, subject_code, subjects, start, end)` — KPI·구성원활동·월별조회·Top10·AI월별 1회 산출(JSON·export 공통). chat_logs 부재/오류는 마지막에 try로 격리(AI만 0/[], 나머지 보존).
  - `GET /portal/api/report` — 통합 1응답(+subjects 드롭다운). 비구독 403, all+구독0 → _empty_report.
  - `GET /portal/api/report/export?...&format=xlsx` — openpyxl 4시트(요약/월별조회/인기슬라이드/AI월별), 전 셀 `_xlsx_safe`. 비구독 403, xlsx 외 format 400, openpyxl 부재 graceful 500.
  - 전 라우트 `@login_required`+`_portal_guard`(scope=`g.institution_id`, inst_id 쿼리/바디 미참조).
- `templates/portal.html`: `#panel-report` 구현(P1·P2와 동일 standalone+interceptor.js, `esc()` XSS). 기간 세그먼트(1/3/6개월/전체)·과목 드롭다운(전체/특정)·KPI 그리드·CSS 막대차트(월별조회·AI·구성원활동)·Top10(클릭="열람"=`/viewer/<id>` 표준 게이트)·엑셀/인쇄. 탭 진입 1회 지연 로드. 빈 데이터 "데이터 없음".
- `tests/test_portal_p3.py`: 신규 15건.
- `CLAUDE.md`: §9 포털 P3 블록 추가(3탭 완성 표기), v3.13 헤더·이력.

## 4. 엔드포인트·게이트 요약
| 라우트 | 메서드 | 게이트 | 과목 격리 |
|--------|--------|--------|-----------|
| /portal/api/report | GET | login_required+_portal_guard | all 또는 _subscribed_subjects, 비구독 403 |
| /portal/api/report/export | GET | 동일 | 동일, format!=xlsx → 400 |

- 모두 GET → CSRF 면제(쿠키 JWT 자동), `window.location` 다운로드.

## 5. 내부 QA 자체검증 (읽기라 §12 외부검증 대신 Claude Code 내부)
- **(a) 스코프 격리**: `g.institution_id`만, inst_id 쿼리 무시(학교 드롭다운 없음). `test_report_scope_uses_g_institution_not_query`(SNU 줘도 CNU만) ✓
- **(b) 과목 격리**: 비구독 → 403(report·export). `test_report_non_subscribed_subject_403`·`test_export_non_subscribed_subject_403` ✓
- **(c) 수식주입 방어**: XLSX 전 셀 `_xlsx_safe`(인기 슬라이드 제목 `=…`→`'=…`). `test_export_xlsx_formula_injection_defused` ✓
- **(d) 집계 과목별 산출→롤업**: users·subscriptions 집계가 subject_code 스코프, max_seats=ANY([code]). `test_aggregation_subject_scoped`(institutions 옛 컬럼 미참조 동시 확인) ✓
- **(+) 빈 데이터 graceful**: 0 나눗셈 가드(util/per_user=0), all+구독0 → _empty_report(본쿼리 미실행), chat_logs 오류 격리. `test_empty_data_graceful_zeros`·`test_all_subject_no_subscription_empty_report`·`test_chat_logs_failure_graceful` ✓

## 6. 테스트
- `pytest 183 passed` (기존 168 회귀 0 + P3 15 신규).
- openpyxl 로컬 설치(3.1.5)로 xlsx 실검증, prod `requirements.txt` 포함 — xlsx 테스트는 `importorskip` 병행(타 환경 portable).

## 7. 한계·미완 (숨기지 않음, §13)
- **라이브 스모크·실수치 미검증** — 코드·pytest 레벨만. CEO 지시대로 access_logs·chat_logs 실데이터가 거의 없어 현재 화면은 0/빈 차트가 정상. 실수치 검증은 HST 134종 입고·학생 e2e(약 2026-06-16 이후) 후로 미룸.
- **외부검증 미실시** — P3는 읽기라 내부 QA만. **P2+P3 묶은 Codex/Gemini 외부검증 1회**는 다음 단계에서 판단(이번 세션 범위 밖).
- **마이그레이션 없음** — 읽기 전용, 스키마 변경 없음(.sql 없음). 기존 `access_logs`/`chat_logs`(reports_special_schema, subject_code 포함)/`users`/`subscriptions`/`slides` 컬럼만 사용.
- **기간 경계 타임존**: `_portal_report_range`는 `_date.today()` 사용(슈퍼관리자 `_reports_date_range`와 동일) — 리포트 기간은 §18 D10 '잔여 추적' 범위. 좌석/활성 판정은 §0 단일판정식과 일치.
- **차트 폴리싱 보류**: 막대차트는 CSS div 기반, 구성원 활동은 도넛 대신 막대+퍼센트로 단순화. CEO 방침대로 디자인 폴리싱은 전체 기능 완성 후 일괄.
- **per_user 정의**: '1인당 평균 조회수' = total_views/active_users(활성 기준). 슈퍼관리자 KPI의 per_user(ai/active)와 의미가 다르나 스펙(P3) 정의를 따름.

## 8. 배포
- 커밋·push origin/main 완료. **EC2 git pull + systemctl restart는 CEO**(§12·§20). 마이그레이션 없음.
