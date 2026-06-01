# COMPLETION_REPORT — 기관 관리자 등록 흐름 (admin roster onboarding)

작업일: 2026-06-01 | 작업자: Lead Developer | 기준: CLAUDE.md §9·§18 D12·D15·§13-2
브랜치: `feature/admin-roster-onboarding-2026-06` | 상태: 구현·내부테스트 완료, **Codex 외부검증 대기**

## 0. 문제
기관 추가 시 `admin_contacts`는 `institutions.admin_contacts`(JSONB)에만 저장되고
명단 등록(`institution_rosters`)·포털 안내 메일이 **모두 끊겨 있었다**. 또한 기존 `/register`·
`verify_email`·`login`·`_authenticate`는 학생 전용(과목 subject_code + 접근창 active 구독 + 좌석)
게이트로, 관리자(role='admin')는 가입 자체가 거부되는 구조였다. `/portal` 라우트는 부재(D15).

## 1. 설계 (CEO 확정)
- roster는 (institution_id, subject_code, email) 독립 행. 관리자 행은 센티넬 `subject_code='__ADMIN__'`,
  과목 행은 'HST' 등 → 같은 이메일이 충돌 없이 공존.
- users 계정은 이메일당 1개. role(시스템 권한, 'admin'=포털 접근)과 position(교수/조교 등, 표시용)은 별개.
- register/verify는 관리자 등록만 있어도 통과(과목·구독·좌석 게이트 면제). 슬라이드 접근 게이트는 불변
  (과목 좌석 안에 있어야 열람) — admin의 `__ADMIN__`은 어떤 슬라이드 과목과도 불일치하므로 콘텐츠 비노출.

## 2. 변경 내역
| 파일 | 변경 |
|---|---|
| auth/decorators.py | `ADMIN_ROSTER_SUBJECT='__ADMIN__'`. `_authenticate` 구독 게이트에 `role=='admin'` 면제(elif) — 반환 shape 무변경 |
| auth/auth.py | `register`(subject 누락 면제+센티넬 채번, 구독·좌석 skip)·`verify_email`(동일)·`login`(구독 게이트 admin 면제 elif) |
| server_render.py | `_send_portal_invite_email`(Gmail SMTP stub, 실패 비치명)·`_upsert_admin_roster`·`api_institution_create`(roster+메일)·`api_institution_update`(추가INSERT / 제거는 __ADMIN__ 행만 DELETE=포털 권한만 회수)·`/portal`+`_is_institution_admin` |
| templates/portal.html | 최소 포털(scope·3탭 placeholder). 본화면 D15 |
| db/admin_roster_schema.sql (신규) | 멱등: position·subject_code 컬럼 + UNIQUE(institution_id,subject_code,email) 정식화(D12) |
| db/auth_schema.sql | fresh install 정합(컬럼·UNIQUE) |
| tests/test_auth.py | +7건 |

## 3. 테스트 결과 (pytest 74/74 통과, 기존 65 + 신규 9)
| 요구 | 테스트 | 결과 |
|---|---|---|
| ① 기관추가→roster(role='admin',position,'__ADMIN__') 등록 | test_institution_create_registers_admin_roster | ✅ |
| ② 그 이메일 /register 허용 | test_register_admin_only_allowed / _skips_subscription_even_if_none | ✅ |
| ③ 인증완료→users.role='admin' 생성 | test_verify_email_admin_creates_admin_role | ✅ |
| ④ /portal 진입 가능 | test_portal_admin_access (+ 학생 차단 test_portal_non_admin_redirected) | ✅ |
| (PUT) 제거=__ADMIN__ 행만 DELETE, suspend/계정삭제 금지 | test_institution_update_syncs_admin_roster | ✅ |
| 겸직자 제거 → 포털 차단 | test_moonlighter_admin_removed_portal_blocked | ✅ |
| 겸직자 제거 → 조직학 슬라이드 열람 유지(503) | test_moonlighter_admin_removed_slides_kept | ✅ |

## 4. 마이그레이션 (EC2, CEO 승인 후 — §12, 코드 작업자 RDS 직접 변경 금지)
`psql ... -f db/admin_roster_schema.sql` (멱등). 실행 전 신 UNIQUE 위반 0건 확인 쿼리 포함.

## 5. 잔여·주의
- **Codex 외부검증 대상**(인증 코어 4경로 수정). 통과 전 main 병합 금지(§12).
- 겸직(admin+학생) 단일 이메일 동시 권한은 D12 UNIQUE 마이그레이션 전제.
- **관리/열람 분리(CEO 확정)**: 관리자 제거 = __ADMIN__ roster 행만 DELETE(포털 권한 회수). users 계정·다른
  과목 roster 행은 불가침 → 겸직자는 슬라이드 열람 유지, 순수 관리자는 포털 접근만 사라짐(계정 정지 아님).
  (suspend·users 변경 코드 제거됨, 테스트로 회귀 방지.)
- 메일은 Gmail SMTP stub(D2 SES 전환 시 `_send_portal_invite_email`만 교체).

---

# COMPLETION_REPORT — D4 subject_code 채번 + 정원 max_seats 이전

작업일: 2026-05-31 | 작업자: Lead Developer | 기준: CLAUDE.md v3.0 (§0·§6-2·§8·§13-2·§16·§18)

## 1. 범위
직전 세션에서 코드 레벨로 끝난 M2(구독 만료 subscriptions 이전)의 미완 2건을 닫아
과목 축(subject_code)을 v1.0부터 정식 작동시킴.

- **D4** users.subject_code 가입 시 채번 (§6-2, §18 D4)
- **Q2** 좌석 정원 검사 subscriptions.max_seats 이전 (§13-2, §16)

## 2. 변경 내역

### D4 — commit 17bb18a
| 항목 | 변경 | 파일 |
|---|---|---|
| (a) register | roster `SELECT subject_code … ORDER BY subject_code LIMIT 1`로 매칭 과목 캡처 → users INSERT에 subject_code 채번. EMAIL_EXISTS를 (기관×과목×이메일) 단위로 정렬. roster 과목 공란 시 ROSTER_SUBJECT_MISSING(403) | auth/auth.py |
| (b) verify_email | user SELECT에 subject_code 추가, active 전환 전 공란이면 SUBJECT_CODE_MISSING(409)+로그 거부(임의 기본값 금지, §0-3) | auth/auth.py |
| (c) 폴백 제거 | login()·_authenticate()의 `(u.subject_code IS NULL OR s.subject_code=u.subject_code)` → `s.subject_code=u.subject_code` 단일화. 만료 검사를 (institution_id, subject_code) 양축으로 정식화 | auth/auth.py, auth/decorators.py |

### Q2 정원 — commit ddfab51
| 항목 | 변경 | 파일 |
|---|---|---|
| register 사전검사 | `SELECT max_users FROM institutions` → `SELECT max_seats FROM subscriptions WHERE (institution_id, subject_code) AND status='active' ORDER BY subscription_end DESC LIMIT 1`. active 카운트도 과목별 | auth/auth.py |
| verify 재검사(동시성) | institutions row 잠금 → 해당 (기관×과목) 구독 행 `FOR UPDATE` 잠금(과목 단위 직렬화) | auth/auth.py |

### 문서 — commit c8c6143
- CLAUDE.md §18 D4 → ✅ 완료 처리.

## 3. 완료 기준 대조
- ✅ pytest **45/45** (각 커밋 독립 green: D4-only 중간상태, 최종상태 모두 확인)
- ✅ 인증·정원 경로 `institutions.max_users`/`subscription_end` **실참조 0건** (auth/ 잔존은 "참조 안 함" 설명 주석뿐)
- ✅ `subject_code IS NULL` 폴백 **0건**
- ✅ NULL subject_code user 0건 전제: 코드/시드 `INSERT INTO users` 0건 + §18 D4 'v1.0 사용자 0' → 폴백 제거 진행
- ✅ §18 D4 "완료" 갱신

## 4. 설계 판단·근거
1. **다중 과목 이메일**: DB UNIQUE(institution_id, subject_code, email)·과목별 카운트로 *구조*는 과목별 독립 레코드를 지원. 단 register/verify/login은 이메일 키 단일 레코드 모델이라, 본 작업은 매칭된 과목 1건을 채번(v1.0 HST 단일에서 정확). 완전한 N-레코드/과목별 가입은 이메일 키 조회를 subject-aware로 바꾸는 별도 큰 변경 — 본 작업 범위 밖, 구조는 마련됨.
2. **특별계정(server_render.py:2349)**: is_special·만료 면제·과목 축 우회 정책(§15-8)상 subject_code NULL이 설계상 정상. 폴백 제거는 `not is_special` 게이트로 영향 없음 → D4 대상 아님(변경하지 않음).
3. **폴백 제거 안전 방향**: subscription_end가 NULL이면 만료 검사 skip(기존 동작). 즉 제거는 lock-out이 아니라 "과목 매칭 시에만 만료 enforce"로 *조이는* 방향 → v1.0 로그인 회귀 위험 없음.
4. **구독 없음 → max_seats 미설정(허용)**: 기존 `max_users is None` 무제한 의미 보존(로스터 업로드가 구독 설정보다 앞설 수 있는 온보딩 보호).

## 5. 미결·CEO 영역 (실행 안 함)
- **라이브 DB의 NULL subject_code user 0건 최종 확인**: `SELECT COUNT(*) FROM users WHERE subject_code IS NULL`은 RDS(EC2 전용 VPC) 접속 필요 → §12·§19로 코드 작업자 금지. 코드/문서 근거상 0이나, 출시 전 CEO/EC2에서 1회 확인 권장.
- **run_tests.py**: 베이스라인부터 Werkzeug 3.x `set_cookie()` 시그니처 변경으로 깨진 stale 복제 하네스(정식 스위트는 tests/test_auth.py). 본 작업과 무관, 미수정.

## 6. 다음 단계
Codex 외부 검증 → CEO 최종 승인.
