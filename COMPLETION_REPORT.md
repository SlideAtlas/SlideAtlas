# COMPLETION_REPORT — 포털 P3 재검증 3R(Codex) 반영 (2026-06-06 v3.16)

작업일: 2026-06-06 | 작업자: Lead Developer | 기준: CLAUDE.md §0·§15-7·§16·§18 D22
상태: **구현·신규 pytest·내부 레드팀(security-reviewer 6/6 OK) 완료 — 좁은 Codex 재확인 + CEO 승인은 운영자 게이트(아래 8)**

## 1. 범위
- 3R 재검증 2건: 필수 1건(#1 소진율 분모 과목별 권위 row 정규화) + 문서 1건(#2 이용량 KPI vs 소진율 비대칭 의도 명문화).
- **핵심 원칙 준수**: 새 규칙 만들지 않음 — 인증 게이트 `active_window_subscription`이 이미 쓰는 "과목별 권위 row 1개" 규칙(`subscription_end DESC`)을 P3 분모에 그대로 재사용(§0). 신규 마이그레이션 없음. active_seat_count 불변. 직전 추적(D21·D22·D26) 유지.

## 2. 수정 내역
| # | 등급 | 내용 |
|---|------|------|
| 1 | 필수(§0) | P3 소진율 분모(max_seats 합산)를 **과목별 권위 row 1개로 정규화**. 같은 (기관×과목)에 접근창 겹치는 active 구독이 2개+여도 중복 합산(150+150=300)하지 않고, 인증 게이트와 동일한 `DISTINCT ON (subject_code) … ORDER BY subject_code, subscription_end DESC`로 과목당 1행만 SUM. 분모 과목집합·정원 = 분자(window_codes) = 인증 게이트 권위 구독 → 셋이 같은 행집합. |
| 2 | 문서 | 이용량 KPI(조회수·월별·Top·AI)는 구독 보유 과목 전체(만료 포함, 과거 기록 의미) / 소진율(활성/정원)은 현재 접근창 과목만 — 과목 집합이 다른 것은 설계 의도임을 §15-7에 명문화(코드 불변). |

## 3. 변경 코드 (최소)
- `server_render.py` `_portal_report_data` 분모 쿼리 1줄 구조 변경:
  - `SELECT subject_code, max_seats FROM subscriptions WHERE … (조건 동일)` → **`SELECT DISTINCT ON (subject_code) … ORDER BY subject_code, subscription_end DESC`**.
  - WHERE 술어(institution_id·status='active'·access_open_date<=today·subscription_end>=today)는 `active_window_subscription`과 완전 동일. today=`_today_kst`.
- **이용량 KPI SQL(total_views·monthly·top_slides·ai)·active_seat_count·분자(active_users) 로직은 무변경**(git diff로 확인 — 비주석 변경은 분모 쿼리뿐).

## 4. §0 정합 (분자=분모=인증 같은 행집합)
- `active_window_subscription`(auth/auth.py): 과목당 `ORDER BY subscription_end DESC LIMIT 1` → 과목별 최신 subscription_end 구독.
- P3 분모: `DISTINCT ON (subject_code) … ORDER BY subject_code, subscription_end DESC` → 과목별 같은 최신 row.
- 분자(window_codes) = 그 분모 결과의 과목집합. → 인증/좌석/소진율 셋이 같은 권위 구독을 본다.

## 5. 테스트
- `pytest 205 passed` (기존 202 회귀 0 + 3R 신규 3): 분모 쿼리 DISTINCT ON+ORDER BY 구조, 인증 게이트와 같은 정렬 규칙 재사용(소스 대조), 권위 row 1개 → 분모 150(중복합산 300 아님, util=active/150).

## 6. 내부 레드팀(security-reviewer, §12)
- **6/6 OK, FAIL 0, 신규 결함 0.** §0 권위 row 일치(분모 WHERE 술어+`subscription_end DESC`=게이트, 과목별 같은 row 선택), 분자=분모=인증 같은 집합, active_seat_count 불변, `DISTINCT ON`↔`ORDER BY` 정합(subject_code 선두), 멀티테넌시(inst_id 스코프)·바인딩 순서([inst_id, seat_codes, today, today])·NULL max_seats 제외·0나눗셈 가드·이용량 KPI SQL 불변 모두 유지.

## 7. 한계·미완 (숨기지 않음, §13)
- **subscription_end 동률 코너(D22)**: 양쪽 쿼리 모두 secondary sort가 없어 동률이면 비결정적으로 1행 선택 — 게이트와 리포트가 드물게 다른 row를 고를 수 있음. 단 **이번 수정이 신규 불일치를 만들지 않으며**(이전 SUM의 확정적 위반을 D22 잔존 코너 수준으로 축소), 정상 운영(과목당 구독 1개)에선 미발생. 완전 정합은 양쪽에 공통 secondary sort(예: `, id DESC`) 추가가 필요하나 이는 **인증 게이트(auth) 변경을 수반**해 이번 범위 밖 — §18 D22 추적 유지(v1.5/Locust D14 시점).
- **라이브 스모크·실수치 미검증**: 로그/사용자 실데이터 거의 없어 0/빈 차트 정상. 134종 입고·학생 e2e 후.
- **외부검증 미실시(운영자 게이트)**: 구현 + 내부 레드팀까지. 좁은 Codex 재확인(분모=과목별 권위 row·게이트와 같은 row·분자=분모=인증 같은 집합) + CEO 승인은 운영자 수행.
- **직전 마이그레이션 2종 미적용**: `db/users_status_notnull_migration.sql`(D25)·`db/special_subject_code_cleanup_migration.sql`(D25b)는 여전히 CEO 실행 대기(이번 세션 신규 마이그레이션 없음).

## 8. 배포 / 남은 게이트 (운영자)
- 커밋·push origin/main 완료. **EC2 git pull + 재기동은 CEO**(이번 신규 마이그레이션 없음).
1. 좁은 Codex 재확인 1회(3R 분모 정규화·인접).
2. CEO 최종 승인.
3. (직전 대기) 마이그레이션 2종(D25·D25b) RDS 실행.
4. EC2 git pull + 재기동.
