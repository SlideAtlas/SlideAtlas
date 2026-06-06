# COMPLETION_REPORT — 포털 P2+P3 재검증 2R(Codex) 반영 (2026-06-06 v3.15)

작업일: 2026-06-06 | 작업자: Lead Developer | 기준: CLAUDE.md §0·§9·§15-7·§15-8·§16·§18 D9
상태: **구현·신규 pytest·내부 레드팀(security-reviewer 7/7 PASS) 완료 — 좁은 Codex 재확인 + CEO 승인 + 마이그레이션 2종 실행은 운영자 게이트(아래 9)**

## 0. ★ 1번 분기 처리 = 라이브 RDS 조회 불가 → 멱등 정리로 양쪽 커버
- "is_special=TRUE인데 subject_code가 NULL이 아닌 기존 계정" 존재 여부는 **작업자가 라이브 RDS 조회 권한이 없어(§12·§20 — VPC 프라이빗·읽기전용) 확정 불가**. → 승격 코드 수정 + **멱등 정리 마이그레이션**(`db/special_subject_code_cleanup_migration.sql`, 잔존 0건이면 no-op)을 함께 제공해 (있음)/(없음) 양쪽 분기를 안전하게 커버. 잔존 건수 확인·실행은 CEO.

## 1. 범위
- Codex(depth) 2R 재검증 확정: 필수 2건(#1 is_special 좌석 정합, #2 소진율 분자/분모) + 가벼움 2건(#3 문서, #4 LEFT JOIN). Gemini #3은 "정상"으로 봤으나 Codex가 분자/분모 비대칭을 더 깊이 봐 버그 확정 → CEO 기준 A로 결정.
- §0 단일판정식(register/verify/active_seat_count/P3 active 동일 집합) 유지. 인증·좌석 쓰기·register/verify/_authenticate 미변경. D21 추적 유지.

## 2. 수정 내역
| # | 등급 | 내용 | 위치 |
|---|------|------|------|
| 1 | 필수(§0) | 특별계정 승격 시 `subject_code=NULL`(+position NULL) — 좌석 비점유(CEO). P3 users 집계의 `is_special` 제외절 제거 → subject_code=NULL로 자연 제외 → `active_seat_count`(is_special 절 없음)와 '글자까지 같은 집합'. 승격 시 P2 used_seats·P3 active_users 동시 -1. | `api_special_accounts_create`, `_portal_report_data` |
| 1 | 필수 | 기존 잔존 정리 멱등 마이그레이션(CEO 실행) | `db/special_subject_code_cleanup_migration.sql` |
| 2 | 필수 | 소진율 분자(active_users)도 분모(max_seats)와 같은 `window_codes`(접근창 열린 active 구독 과목)만. 만료 과목 유령 active 양쪽 제외(N명/0석 0% 왜곡 제거). window_codes 비면 members skip(0/0). **`active_seat_count` 불변.** | `_portal_report_data` |
| 3 | 문서 | 스냅샷 `al.subject_code` NULL 과거 로그는 의도적 집계 제외(과목 귀속 불명, 백필 안 함) 명문화 | CLAUDE.md §15-7 |
| 4 | 가벼움 | top_slides `JOIN`→`LEFT JOIN slides` + `COALESCE(s.title_ko, al.slide_id)`, `GROUP BY al.slide_id` — 깨진 참조도 집계 포함(total/monthly와 정합) | `_portal_report_data` |
| 5 | 추적 | D26 슈퍼관리자 COALESCE(status,'active') 잔재(L2232·L3528·L3723·L3842, 포털 무영향) — MD감사 세션 통일 검토 | CLAUDE.md §18 D26 |

## 3. 분자/분모 동작 (기준 A)
- `window_codes` = 구독 과목 중 접근창 열린 active 구독(`access_open_date<=today<=subscription_end`, today=`_today_kst`)이 있는 과목.
- active_users(분자)·max_seats(분모) 둘 다 `window_codes` 집합만. 만료/미래 과목은 양쪽에서 빠짐 → "집계 제외".
- 구성원 활동(donut)도 window_codes 기준(active==active_users 정합). 등록 이용자(총원)는 전체 구독 과목 기준(별도 KPI).

## 4. 변경 파일
- `server_render.py`: `_portal_report_data`(window_codes 산출·members/active 분자 window 제한·max_seats Python 합산·is_special 제외절 제거·top_slides LEFT JOIN), `api_special_accounts_create`(승격 subject_code/position NULL).
- `db/special_subject_code_cleanup_migration.sql`: 신규(CEO 실행).
- `tests/test_portal_p3.py`·`tests/test_portal_review.py`: mock 시퀀스 갱신(window_rows 추가·max_seats fetchone 제거) + 2R 신규 6건.
- `CLAUDE.md`: §9 P3 2R 블록, §15-7 스냅샷/기준A 명문화, §18 D25b·D26, v3.15 헤더·이력.

## 5. 테스트
- `pytest 202 passed` (기존 196 회귀 0 + 2R 신규 6). 신규: 승격 subject_code=NULL, P3 is_special 제외절 부재, 분자 window_codes 제한, 만료 시 분자·분모 동시 제외, top_slides LEFT JOIN+폴백, 정리 마이그레이션 멱등.
- 기존 P3 테스트 mock 시퀀스 갱신(쿼리 구성 변경 반영).

## 6. 내부 레드팀(security-reviewer, §12)
- **7/7 PASS, FAIL 0, 인접 신규 결함 0.** §0 같은 집합(승격 시 P2·P3 동시 -1), 분자=분모 window_codes, IDOR 없음(전 쿼리 g.institution_id 스코프), LEFT JOIN 정합, 마이그레이션 멱등·트랜잭션, **특별계정 subject_code=NULL이 `_slide_access_allowed`(is_special 분기, subject 미참조)에 무영향(좌석↔접근 직교)** 확인. 바인딩 순서·ANY(빈배열) 회피·NULL max_seats 가드 모두 OK.

## 7. 한계·미완 (숨기지 않음, §13)
- **마이그레이션 2종 미적용**: `special_subject_code_cleanup_migration.sql`(D25b)·`users_status_notnull_migration.sql`(D25, 1R) 모두 .sql만 작성 — **CEO가 EC2 psql 실행**. 미실행 시: (D25b) 잔존 특별계정이 P2·P3 양쪽에 동일 계상(여전히 일치하나 좌석 1 과점유 가능). (D25) 잔존 NULL status는 P3 비활성 분류. `SET NOT NULL`은 짧은 ACCESS EXCLUSIVE 락 → 트래픽 적은 시점 권장.
- **라이브 RDS 조회 불가**: 1번 잔존 건수 미확인(권한 없음) → 멱등 정리로 커버, 실제 정리·검증은 CEO.
- **라이브 스모크·실수치 미검증**: 로그/사용자 실데이터 거의 없어 0/빈 차트가 정상. 134종 입고·학생 e2e 후.
- **외부검증 미실시(운영자 게이트)**: 구현 + 내부 레드팀까지. 좁은 Codex 재확인(is_special 정리 후 P2=P3 같은 집합·소진율 분자/분모 같은 행집합) + CEO 승인은 운영자 수행.
- **per_user_views**: total_views(전체 구독 과목)/active_users(window 과목) — 분모만 window라 약간 비대칭이나 소진율(핵심 KPI)은 정합. 추적.

## 8. 배포
- 커밋·push origin/main 완료. **EC2 git pull + 재기동, 마이그레이션 2종 psql 실행은 CEO**.

## 9. 남은 게이트 (운영자)
1. 좁은 Codex 재확인 1회(이번 2R 수정·인접 경로 한정).
2. CEO 최종 승인.
3. `db/special_subject_code_cleanup_migration.sql` + `db/users_status_notnull_migration.sql` RDS 실행(트래픽 적은 시점).
4. EC2 git pull + 재기동.
