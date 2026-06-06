# COMPLETION_REPORT — 기관 포털 P2(구독 플랜) (2026-06-06 v3.12)

작업일: 2026-06-06 | 작업자: Lead Developer | 기준: CLAUDE.md §0·§8·§9·§16·§17
상태: **구현·내부 QA(a·b·c+과목격리) 통과·pytest 168 passed 완료 — 배포 push까지(EC2 pull·restart는 CEO)**

## 1. 범위
- 포털 3탭 중 **P2(구독 플랜)만** 구현. **읽기 전용**(표시 + 내보내기), 인증·좌석·쓰기 게이트 신설 없음.
- P1(명단)·인증·좌석·register/verify/_authenticate 로직 **일절 미변경**.
- P3(이용 리포트)는 다음 세션.

## 2. CEO 확정 설계 (착수 전 1회 승인 + 보완 2개)
- 슈퍼관리자 엔드포인트 직접 호출 금지 → **포털 전용 읽기 래퍼**(SQL·헬퍼만 재사용).
- 단일 진실(§0): 구독 = `subscriptions`만, `institutions` 옛 컬럼 0건. 좌석 = `active_seat_count`, D-day = `_sub_status`/`_sem_dates` 재사용.
- /viewer 게이트 우회 금지: 포털 "열람"도 표준 `_slide_access_allowed`.
- **보완#1**: `/plans/slides/export` 에도 `_subscribed_subjects` allowlist 적용.
- **보완#2**: 두 slides 경로 모두 비구독 `subject_code` → 빈 목록 아닌 **403**.
- PDF는 서버 생성 금지(§13-1 한국어 폰트 한계) → 클라이언트 `window.print()`.

## 3. 변경 파일
- `server_render.py` (+약 175줄, 읽기 라우트만 추가):
  - `_portal_subject_slides(cur, subject_code)` — 과목 배포(deployed) 슬라이드 메타(콘텐츠는 SA 단일채번이라 고객 기관 id 필터 안 함, 격리는 과목 구독).
  - `GET /portal/api/plans` — 구독 카드(플랜·max_seats·시작학기·학기수·접근창·만료·구독료·status·D-day) + 좌석현황(`active_seat_count`, 소진율).
  - `GET /portal/api/plans/slides?subject_code=` — 메타 목록, 비구독 403.
  - `GET /portal/api/plans/slides/export?subject_code=&format=xlsx|csv` — `_xlsx_safe` 셀 방어, 비구독 403, bad format 400, openpyxl 부재 시 graceful 500.
  - 전 라우트 `@login_required` + `_portal_guard`(scope=`g.institution_id`, inst_id 쿼리/바디 미참조).
- `templates/portal.html`: `#panel-plan` 구현(P1과 동일 standalone+interceptor.js, `esc()` XSS). 플랜 카드(좌석바·소진율·상태뱃지·D-day·구독료), 카드 선택→슬라이드 테이블(검색·"열람"=`/viewer/<id>` 앵커), 내보내기 버튼(xlsx/csv=GET 다운로드, PDF=`window.print()`). 탭 진입 시 1회 지연 로드.
- `tests/test_portal_p2.py`: 신규 16건.
- `CLAUDE.md`: §9 포털 P2 블록 추가, v3.12 헤더·이력.

## 4. 엔드포인트·게이트 요약
| 라우트 | 메서드 | 게이트 | 과목 격리 |
|--------|--------|--------|-----------|
| /portal/api/plans | GET | login_required+_portal_guard | — (자기 기관 전 구독) |
| /portal/api/plans/slides | GET | 동일 | _subscribed_subjects, 비구독 403 |
| /portal/api/plans/slides/export | GET | 동일 | _subscribed_subjects, 비구독 403 |

- 모두 GET → CSRF 면제(쿠키 JWT 자동 전송), `<a download>`/`window.location` 다운로드 가능.

## 5. 내부 QA 자체검증 (읽기라 §12 외부검증 대신 Claude Code 내부)
- **(a) 스코프 격리**: 세 엔드포인트 `g.institution_id`만 사용, inst_id 쿼리 무시. `test_plans_no_inst_id_from_query`(SNU 줘도 CNU만) ✓
- **(b) /viewer 게이트 우회 없음**: 포털 슬라이드 경로는 메타데이터만 반환·타일토큰 미발급. "열람"→/viewer→표준 게이트. `test_plan_slides_subscribed_returns_deployed_metadata`(SQL에 tile 없음) ✓
- **(c) 내보내기 수식주입 방어**: xlsx·csv 모든 셀 `_xlsx_safe`. `test_export_xlsx/csv_formula_injection_defused`(`=…`→`'=…`) ✓
- **(+) 전 slides 경로 과목 격리**: list·export 비구독 403. `test_plan_slides_non_subscribed_403`·`test_export_non_subscribed_403` ✓
- **단일 진실**: subscriptions만·institutions deprecated 컬럼 미참조. `test_plans_scope_and_single_source`(`max_users`/`subscription_plan` 부재) ✓

## 6. 테스트
- `pytest 168 passed` (기존 152 회귀 0 + P2 16 신규).
- openpyxl 로컬 미설치였으나 prod `requirements.txt`에 `openpyxl>=3.1.0` 포함 — xlsx 테스트는 `importorskip` 후 로컬 설치(3.1.5)로 실검증까지 완료.

## 7. 한계·미완 (숨기지 않음, §13)
- **P3(이용 리포트) 미구현** — 다음 세션. P2+P3 묶은 외부검증(Codex/Gemini)은 P3 완료 후 판단.
- **라이브 스모크 미실시** — 코드·pytest 레벨만. EC2 배포 후 실데이터 확인은 다음 차수(HST 134종 입고 약 2026-06-16 예정 후 학생 e2e와 함께).
- **마이그레이션 없음** — 읽기 전용이라 스키마 변경 없음(.sql 없음). 기존 `subscriptions`/`subject_codes`/`slides`/`institution_rosters` 컬럼만 사용.
- **`_sub_status`는 `_date.today()` 사용**(KST `_today_kst` 아님) — 기존 헬퍼 그대로 재사용(신규 계산식 금지 지침 준수). 좌석 카운트(`active_seat_count`)는 §0 단일판정식과 정확히 일치. 표시용 D-day의 경계 타임존 미세차는 §18 D10 잔여 추적 범위.
- **콘텐츠 메타 노출 범위**: 구독 과목의 배포 슬라이드 ID·제목·염색을 포털 관리자에게 카탈로그로 노출(타일·토큰 없음). 그 기관이 구독한 과목에 한정 — §9 리포트 Top-N 슬라이드 노출과 동일 수준, 콘텐츠 접근 아님.

## 8. 배포
- 커밋·push origin/main 완료. **EC2 git pull + systemctl restart는 CEO**(§12·§20). 마이그레이션 없음.
