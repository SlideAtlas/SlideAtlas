# SlideAtlas 401 에러 코드 세분화 작업 완료 보고서

**작성일**: 2026-05-30  
**보고 대상**: CEO 김보람  
**작업 범위**: JWT 인증 백엔드 401 응답 세분화 + 세션 무효화 주석 명문화

---

## 1. 한 줄 요약

단일 SESSION_EXPIRED 코드를 TOKEN_INVALID/SESSION_REVOKED/SUBSCRIPTION_EXPIRED/TILE_TOKEN_INVALID 네 가지로 세분화했습니다. 프론트엔드 인터셉터가 "재로그인 필요", "다른 기기 로그인 알림", "구독 만료 안내", "타일 새로고침 안내"를 구분 처리할 수 있게 되었습니다. 테스트 45개 전부 통과.

---

## 2. 완료 조건 체크리스트

- [x] `_authenticate()` 내 SESSION_EXPIRED 코드 전량 제거 확인 (0건 잔존)
- [x] TOKEN_INVALID / SESSION_REVOKED / SUBSCRIPTION_EXPIRED 분기 순서 고정
  - ① 유저 미조회 → TOKEN_INVALID
  - ② token_session 없음 → TOKEN_INVALID (SESSION_REVOKED 오발동 방지)
  - ② DB session_token 불일치 → SESSION_REVOKED
  - ③ 구독 만료 → SUBSCRIPTION_EXPIRED
- [x] TILE_TOKEN_INVALID 반환 경로 존재 확인 (`_verify_tile_request`)
- [x] pytest 전체 통과: 기존 40개 + 신규 5개 = **45/45 PASS**
- [x] CLAUDE.md §8 업데이트 완료 (SESSION_EXPIRED → 4개 에러코드 설명)
- [x] progress.md / COMPLETION_REPORT.md 기록 완료

---

## 3. 변경 상세

### `auth/decorators.py` — `_authenticate()` 에러 코드 재설계

| 상황 | 이전 | 변경 후 |
|------|------|---------|
| 쿠키 없음 | SESSION_EXPIRED | TOKEN_INVALID |
| JWT 만료 | SESSION_EXPIRED | TOKEN_INVALID |
| 유저 미조회 (DB) | SESSION_EXPIRED | TOKEN_INVALID |
| 계정 비활성 (status ≠ active) | SESSION_EXPIRED | TOKEN_INVALID |
| DB session_token 불일치 | SESSION_EXPIRED | SESSION_REVOKED |
| 구독 만료 | SUBSCRIPTION_EXPIRED ✓ | SUBSCRIPTION_EXPIRED (유지) |

**분기 순서 고정 이유**: `token_session`이 없는 상태에서 `db_session != token_session` 비교를 먼저 하면 `None != None`이 False가 되거나 `None != "uuid"` 가 True가 되어 SESSION_REVOKED가 오발동. 따라서 반드시 `if not token_session → TOKEN_INVALID` 확인 후 불일치 비교 수행.

### `auth/auth.py` — 세션 무효화 지점 주석 명문화

로그인 시 `session_token` 갱신 직전에 아래 주석 추가:
```python
# 기존 세션 무효화 — 이 시점부터 구 토큰 요청은 _authenticate()에서
# SESSION_REVOKED를 반환함. 단일 동시접속 제어의 핵심 지점.
```

### `server_render.py` — `_verify_tile_request()` 에러 코드 교체

`TOKEN_EXPIRED` → `TILE_TOKEN_INVALID` 로 변경.

프론트엔드 인터셉터가 타일 관련 오류를 로그인 세션 오류(SESSION_REVOKED, SUBSCRIPTION_EXPIRED)와 구분하여 처리 가능.

### `CLAUDE.md §8` 보안 아키텍처 업데이트

4개 에러 코드 설명 추가:
- SUBSCRIPTION_EXPIRED (401): 구독 만료
- SESSION_REVOKED (401): 타 기기 로그인
- TOKEN_INVALID (401): 쿠키 없음/만료/삭제
- TILE_TOKEN_INVALID (401): 타일 토큰 검증 실패 (로그인 세션과 무관)

---

## 4. 신규 테스트 (5개)

| 테스트명 | 검증 항목 |
|----------|----------|
| test_token_invalid_no_cookie | 쿠키 없음 → TOKEN_INVALID, SESSION_REVOKED 아님 명시 |
| test_session_revoked_on_db_mismatch | 유효 쿠키 + DB 불일치 → SESSION_REVOKED |
| test_subscription_expired_returns_401 | 구독 만료 → SUBSCRIPTION_EXPIRED |
| test_is_special_subscription_expired_passes | is_special=True + 만료 → 200 정상 통과 |
| test_tile_token_invalid_returns_correct_code | 타일 토큰 없음 → TILE_TOKEN_INVALID |

---

## 5. 에러 코드 전체 현황 (프론트엔드 인터셉터 참조용)

| 코드 | HTTP | 의미 | 프론트 처리 권장 |
|------|------|------|-----------------|
| TOKEN_INVALID | 401 | 쿠키 없음·만료·삭제·유저 미조회 | 로그인 페이지 리다이렉트 |
| INVALID_TOKEN | 401 | JWT 변조 탐지 | 로그인 페이지 + 보안 경고 |
| SESSION_REVOKED | 401 | 타 기기 로그인으로 세션 교체 | "다른 기기 로그인" 모달 → 재로그인 |
| SUBSCRIPTION_EXPIRED | 401 | 기관 구독 만료 | "과 사무실에 문의하세요" 표시 |
| TILE_TOKEN_INVALID | 401 | 타일 접근 토큰 만료/불일치 | "뷰어를 새로고침하세요" (재로그인 불필요) |
| CSRF_INVALID | 403 | CSRF 토큰 검증 실패 | 페이지 새로고침 유도 |

---

생성: Claude Code 오케스트레이터 | 2026-05-30
