# SlideAtlas 인증 API 명세 (프론트 연동용)

> 베이스 경로: `/api/auth`
> 모든 응답은 JSON. 모든 응답 헤더에 `Cache-Control: no-store` 포함.
> 인증 쿠키는 `Secure` 속성이므로 HTTPS 환경에서만 전송됨 (로컬 테스트는 https 필요).

---

## 공통 응답 형식

성공:
```json
{ "success": true, "data": { ... } }
```

실패:
```json
{ "success": false, "error": "ERROR_CODE", "message": "사용자용 메시지" }
```

세션 만료/무효 (HTTP 401):
```json
{ "success": false, "error": "SESSION_EXPIRED", "message": "다시 로그인하세요" }
```

---

## 쿠키 / CSRF 토큰

로그인 또는 이메일 인증 성공 시 서버가 두 쿠키를 내려준다.

| 쿠키 | 속성 | 용도 |
|------|------|------|
| `access_token` | HttpOnly, Secure, SameSite=Strict, max-age=86400 | JWT. JS에서 읽을 수 없음. 요청 시 자동 전송됨 |
| `csrf_token` | Secure, SameSite=Strict (HttpOnly 아님) | JS가 읽어 변경 요청 헤더에 실어보내는 값 |

프론트는 상태 변경 요청(POST/DELETE 등) 시 다음을 권장:
```js
fetch("/api/auth/logout", {
  method: "POST",
  credentials: "include",            // 쿠키 동봉 필수
  headers: { "X-CSRF-Token": getCookie("csrf_token") }
});
```
- JWT는 쿠키로 자동 전송되므로 `Authorization` 헤더는 불필요.
- `credentials: "include"`를 빠뜨리면 쿠키가 안 실려 401이 난다.

JWT payload(참고, 서버 검증용):
```
sub(int 사용자ID) / institution_id / role / session_token(uuid) / is_special(bool) / iat / exp(발급+24h)
```
매 요청마다 서버가 payload의 `session_token`을 DB의 최신 값과 대조한다.
다른 기기에서 로그인하면 DB의 session_token이 갱신되어 이전 토큰은 즉시 401(`SESSION_EXPIRED`).

---

## 1. 회원가입 — `POST /api/auth/register`

요청:
```json
{ "email": "kim@yonsei.ac.kr", "password": "비밀번호",
  "name": "김학생", "role": "student", "institution_id": "YU" }
```
- `role`: `student` | `professor` | `ta`

성공 (200):
```json
{ "success": true, "data": { "message": "인증코드가 이메일로 발송되었습니다" } }
```
이후 사용자는 메일로 받은 6자리 코드를 `verify-email`로 제출한다.
(이 단계에서는 토큰이 발급되지 않는다.)

에러:
| HTTP | error | 의미 |
|------|-------|------|
| 400 | MISSING_FIELDS | 필수 입력값 누락 |
| 403 | ROSTER_MISMATCH | 기관 명단에 (이메일+역할) 일치 항목 없음 → "과 사무실에 문의하세요" |
| 404 | INSTITUTION_NOT_FOUND | institution_id 없음 |
| 409 | EMAIL_EXISTS | 이미 가입된 이메일 |
| 409 | CAPACITY_EXCEEDED | 정원(max_users) 초과 → "정원이 초과되었습니다" |
| 502 | EMAIL_SEND_FAILED | 인증코드 발송 실패 |
| 500 | SERVER_ERROR | 서버 오류 |

---

## 2. 이메일 인증 — `POST /api/auth/verify-email`

요청:
```json
{ "email": "kim@yonsei.ac.kr", "code": "482913" }
```

성공 (200): `access_token` + `csrf_token` 쿠키 설정 + 본문:
```json
{ "success": true, "data": {
  "user_id": 12, "institution_id": "YU", "role": "student",
  "csrf_token": "..." } }
```

에러:
| HTTP | error | 의미 |
|------|-------|------|
| 400 | MISSING_FIELDS | 이메일/코드 누락 |
| 400 | CODE_MISMATCH | 코드 불일치. 본문에 `remaining`(남은 시도 횟수) 포함 |
| 404 | USER_NOT_FOUND | 인증 대기 사용자 없음 |
| 404 | CODE_NOT_FOUND | 유효 인증코드 없음 |
| 410 | CODE_EXPIRED | 코드 만료(발급 후 10분) |
| 429 | TOO_MANY_ATTEMPTS | 5회 초과 → 코드 폐기, 재발송 필요 |
| 409 | CAPACITY_EXCEEDED | 인증 직전 정원 재검사에서 초과 (동시성 방어) |
| 500 | SERVER_ERROR | 서버 오류 |

CODE_MISMATCH 응답 예:
```json
{ "success": false, "error": "CODE_MISMATCH",
  "message": "인증코드가 일치하지 않습니다", "remaining": 3 }
```

---

## 3. 로그인 — `POST /api/auth/login`

요청:
```json
{ "email": "kim@yonsei.ac.kr", "password": "비밀번호" }
```

성공 (200): `access_token` + `csrf_token` 쿠키 설정 + 본문:
```json
{ "success": true, "data": {
  "user_id": 12, "institution_id": "YU", "role": "student",
  "csrf_token": "..." } }
```
> 로그인 시 새 session_token이 발급되어 기존 기기 세션은 즉시 무효화된다(1기기 동시접속).

에러:
| HTTP | error | 의미 |
|------|-------|------|
| 400 | MISSING_FIELDS | 이메일/비밀번호 누락 |
| 401 | INVALID_CREDENTIALS | 이메일 없음 또는 비밀번호 불일치 |
| 403 | EMAIL_NOT_VERIFIED | 이메일 인증 미완료 → "이메일 인증을 완료하세요" |
| 403 | ACCOUNT_INACTIVE | 비활성 계정 |
| 403 | SUBSCRIPTION_EXPIRED | 기관 구독 만료 → "구독이 만료되었습니다" (결제 유도 팝업) |
| 500 | SERVER_ERROR | 서버 오류 |

---

## 4. 로그아웃 — `POST /api/auth/logout`

- 인증 필요(쿠키). DB의 session_token을 NULL 처리하고 쿠키를 삭제한다.

성공 (200):
```json
{ "success": true, "data": { "message": "로그아웃되었습니다" } }
```
미인증/만료 시 401 `SESSION_EXPIRED`.

---

## 5. 현재 사용자 — `GET /api/auth/me`

- 인증 필요(쿠키).

성공 (200):
```json
{ "success": true, "data": {
  "user_id": 12, "email": "kim@yonsei.ac.kr", "role": "student",
  "institution_id": "YU", "is_special": false, "status": "active",
  "last_login": "2026-05-30T01:23:45+00:00" } }
```
미인증/만료/타기기 로그인 시 401 `SESSION_EXPIRED`.

---

## 세션 만료 처리 (프론트 가이드)

모든 보호 API 호출에서 다음을 공통 처리:
```js
const res = await fetch(url, { credentials: "include", ... });
const json = await res.json();
if (res.status === 401 && json.error === "SESSION_EXPIRED") {
  // 토큰 만료, 변조, 또는 다른 기기 로그인으로 세션 무효화됨
  redirectToLogin("다시 로그인하세요");
}
```
- 401 `INVALID_TOKEN`도 동일하게 로그인 화면으로 보낸다.
- 403 `SUBSCRIPTION_EXPIRED`는 로그인 단계에서 발생 → 결제/문의 안내 팝업.

---

## TO(정원) 초과 시나리오

1. 가입 시점(`register`): `max_users` vs active 유저 수 비교 → 초과면 `CAPACITY_EXCEEDED`.
2. 인증 완료 시점(`verify-email`): institutions 행을 `FOR UPDATE`로 잠그고 active 유저 수를
   재계산. 가입 후 인증 사이에 정원이 차면 이 단계에서 `CAPACITY_EXCEEDED`로 차단(동시성 방어).
   이 경우 사용자는 `pending_verification` 상태로 남으며, 정원 확보 후 재인증하면 활성화된다.
3. `max_users`가 NULL이면 정원 무제한으로 간주.
