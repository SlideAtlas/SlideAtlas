# SlideAtlas JWT 인증 백엔드 작업 완료 보고서

**작성일**: 2026-05-30  
**보고 대상**: CEO 김보람  
**작업 범위**: JWT 인증 백엔드 구축 (프론트엔드 제외)

---

## 1. 한 줄 요약

JWT 인증 백엔드(회원가입·인증코드·로그인·로그아웃 API, 접근 제어 데코레이터)를 Flask에 구현했고 테스트 26개 전부 통과했습니다. 단, 보안 검증 2회에서 "타일/슬라이드 라우트에 로그인 검사가 없다"는 치명적 결함이 공통 발견되어 현재 상태로 운영 배포를 권장하지 않습니다.

---

## 2. 완료한 것 (체크리스트)

### 구현 완료
- [x] 회원가입 API (POST /api/auth/register): 기관 명단 대조 → 불일치 시 "과 사무실 문의", 일치 시 인증코드 이메일 발송
- [x] 인증코드 확인 API (POST /api/auth/verify-email): 10분 만료, 5회 오입력 시 코드 폐기, 정원 초과 동시성 방어
- [x] 로그인 API (POST /api/auth/login): 활성 계정만 허용, 구독 만료 차단, 기존 세션 무효화
- [x] 로그아웃 API (POST /api/auth/logout)
- [x] 내 정보 조회 (GET /api/auth/me)
- [x] JWT 발급: HttpOnly + Secure + SameSite=Strict 쿠키 저장, CSRF 토큰 발급
- [x] 접근 제어 데코레이터 (@login_required, @role_required): 매 요청 session_token DB 대조
- [x] DB 마이그레이션 SQL (db/auth_schema.sql): institution_rosters, email_verifications 테이블, BEGIN/COMMIT 트랜잭션
- [x] API 명세서 (AUTH_API_SPEC.md): 프론트 연동용 문서
- [x] CLAUDE.md §7 스키마 업데이트
- [x] pytest 26개 전부 통과 (Python 3.14.4 환경, 실제 실행 확인)

### §12-4 QA 체크리스트 대응

| 항목 | 상태 |
|------|------|
| JWT 토큰 변조 공격 방어 | PASS |
| session_token 1기기 동시접속 제어 | PASS |
| 인증코드 브루트포스 방어(5회+FOR UPDATE) | PASS |
| TO 정원 초과 동시성 방어(FOR UPDATE) | PASS |
| DB 트랜잭션 + 에러 시 Rollback | PASS |
| 민감정보 코드 하드코딩 없음 | PASS |
| 브라우저 캐시 no-store (인증 응답) | PASS |
| 동시 로그인 레이스컨디션 방어 | PASS |
| subscription_end 만료 차단 (로그인 시) | PASS |
| 슬라이드/타일 라우트 인증 적용 | FAIL (미구현) |
| CSRF 토큰 검증 로직 | FAIL (발급만 됨) |
| Presigned URL TTL 5분 | FAIL (미구현) |

---

## 3. 검증 결과

### 1차 검증 (security-reviewer): PASS 11 / FAIL 3 / WARNING 3

FAIL:
1. 슬라이드/타일/DZI 라우트에 @login_required 없음 — slide_id만 알면 누구나 접근 가능 [치명]
2. CSRF 토큰 발급만 있고 서버 검증 코드 없음 [높음]
3. 이메일 발송 실패 시 pending 계정이 DB에 남아 재등록 불가 [중간]

WARNING:
4. 로그인 후 24시간 동안 구독 만료 여부 매 요청 미확인
5. autocommit 설정 코드 순서 문제 (경쟁조건 가능)
6. 로그인 응답 코드 차이로 계정 존재 여부 추정 가능

### 2차 검증 (Codex 독립): PASS 7 / FAIL 4 / WARNING 2

FAIL:
1. 슬라이드/타일 라우트 인증·기관 격리 미적용 [치명] (1차와 동일)
2. CSRF 토큰 검증 없음 [높음] (1차와 동일)
3. Presigned URL TTL 5분 미구현 — EC2 타일 프록시가 인증/만료 없이 동작
4. institution_id 기반 멀티테넌시 격리 미적용

WARNING:
1. 타일/DZI/썸네일 응답에 Cache-Control: no-store 없음
2. JWT issuer·audience 정책 미명시

### 두 검증이 엇갈린 항목 (특별 주의)

| 항목 | 1차 | 2차 | 차이 원인 |
|------|-----|-----|----------|
| 브라우저 캐시 no-store | PASS | WARNING | 1차는 인증 응답만 확인, 2차는 타일까지 포함 |
| Presigned URL TTL | 미검토 | FAIL | 1차는 auth 파일 범위만, 2차는 server_render.py 전체 확인 |
| 이메일 발송 실패 pending 계정 | FAIL | 미언급 | 2차에서 독립 발견 못함 |
| autocommit 경쟁조건 | WARNING | 미언급 | 2차에서 미검토 |

엇갈린 항목 중 가장 중요한 것: Presigned URL TTL — 1차가 범위 외로 놓쳤으나 2차가 발견. 현재 EC2 타일 프록시는 인증 없이 누구나 접근 가능하며 TTL 제한이 없음.

---

## 4. 미완성·막힌 것

### 즉시 수정 필요 (운영 배포 전 필수)

A. 슬라이드/타일/DZI 라우트 인증 적용 [치명]
- 현재: /viewer/, /slides, /dzi/*, /thumbnail/*, /ec2tile/* 모두 @login_required 없음
- 영향: slide_id를 알면 로그인 없이 Happy Science 라이선스 콘텐츠 접근 가능
- 해결: 각 라우트에 @login_required + slide.institution_id == g.institution_id 검사 추가

B. CSRF 토큰 서버 검증 로직 [높음]
- 현재: 발급만 되고 검증 코드 없음
- 해결: POST/PUT/DELETE 요청에서 X-CSRF-Token 헤더 검증 추가

C. Presigned URL TTL 5분 [높음]
- 현재: EC2 타일 프록시가 인증·만료 없이 동작
- CLAUDE.md §8 요구사항 미충족

### 개선 권장 (배포 후 단기)

D. subscription_end 매 요청 재확인: 로그인 후 24시간 동안 만료 무시 가능
E. 이메일 발송 실패 시 재발송 엔드포인트: 현재 발송 실패 시 재등록 불가 상태
F. autocommit 코드 순서 정리: except 블록에서 release 후 finally에서 autocommit 설정하는 패턴

---

## 5. CEO 결정사항

다음 사항에 대해 결정이 필요합니다:

1. [RDS 마이그레이션 실행 승인] db/auth_schema.sql이 파일만 생성되고 아직 RDS에 실행되지 않았습니다. EC2에서 실행 명령어를 실행해야 합니다. 승인 여부를 알려주세요.

2. [A항 작업 즉시 진행 여부] 슬라이드/타일 라우트 인증 적용은 Happy Science 라이선스 콘텐츠 보호를 위한 핵심 보안 작업입니다. 다음 작업으로 즉시 진행할지 확인이 필요합니다.

3. [B항 CSRF 구현 범위] SameSite=Strict가 대부분의 CSRF를 차단하지만 CLAUDE.md §8 기준상 완전하지 않습니다. v1.0 런칭 전 필수로 볼지 개선사항으로 볼지 판단이 필요합니다.

4. [E항 이메일 재발송 정책] 발송 실패 시 재등록 불가 문제를 어떻게 처리할지 — 재발송 엔드포인트 추가 or pending 계정 자동 만료 중 선택.

---

## 6. 다음 단계 (우선순위 순)

1. [긴급] RDS 마이그레이션 실행 — CEO 승인 후 db/auth_schema.sql EC2에서 실행
2. [긴급] 슬라이드/타일 라우트 인증 + institution_id 격리 — A항 구현
3. [필수] CSRF 검증 로직 추가 — B항 구현
4. [필수] Presigned URL TTL 5분 — C항 구현
5. [권장] subscription_end 매 요청 재확인 — D항
6. [권장] 이메일 재발송 엔드포인트 — E항
7. [권장] autocommit 순서 정리 — F항
8. [완료 후] 전체 QA 5대 체크리스트 재검증 + CEO 최종 승인

---

생성: Claude Code 오케스트레이터 | 2026-05-30
