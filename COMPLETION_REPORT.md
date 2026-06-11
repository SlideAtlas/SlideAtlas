# COMPLETION_REPORT — organ 정규화 검증 반영(Codex/Gemini) (2026-06-11)

작업일: 2026-06-11 | 작업자: Lead Developer(Claude) | 기준: CLAUDE.md §18 D28·§12·§0
상태: **구현 완료 · 전수 pytest 263 passed(261→263, 회귀 0) · §0·인증·게이트 무변경.**
대상: 로컬 커밋 `a97b381`(organ 통제어휘 정규화) 위 후속 수정. **코드·verify.sql만** — 라이브 RDS·SSH·마이그레이션 실행 없음(§12). 재검증 → CEO 배포(push 없음).

## 변경 파일
| 파일 | 변경 |
|------|------|
| `server_render.py` | 수정1(api_slide_add organ_code 필수)·수정3(admin_save_slide 410) |
| `templates/admin/slides.html` | 수정1(필수 드롭다운)·수정2(loadOrgans fail-loud) |
| `db/organs_taxonomy_verify.sql` | 수정4(\echo 안내) |
| `db/organs_taxonomy_migration.sql` | 운영5(배포 순서 명시) |
| `tests/test_auth.py` | 신규 회귀 2건 |

## 수정 1 (Med#1) — organ_code 필수
- **백엔드** `api_slide_add`: `organ_code` 누락/빈 값이면 `400 'organ_code(장기)는 필수입니다'` 거부. 기존엔 미등록 코드만 400이고 누락은 NULL INSERT 허용 → 이제 신규 INSERT 불가. organs 마스터 대조·`organ`=name_ko 병기는 유지(표시 경로 무변경).
- **프론트** 개별추가 드롭다운: `(미지정)` 제거 → `장기 선택` 비활성 플레이스홀더 + `required`. `submitAdd()`가 미선택 시 차단(서버도 400).
- ⚠ **기존 NULL organ_code 행(D24 잔재)은 건드리지 않음** — 신규 INSERT 경로에만 강제.

## 수정 2 (High) — 프론트 fail-loud
- `loadOrgans()`: organs fetch 실패(`!res.ok || !data.ok` 또는 catch) 시 등록 submit 비활성(`#a-submit`) + 에러 표시(`#a-org-err` "장기 목록 로드 실패 — 새로고침"). 실패를 삼키고 미지정 등록을 허용하던 동작 제거. `_organsOk` 플래그로 `submitAdd()`에서 이중 차단.

## 수정 3 (Med#2, ★ CEO 판단) — 레거시 하드블록
- `admin_save_slide`(`/admin/api/slide`): 인증·CSRF·세션잠금 데코레이터/라우트 **존치**(tests/test_auth.py의 401/403 게이트 검사 무영향), organ 자유텍스트 쓰기(organ_code 정규화 우회)에 도달하기 전 **410 Gone** 반환. 본문 INSERT/UPDATE 제거. 슬라이드 추가는 `/admin/api/slides/add`(통제어휘)만 사용.
- CEO가 불요로 판단하면 이 수정만 단독 revert 가능(다른 수정과 독립).

## 수정 4 (Gemini Low) — verify 가독성
- `db/organs_taxonomy_verify.sql` [1]~[8] 각 쿼리 앞 `\echo '=== [n] … ==='` 안내 추가(psql 출력에서 어느 점검인지 식별).

## 운영 5 — 배포 순서(코드 아님)
- `db/organs_taxonomy_migration.sql` 헤더에 **"migration → verify → 코드 배포"** 순서 명시(코드가 organs 테이블·slides.organ_code 컬럼 참조).

## 테스트 영향 처리
- **영향 점검**: `api_slide_add`(`/admin/api/slides/add`)를 성공 기대로 호출하는 기존 테스트 **없음**. `admin_save_slide`(`/admin/api/slide`)를 호출하는 기존 테스트 4건은 모두 게이트 단계(401/403)에서 본문 미도달 → 410 무영향.
- **신규 2건**: `test_slide_add_requires_organ_code`(게이트 통과 후 organ_code 누락 → 400), `test_legacy_admin_save_slide_is_gone`(게이트 통과 후 → 410).
- 전수 **263 passed(261→263, 회귀 0)**.

## 무변경 확인
- `git diff`: `_authenticate`·`subscriptions`·`max_seats`·`_slide_access_allowed`·`_visible_slides` 변경 0, `auth/` 변경 0. §0(구독·좌석·접근·인증)·표시 별칭·게이트 무변경.
- CLAUDE.md 미수정. 마이그레이션 SQL 로직 무변경(\echo·헤더 주석만).
