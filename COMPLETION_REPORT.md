# COMPLETION_REPORT — LMS 2단계 외부검증 반영 수정 (2026-06-08)

작업일: 2026-06-08 | 작업자: Lead Developer | 기준: CLAUDE.md §8·§9·§15-7·§21
상태: **구현·tests/test_lms.py 34·전수 239 passed(회귀 0)·내부 QA 완료.** 변경 파일 = `server_render.py`(LMS만) + `tests/test_lms.py`.

## 1. 범위 / 불변
LMS 라우트·헬퍼의 외부검증(Codex/Gemini) 4건 반영. `_slide_access_allowed`·`_visible_slides`·auth 인증 로직 **무수정**(git diff: 보호 def 변경 0). `.sql` 마이그레이션·`CLAUDE.md` **미수정**.

## 2. 수정 내역 (파일:라인)

### 수정1 — 동적 position 재검증 (`_course_owner_or_assistant`, server_render.py:1945)
**변경 전**: course scope 확인 후, `professor_user_id==g.user_id`면 professor, `course_assistants` 행 있으면 assistant 통과. (지위 강등 무시 — 소유/위임 행만 보면 강등된 교수도 편집 가능.)
**변경 후**: scope 확인 후 `pos = _course_position(cur, g.user_id)`(같은 cursor/트랜잭션 재조회) 추가 →
- professor 통과 = `professor_user_id 일치 AND pos=='교수'`
- assistant 통과 = `course_assistants 행 존재 AND pos=='조교'`
- 둘 다 아니면 403 FORBIDDEN.
**효과**: 교수→학생 강등·조교 박탈 시 소유/위임 행이 남아 있어도 기존 수업 편집·삭제·주차·배치 **즉시 차단**(인증 DB 권위 §8 정합).

### 수정2 — DELETE /enroll scope 재검증 (`api_course_unenroll`, server_render.py:2578)
삭제 전 `_course_in_scope(cur, cid)` 추가 — cid가 현재 scope(`g.institution_id`·`g.subject_code`) 소속이 아니면 POST /enroll와 동일하게 404, **DELETE 미실행**(cross-scope 수강행 삭제 차단). position 무관(기등록 정리 허용).

### 수정3 — 상세 미배포 슬라이드 필터 (`api_course_detail`, server_render.py:2627)
주차 슬라이드 쿼리의 `course_week_slides` LEFT JOIN ON 절에 `AND cws.slide_id IN (SELECT id FROM slides WHERE deploy_status='deployed')` 추가. 미배포(qc_pending·rejected) 슬라이드 배치는 행 자체가 조인에서 빠져 **빈 주차로 표시**(주차 행은 유지), 메타데이터 비노출(`_visible_slides` 필터 원칙 응용). 일반 사용자 경로는 무조건 deployed만(편집자용 미배포 표시는 3단계).

### 수정4 — enroll position 가드 (`api_course_enroll`, server_render.py:2549)
`_course_in_scope` 통과 후 `_course_position(cur, g.user_id)`가 `'학생'·'조교'`일 때만 등록, 그 외(교수·행정직원·position NULL) → 403 `ENROLL_NOT_ALLOWED`. 해지(DELETE)는 position 무관(수정2).

## 3. 신규 테스트 (tests/test_lms.py, +12 → 34)
- 수정1: 교수→학생 강등 후 PUT/DELETE/주차추가/배치 전부 403(배치는 권한 실패가 `_slide_access_allowed` 호출보다 먼저임 단언) + 조교 박탈 후 위임 수업 편집 403.
- 수정2: DELETE /enroll cross-scope cid → 404 + DELETE 미실행 단언 / in-scope → 200, DELETE 1회.
- 수정3: 상세 응답에 미배포 슬라이드 미포함(빈 주차) + SQL에 `deploy_status='deployed'` 포함 단언.
- 수정4: 학생·조교 enroll → 200(INSERT 1회) / 교수·NULL enroll → 403 ENROLL_NOT_ALLOWED(INSERT 미실행).
- 기존 22건: 권한 헬퍼 cursor 시퀀스에 position SELECT가 추가돼 fetchone side_effect 갱신(로직 동일, 회귀 아님).

## 4. 검증 결과
- `tests/test_lms.py` **34 passed** / 전수 **pytest 239 passed**(227→239, 회귀 0).
- git diff: `server_render.py`(LMS 영역만)+`tests/test_lms.py` 2파일. 보호 def·auth·`.sql`·`CLAUDE.md` 변경 0.

## 5. TOCTOU 평가 (Codex Medium)
수정1의 position 재검증은 **상태변경과 같은 트랜잭션**(state-change 라우트 `autocommit=False`) 안에서 수행 — 권한 SELECT와 후속 UPDATE/DELETE 사이에 커밋 경계가 없어 TOCTOU 창이 **대폭 축소**됐다. **완전 제거는 아님**: `users` 행을 `FOR UPDATE`로 잠그거나 SERIALIZABLE을 쓰지 않으므로, position SELECT 직후~mutation 직전(마이크로초)에 커밋된 동시 강등은 구 스냅샷이라 미포착될 수 있다. 잔여 위험은 낮음(동시 강등은 드묾) — 완전 차단이 필요하면 권한 행 `SELECT ... FOR UPDATE` 추가가 후속 과제(v1.5 Locust D14 시점 재검토).

## 6. 한계·미완
- 프론트/템플릿 미구현(3단계). favorites·마이페이지(4단계).
- LMS 6테이블 라이브 동작은 마이그레이션(`db/lms_and_viewer_role_migration.sql`, CEO 실행 대기) 적용 후. 본 작업 코드만(마이그레이션 미실행·미수정).
- CLAUDE.md 미수정(묶음 끝 §21·D27 일괄).

## 7. 배포 / 남은 게이트
- 커밋·push origin/main 수행. **EC2 git pull + 재기동 + LMS 마이그레이션(미적용 시)은 CEO**(RDS/인프라 변경 없음 — 코드만).
