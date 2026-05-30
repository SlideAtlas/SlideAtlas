# SlideAtlas JWT 인증 보안 결함 수정 완료 보고서 (v2)

**작성일**: 2026-05-30  
**보고 대상**: CEO 김보람  
**작업 범위**: JWT 인증 보안 결함 수정 2회차 + 계정 잠금·재발송 기능 추가

---

## 1. 한 줄 요약

1회차에서 발견된 3개 치명 결함(타일 인증 미적용, CSRF 미검증, Presigned URL 미구현)을 전부 수정했고, 신규 기능(계정 잠금, 인증코드 재발송, 구독 만료 매요청 차단, 탈옥 방어)을 추가했습니다. 테스트 37개 전부 통과. 2차 보안 검증에서 1회차 FAIL 3건이 PASS로 전환됐으나, 신규 FAIL 3건이 추가 발견되어 2차 수정까지 완료했습니다.

---

## 2. 완료한 것 (체크리스트)

### 1회차 FAIL → 수정 완료
- [x] **[P0] 슬라이드/타일/DZI/썸네일/EC2 프록시 라우트에 @login_required 적용**
  - /viewer/<slide_id>, /slides: @page_login_required + institution_id 필터
  - /dzi/*.dzi, /dzi/*_files/*, /thumbnail/*, /ec2tile/*, /api/chat: @login_required
  - _slide_access_allowed()에서 institution_id + is_public 이중 검사
- [x] **[P1] CSRF 더블서밋 검증 구현**
  - login_required의 POST/PUT/DELETE/PATCH에서 X-CSRF-Token 헤더 ↔ csrf_token 쿠키 대조
  - secrets.compare_digest로 타이밍 공격 방지
- [x] **[P1] 타일 접근 토큰 TTL 5분 구현 (Presigned URL 대체)**
  - generate_tile_token(user_id, institution_id, slide_id): HMAC-SHA256, exp 5분
  - 뷰어 로드 시 토큰 발급 → 모든 타일 URL에 ?t= 포함 (OpenSeadragon getTileUrl 오버라이드)
  - 모든 타일/DZI 라우트에서 verify_tile_token() 검증

### 신규 기능 추가
- [x] **계정 잠금**: 24시간 내 10회 실패(비밀번호+인증코드 합산) → status='locked', locked_at 기록. 24시간 경과 시 자동 해제. FOR UPDATE로 동시성 방어.
- [x] **인증코드 재발송**: POST /api/auth/resend-code. 1분 쿨다운, 24시간 5회 한도. locked/suspended 차단. FOR UPDATE 경쟁조건 방어.
- [x] **구독 만료 매 요청 검사**: _authenticate()에서 매 요청 institutions.subscription_end 확인. 만료 시 즉시 SUBSCRIPTION_EXPIRED(401). 기존 24h 세션 악용 차단.
- [x] **/api/chat 탈옥 방어**: 클라이언트 system 파라미터 무시, 서버 고정 가드레일 사용.
- [x] **is_public=FALSE 라이선스 격리**: _slide_access_allowed()에서 is_public 플래그 검사. 비공개 슬라이드 일반 사용자 접근 차단.

### DB 스키마 추가 (db/auth_schema.sql)
- [x] users 테이블: failed_attempts, failed_window_start, locked_at 컬럼 추가
- [x] 기존 v1 테이블 (institution_rosters, email_verifications) 포함 멱등 SQL 완성
- [ ] **RDS 실행 미완료** — CEO 승인 후 EC2에서 실행 필요 (아래 §5 참조)

### 테스트
- [x] **기존 26개 모두 통과 유지**
- [x] **신규 11개 추가 통과**: 계정잠금 4개, resend-code 5개, CSRF 2개
- [x] **최종 합계: 37/37 PASS** (Python 3.14.4, pytest-9.0.3)

---

## 3. 검증 결과 (2회차)

### 1차 검증 (security-reviewer): PASS 11 / FAIL 3 / WARNING 2

**1회차 FAIL → PASS 전환 (3건 모두 해결)**
- 슬라이드/타일 라우트 인증 → PASS
- CSRF 검증 → PASS
- Presigned URL TTL → PASS

**신규 FAIL (2차 수정으로 해결)**
1. is_public=FALSE 비공개 슬라이드 접근 → **수정 완료 (Fix2)**
2. /api/chat system 프롬프트 클라이언트 주입 → **수정 완료 (Fix2)**
3. subscription_end 만료 세션 차단 누락 → **수정 완료 (Fix2)**

**남은 WARNING 2건**
- 타일 응답 no-cache 헤더 누락 (no-store만 적용, no-cache는 없음)
- 마이그레이션 스키마-코드 배포 순서 강제 장치 부재

### 2차 검증 (Codex): PASS 2 / FAIL 1 / WARNING 3

**신규 FAIL → 수정 완료**
1. resend-code 쿨다운·한도 경쟁조건 → **수정 완료 (FOR UPDATE 추가)**

**남은 WARNING 3건**
- 개별 타일/EC2 프록시의 DB 기관 재검증 없음 (타일 토큰으로 대체, 방어 심도 제한)
- admin 라우트 CSRF 미적용 (JWT 인증 범위 외, 별도 세션 인증)
- admin 비밀번호 기본값 코드 존재 (환경변수 설정 권장)

### 두 검증이 엇갈린 항목

| 항목 | 1차 판정 | 2차 판정 | 차이 원인 |
|------|---------|---------|----------|
| 타일 라우트 기관 격리 | PASS | WARNING | 1차: 토큰에 institution_id 포함으로 충분. 2차: DB 재검증 부재로 방어 심도 부족 |
| CSRF 검증 | PASS | WARNING | 1차: JWT API 범위 내 PASS. 2차: admin API에도 CSRF 없어 WARNING |
| resend-code 경쟁조건 | 미검토 | FAIL | 2차만 발견, Fix2에서 수정 완료 |
| is_public 격리 | FAIL | 미언급 | 1차만 발견, Fix2에서 수정 완료 |

---

## 4. 미완성·막힌 것

### A. RDS 마이그레이션 미실행 [CEO 승인 필요]
- 현재: db/auth_schema.sql 완성, RDS에 미적용
- 사유: AWS CLI 미설치, EC2 Instance Connect 로컬 실행 불가
- 영향: 코드 배포해도 `failed_attempts`, `locked_at` 컬럼 없어 계정 잠금 기능 오류 발생
- 실행 명령 (AWS 콘솔 EC2 Instance Connect에서):
  ```
  psql -h slideatlas-db.c94iwikwox6l.ap-northeast-2.rds.amazonaws.com \
       -U slideatlas_admin -d slideatlas -p 5432 \
       -f db/auth_schema.sql
  ```

### B. 남은 WARNING 항목 [다음 스프린트 권장]
- **타일 no-cache 헤더**: Cache-Control: no-store만 있고 no-cache 없음 (CLAUDE.md §8 요구)
- **admin CSRF**: /admin/api/* 라우트에 CSRF 검증 없음 (별도 세션 인증 사용 중)
- **admin 기본 비밀번호**: 환경변수로 설정하도록 안내 필요

### C. 미완성 기능 (원래 범위 외)
- 기관 관리자 계정 잠금 수동 해제 UI (/portal)
- 계정 잠금 알림 이메일

---

## 5. CEO 결정사항

1. **[즉시] RDS 마이그레이션 실행**: AWS 콘솔 → EC2 Instance Connect → 위 psql 명령 실행. 마이그레이션 후 코드 배포해야 계정 잠금 기능 작동.

2. **[선택] Render 재배포**: 코드 변경사항을 Render에 반영하려면 GitHub push 후 자동 배포 대기 (또는 수동 배포).

3. **[차기] admin CSRF 추가 여부**: 현재 admin은 Flask session 기반. v1.0 런칭 전 CSRF 추가할지 결정 필요.

4. **[차기] no-cache 헤더 추가 여부**: no-store만으로 충분한지 (실제 라이선스 계약 요건 확인 필요).

---

## 6. 다음 단계

1. [필수] RDS 마이그레이션 실행 (CEO 직접)
2. [필수] Render 재배포 (GitHub push)
3. [차기] 포털 명단 관리 구현 (/portal) — §9 기관 관리자 기능
4. [차기] 동적 워터마킹 구현
5. [차기] admin CSRF 추가
6. [완료 후] 전체 QA 5대 체크리스트 최종 점검 + CEO 승인

---

생성: Claude Code 오케스트레이터 | 2026-05-30 v2
