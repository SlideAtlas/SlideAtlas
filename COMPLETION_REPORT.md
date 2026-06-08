# COMPLETION_REPORT — LMS 백엔드 2단계(라우트·API·권한 로직) (2026-06-08)

작업일: 2026-06-08 | 작업자: Lead Developer | 기준: CLAUDE.md §8·§9·§15-7·§21
상태: **구현·LMS pytest 22·전수 227 passed(회귀 0)·내부 QA 완료.** 프론트/템플릿은 3단계.

## 1. 범위
교수 수업 페이지(LMS) 백엔드 — 라우트·API·권한 로직만. `server_render.py`에 `/api/chat` 직전 **순수 additive 710줄**(1 hunk). 프론트 미구현(3단계).

**불변 보장**: `_slide_access_allowed`(server_render.py:431)·`_visible_slides`(:472)·auth 인증 로직 **무수정**(git diff: 보호 def 변경 0, 단일 additive hunk). 슬라이드 접근 정책 미변경 — LMS는 기존 게이트를 **호출만** 한다.

## 2. 신규 라우트 (17개, 전부 `/api/courses*`)
| 메서드·경로 | 권한 | 비고 |
|---|---|---|
| POST `/api/courses` | position=='교수'만 | 개설. subject_code=g.subject_code·professor_user_id=g.user_id 고정 |
| GET `/api/courses/mine` | 교수·위임조교 | 내가 개설/위임받은 수업 |
| PUT `/api/courses/<cid>` | 교수·위임조교 | 수업명/학기 수정 |
| DELETE `/api/courses/<cid>` | 교수만 | weeks/slides/assistants/enrollments 명시 CASCADE 정리 |
| POST `/api/courses/<cid>/weeks` | 교수·위임조교 | 주차 추가(빈 주차 empty_reason 허용) |
| DELETE `/api/courses/<cid>/weeks/<wid>` | 교수·위임조교 | 주차 삭제(소속 확인) |
| POST `/api/courses/<cid>/weeks/<wid>/slides` | 교수·위임조교 | ★배치 전 `_slide_access_allowed` 검증, 실패 403. 중복 허용 |
| DELETE `/api/courses/<cid>/weeks/<wid>/slides/<sid>` | 교수·위임조교 | 배치 제거(course/주차 소속 확인, rowcount 404) |
| POST `/api/courses/<cid>/assistants` | 교수만 | 대상=같은 기관·과목·position=='조교' 검증 |
| DELETE `/api/courses/<cid>/assistants/<uid>` | 교수만 | 위임 해제 |
| GET `/api/courses/<cid>/roster` | 교수·위임조교 | 명단(이름·이메일·등록일만, 활동 데이터 무) |
| GET `/api/courses/<cid>/stats` | 교수·위임조교 | **익명 집계만**(개별 행 무) |
| GET `/api/courses/available` | 학생(과목 좌석) | 같은 기관·과목 공개 수업 + enrolled 플래그 |
| GET `/api/courses/enrolled` | 학생 | 내가 등록한 수업 |
| POST `/api/courses/<cid>/enroll` | 학생 | 자유 등록, ON CONFLICT DO NOTHING(멱등) |
| DELETE `/api/courses/<cid>/enroll` | 학생 | 해지(멱등) |
| GET `/api/courses/<cid>` | 같은 기관·과목 좌석 사용자 | 상세(주차+슬라이드 메타). **미등록도 조회 가능**(게이트 아님) |

## 3. 헬퍼 시그니처
- `_course_position(cur, user_id) -> position|None` — users.position 매 요청 DB 재조회(권위, LMS 권한 근거 §6-4).
- `_course_owner_or_assistant(cur, course_id) -> (ok, role_in_course, err)` — course가 `g.institution_id`·`g.subject_code` 소속인지(scope/IDOR) + 교수(`professor_user_id` 일치, role='professor') 또는 위임 조교(`course_assistants`, role='assistant') 판정. 아니면 403. `err`=(json,status)|None. **매 요청 DB 재조회.**
- `_course_in_scope(cur, course_id) -> row|None` — 같은 기관·같은 과목 소속 확인(열람 자격, 수업≠게이트 §21-6).
- `_forbidden_json(msg)` — 공통 403 JSON.

> 헬퍼는 코드베이스 컨벤션(`_sync_member` 등)대로 `cur`를 받아 트랜잭션 내 재사용한다(지시문 개념 시그니처 `(course_id)`에 cur 추가).

## 4. 권한 매트릭스 구현 위치
- **개설=교수만**: `api_course_create`가 `_course_position(cur, g.user_id) != '교수'` → 403. (조교 신규개설 불가.)
- **편집(수정·주차 추가삭제·슬라이드 배치/제거)=교수·위임조교**: 각 라우트 진입부 `_course_owner_or_assistant`. 학생/행정직원은 professor_user_id도 course_assistants도 아니므로 자동 403.
- **삭제·조교지정·위임해제=교수만**: `_course_owner_or_assistant` 통과 후 `role_in_course != 'professor'` → 403.
- **조교 위임 대상 검증**: `users WHERE id=대상 AND institution_id=g.* AND subject_code=g.* AND position='조교'` 없으면 400 INVALID_TARGET.
- **role(viewer/admin)은 LMS 권한에 일절 미사용** — position과 course 소유/위임만으로 분기.

## 5. 핵심 불변식 준수
- **수업≠접근 게이트(§8)**: 슬라이드 배치 시 `_slide_access_allowed(slide_id)`로 그 슬라이드가 편집자의 과목 구독·배포 범위인지 검증 → 실패 403 `SLIDE_NOT_ALLOWED`. course API는 슬라이드 접근을 새로 부여하지 않음. 상세 조회는 메타(ID·제목·염색)만, /viewer 클릭은 기존 게이트가 최종 판정.
- **scope 강제(§9 IDOR)**: 전 라우트 institution_id·subject_code는 `g.*`에서만 취득, body/쿼리 미참조. 타 기관/타 과목 course_id는 **FORBIDDEN(존재 은닉)**.
- **개인정보 익명(§15-7)**: `/stats`는 수업 전체 집계 숫자만(enrolled_count·active_recent_count·inactive_count·placed/viewed_slide_count·slide_view_rate). 학생별 행·user_id·email·이름 **무반환**(0나눗셈 가드). access_logs 집계는 `al.institution_id`·`al.subject_code` 스냅샷(NULL 과거 로그 제외)이며 '이 수업을 통한 열람'이 아니라 '등록 학생의 해당 과목 활동'임을 주석 명시. `/roster`는 이름+이메일+등록일만(활동/접속 컬럼은 SELECT 자체에 없음).
- **트랜잭션·커넥션**: 상태변경 전부 `@login_required`+CSRF(interceptor 전제), 명시 트랜잭션(autocommit=False), **`finally`에서 autocommit 복원 + `release_db_conn`** — 조기 return도 finally를 거쳐 누수 0(기존 portal 일부 조기-return 누수 패턴을 답습하지 않음).

## 6. 테스트 (tests/test_lms.py, 22개)
지시 ①~⑧ 전부 + 보강:
- ① 학생 개설→403 / ② 위임 없는 조교 편집→403(+위임 조교 편집 200) / ③ 비구독·미배포 배치→403 SLIDE_NOT_ALLOWED(+게이트 통과 시 200) / ④ 타기관·타과목 IDOR→403(+위임 조교의 수업 삭제 403) / ⑤ 자유 등록·중복 멱등(ON CONFLICT DO NOTHING 단언)+타스코프 404 / ⑥ 미등록 학생 상세 조회 200(enrolled=False) / ⑦ roster·stats를 학생·타기관·미위임 조교 호출→403 / ⑧ stats 응답에 user_id·email·이름·학생별 행 부재 단언(전 값 정수 집계)+0가드.
- 개설 성공 시 INSERT 파라미터가 g 값(CNU/user 5)임을 단언(scope), 조교 위임 대상 position 검증(400).
- **DB는 mock**(라우트 cursor fetch 시퀀스 정밀 모킹). CSRF는 `_csrf_ok` 패치로 통과.

## 7. 검증 결과
- `tests/test_lms.py` **22 passed** / 전수 **pytest 227 passed**(205→227, 회귀 0).
- `server_render.py` AST 파싱 OK. git diff: **순수 additive 710줄 단일 hunk**, 보호 def(_slide_access_allowed·_visible_slides) 변경 0.

## 8. 한계·미완 (숨기지 않음)
- **프론트/템플릿 0**: 3단계(home.html 수업 탭 연동·교수 편집 화면·학생 수강 화면).
- **favorites·마이페이지**: 이번 범위 밖(4단계).
- **course_week_slides display_order 재정렬 API 없음**: 배치/제거만. 순서 조정은 3단계 UI 요구 시.
- **라이브 DB 미검증**: LMS 6테이블은 마이그레이션(CEO 실행 대기, `db/lms_and_viewer_role_migration.sql`) 적용 후에야 실동작. 본 작업은 마이그레이션 미실행(금지) — 코드만.
- CLAUDE.md 미수정(지시 — 묶음 끝 §21·D27 일괄 갱신).

## 9. 배포 / 남은 게이트
- 커밋·push origin/main 수행(지시). **EC2 git pull + 재기동 + LMS 마이그레이션(아직 미적용 시)은 CEO**(인프라/RDS 변경 없음 — 코드만).
