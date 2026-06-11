# COMPLETION REPORT — LMS 3단계-B (학생 프론트)

**일자**: 2026-06-11 · **브랜치**: main · **기준선**: pytest 263 → **274** (회귀 0) · push 완료(`24033c8`)

학생 LMS 프론트 3종 구현: 홈 수업 탭 / 수업 상세 `/course/<id>` / 마이페이지 `/mypage`.
교수 화면(3단계-A)·슬라이드 접근 판정은 손대지 않음.

---

## 1. 신규/변경 파일

| 파일 | 변경 | 비고 |
|------|------|------|
| `templates/home.html` | 수업 탭 placeholder → 실제 UI(CSS+JS) | 전체 탭 무변경, home 자체 디자인 유지 |
| `templates/course.html` | **신규** | 수업 상세(lms.css + 3단계-A topbar 재사용) |
| `templates/mypage.html` | **신규** | 프로필·비번폼·즐겨찾기·열람기록 |
| `server_render.py` | +219 (기존함수 수정은 api_course_detail 1건) | 신규 라우트 6 + `api_course_detail` 표시필드 보강 |
| `static/css/lms.css` | +54 | 수업상세·마이페이지 컴포넌트(모노폰트 미사용) |
| `tests/test_lms.py` | 상세 3건 mock shape 갱신 | 표시필드 보강 반영(organ 컬럼+교수/과목 fetchone) |
| `tests/test_lms_student_pages.py` | **신규** 11건 | 페이지 권한·API scope·IDOR·게이트 |

---

## 2. 새 라우트

| 메서드·경로 | 데코레이터 | 용도 | scope/게이트 |
|---|---|---|---|
| `GET /course/<int:cid>` | `@page_login_required` | 수업 상세 셸 | admin-only→/portal. scope·존재는 `GET /api/courses/<cid>`가 판정 |
| `GET /mypage` | `@page_login_required` | 마이페이지 셸+프로필 | 프로필 서버 렌더(Jinja escape) |
| `GET /api/favorites` | `@login_required` | 내 즐겨찾기 목록 | **scope=g.user_id**, deployed+본인과목 |
| `POST /api/favorites/<slide_id>` | `@login_required` | 즐겨찾기 추가 | g.user_id + **`_slide_access_allowed` 게이트 읽기** |
| `DELETE /api/favorites/<slide_id>` | `@login_required` | 즐겨찾기 해제 | scope=g.user_id (본인 행만, 멱등) |
| `GET /api/me/history` | `@login_required` | 최근 열람 기록 | **scope=g.user_id**, deployed+본인과목 |

---

## 3. 호출/신설한 API

- **호출(기존, 무수정)**: `GET /api/courses/enrolled`·`/api/courses/available`(B-1), `POST/DELETE /api/courses/<cid>/enroll`(B-2).
- **보강(표시필드만, 권한/scope·deployed 필터 무변경)**: `GET /api/courses/<cid>` → 슬라이드 `organ`(load_slides 'system' 자유텍스트 표시축 §6-1) + course `professor_name`·`subject_name`.
- **신설**: favorites GET/POST/DELETE, me/history (위 표).

---

## 4. 불변식 검증 (security-reviewer 독립 검증 — FAIL 0)

1. `_slide_access_allowed`·`_visible_slides`·`_course_owner_or_assistant`·`auth/` **git diff 변경 0**.
2. `api_course_detail` scope(`_course_in_scope`)·`deploy_status='deployed'` 필터 그대로(표시필드만 보강).
3. 신규 favorites/history **scope=g.user_id 강제** — body/쿼리/경로 user_id 미참조(IDOR 불가, 쿼리 `?user_id=999` 무시 테스트로 단언).
4. `POST /api/favorites` 가 게이트 읽기로 접근권 없는 슬라이드 북마크 차단(존재 probing·메타 누수 차단).
5. favorites/history 표시 deployed+본인과목 한정(타 과목/미배포 누수 없음).
6. XSS: 클라이언트 렌더 esc() + href encodeURIComponent + 학기 칩 textContent. CSRF: 상태변경 `@login_required`(interceptor 자동 주입).

---

## 5. 회귀 결과

`pytest tests/` → **274 passed**(263→274, +11, 회귀 0).

---

## 6. 단계별 커밋

| 단계 | 커밋 | 내용 |
|------|------|------|
| B-1 | `a15f869` | 홈 수업 탭(학기 칩·내 수업·개설 수업) |
| B-2 | `96eb329` | 수업 상세 `/course/<id>` + 표시필드 보강 |
| B-3 | `24033c8` | 마이페이지 `/mypage` + 즐겨찾기·열람기록 API |

---

## 7. 설계 결정 / 보고 사항

- **썸네일 = 플레이스홀더(마이크로스코프 아이콘)**: 1차 사양서(목업)가 실이미지가 아닌 아이콘 플레이스홀더를 렌더하고, "게이트 무관 표시 필드만" 원칙상 실썸네일 URL은 타일토큰(=게이트 발급)이 필요하므로 목업대로 채택(기존 home '전체' 탭과 동일 패턴). 추후 실썸네일 필요 시 게이트 통과 슬라이드 한정 토큰 발급으로 확장 가능.
- **부채 D31(신설 제안)**: 학생 비밀번호 변경 API 부재 → mypage 비번 폼은 표시용(안내 토스트)+TODO 주석. CLAUDE.md는 본 지시대로 미수정(LMS 묶음 끝 §18 일괄 갱신 시 D31 추가 제안).
- CLAUDE.md 미수정(지시 준수). progress.md 단계별 append 완료.
