# COMPLETION_REPORT — 포털 P2+P3 외부검증(Codex+Gemini) 반영 수정 5건 (2026-06-06 v3.14)

작업일: 2026-06-06 | 작업자: Lead Developer | 기준: CLAUDE.md §0·§8·§9·§15-7·§16·§18 D9·D10
상태: **구현·신규 pytest·내부 레드팀(security-reviewer FAIL 0) 완료 — 외부 Codex+Gemini 재검증 1라운드 + CEO 승인은 운영자 게이트(아래 9)**

## 0. ★ 1번 스키마 분기 결과 = (A) — Codex 지적 옳음
- `db/p05_logging_schema.sql`·`db/reports_special_schema.sql`가 `access_logs`에 `institution_id`·`subject_code`를 추가하고, `_log_slide_view`(server_render.py:351)가 **열람 시점 스냅샷**(institution_id=`g.institution_id`, subject_code=슬라이드 과목)으로 INSERT함을 확인. → 분기 (A): 스냅샷 컬럼 존재 → 수정 진행. (B 아님.)

## 1. 범위
- 외부검증(Codex depth + Gemini breadth) 확정 5건 + 마이그레이션 1건. **읽기 전용 집계·타임존·검증 로직만** 수정. §0 단일판정식(register/verify/active_seat_count) 불변.
- 인증·좌석 쓰기·register/verify/_authenticate **미변경**. D21(granted-OR 이원화)은 추적 유지(코드 변경 없음, 별도 §12 세션).

## 2. 수정 내역
| # | 등급 | 내용 | 파일·근거 |
|---|------|------|-----------|
| 1 | High | 조회수(total_views·monthly_views·top_slides)를 access_logs 스냅샷(`al.institution_id`·`al.subject_code`) 기준으로 필터. 현재 `u.institution_id`·`s.subject_code` 재분류(시간축 오염) 제거. total/monthly는 users·slides 조인 제거, top_slides의 slides 조인은 제목·염색 **표시용만**(필터는 al). | `_portal_report_data` |
| 2 | Med(§0) | P3 구성원활동 active = `u.status='active'`(NULL 제외) — `COALESCE(status,'active')` 제거 → `active_seat_count`와 정확히 일치(P2 좌석↔P3 활성 모순 제거). NULL은 `IS DISTINCT FROM`으로 비활성 분류. | `_portal_report_data` 멤버 쿼리 |
| 3 | Med | `SUM(max_seats)`에 접근창 필터(`access_open_date<=today AND subscription_end>=today`, today=`_today_kst`) 추가 → 미래 갱신 구독 합산(150+150=300) 차단. **`active_seat_count`(점유)는 불변**, 정원 합산만. | `_portal_report_data` 좌석 쿼리 |
| 4 | 타임존 | P2·P3 날짜연산 `_date.today()`→`_today_kst()` 4곳: `_sub_status`(P2 카드·관리자 목록 공유)·`portal_plans_list` D-day·`_portal_report_range`·관리자 `api_institutions_list` dday. 날짜 경계 half-open(`>=start AND <end+1day`). 새 헬퍼 없이 기존 `_today_kst` 재사용. | 4개 위치 |
| 5 | Low | period allowlist `{'1m','3m','6m','all'}`(`_norm_report_period`) — 미허용값은 조용한 전체확장 대신 기본 '3m'. report·export 양쪽 적용. | `portal_report`·`portal_report_export` |
| 6 | 마이그레이션 | `users.status NOT NULL` 근본해결(`db/users_status_notnull_migration.sql`, 멱등·트랜잭션: NULL 백필→DEFAULT→NOT NULL). **CEO가 EC2 psql 실행**(§12·§20). | 신규 .sql |

## 3. P2 점검 결과 (item 3 관련)
- `portal_plans_list`는 구독 행을 **카드별 개별 표시**(SUM 없음) — 150+150 혼합 버그가 P2에는 없음. 각 카드는 `status_key`(active/upcoming/expired, 이제 KST)로 현재/미래/만료를 구분. 카드 목록에 접근창 필터를 걸면 미래·만료 카드가 사라져 오히려 의도(전체 구독 현황 표시) 위반 → **P2 카드 목록은 변경하지 않음**(item4 KST 치환만 적용). 좌석 윈도우 필터는 P3의 SUM에만 적용.

## 4. 변경 파일
- `server_render.py`: `_portal_report_data`(조회수 스냅샷·active 정의·좌석 윈도우·날짜 half-open), `_portal_report_range`(KST), `_norm_report_period`+상수 신설, `portal_report`·`portal_report_export`(period 정규화), `portal_plans_list`(KST dday), `_sub_status`(KST), `api_institutions_list`(KST dday).
- `db/users_status_notnull_migration.sql`: 신규(CEO 실행 대기).
- `tests/test_portal_review.py`: 신규 13건.
- `CLAUDE.md`: §9 P3 외부검증 반영 블록, §18 D10 갱신·D25 신설, v3.14 헤더·이력.

## 5. 테스트
- `pytest 196 passed` (기존 183 회귀 0 + 신규 13). 신규는 조회수 스냅샷 필터·active NULL 제외·좌석 윈도우·_today_kst 사용·half-open 경계·period allowlist를 SQL 텍스트/파라미터 수준에서 검증.
- openpyxl 로컬 설치(3.1.5), xlsx 테스트 `importorskip` 병행.

## 6. 내부 레드팀(security-reviewer, §12 내부 QA)
- 5건 전부 **PASS, FAIL 0, 인접 신규 결함 0**. 멀티테넌시(al.institution_id=g.institution_id 스코프, 타 기관 로그 유출 차단), §0 단일판정식, IDOR 불가, 비구독 403, `_xlsx_safe` 유지, ANY(빈배열) 회피(`_empty_report` 분기), 파라미터 순서 일치 모두 확인.

## 7. 한계·미완 (숨기지 않음, §13)
- **마이그레이션 미적용**: `users.status NOT NULL`은 .sql만 작성, **CEO가 EC2 psql 실행**(§18 D25). 실행 전엔 잔존 NULL status 행이 P3에서 비활성으로 분류될 수 있음(좌석엔 영향 없음 — active만 점유). 운영 중 `SET NOT NULL`은 짧은 ACCESS EXCLUSIVE 락 → 트래픽 적은 시점 권장.
- **스냅샷 무결성 전제**: 조회수 스냅샷 정확성은 `db/p05_logging_schema.sql`가 RDS에 적용돼 있어야 보장(코드 검증 사각, §20 인프라 점검 영역 — 사람 확인).
- **라이브 스모크·실수치 미검증**: access_logs·chat_logs 실데이터 거의 없어 0/빈 차트가 정상. 실수치는 134종 입고·학생 e2e 후.
- **외부검증 미실시(운영자 게이트)**: 본 세션은 구현 + 내부 레드팀까지. **Codex+Gemini 재검증 1라운드(이 5건·인접 경로 한정) + CEO 승인**은 §12 거버넌스상 운영자가 수행(Gemini는 본 에이전트 도구 부재). 그 통과 후 최종 승인.

## 8. 배포
- 커밋·push origin/main 완료. **EC2 git pull + systemctl restart는 CEO**. **마이그레이션 `db/users_status_notnull_migration.sql`은 CEO가 EC2에서 psql 실행**(§12·§20).

## 9. 남은 게이트 (운영자)
1. 외부 Codex+Gemini 재검증 1라운드(이번 5건·인접 경로 한정).
2. CEO 최종 승인.
3. `db/users_status_notnull_migration.sql` RDS 실행 + `db/p05_logging_schema.sql` 적용 여부 확인(§20).
4. EC2 git pull + 재기동.
