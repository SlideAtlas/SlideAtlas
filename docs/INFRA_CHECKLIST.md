# INFRA_CHECKLIST.md — SlideAtlas 환경·인프라 점검 매뉴얼 v1.0

> **이 문서의 존재 이유 (반드시 먼저 읽을 것)**
> Codex·Gemini 등 외부 AI 검증은 **git에 올라간 소스코드만** 본다. 따라서 코드 안에서
> 추론 가능한 결함(IDOR, 인증 우회, SQL 인젝션, 권한 게이트 허점 등)은 잘 잡지만,
> **git 밖에 존재하는 것 — 환경변수 실제 설정값, 인프라 구성, 라이브 DB 데이터 상태, 배포 환경 —
> 은 구조적으로 못 본다.** 코드가 `os.environ.get('JWT_SECRET_KEY')`로 완벽히 작성돼 있어도,
> 그 변수가 실제 서버에 설정됐는지는 코드 리뷰의 사정거리 밖이다.
>
> **실제 사고 (2026-06, 비싼 교훈 → 싸게 얻음)**: JWT_SECRET_KEY가 Render에 설정 안 됐는데
> 코드·프론트·백 외부검증을 다 돌렸어도 아무도 못 잡았다. 코드엔 결함이 없었기 때문이다.
> 이 사각지대(코드 검증 ≠ 환경/인프라 검증)를 사람이 눈으로 메우는 것이 이 문서의 목적이다.
>
> **원칙: 외부 AI 검증은 "코드 한정"임을 항상 의식하고, 환경·구성·데이터·인프라는
> 이 체크리스트로 별도 점검한다.** Codex/Gemini가 OK해도 이 문서를 통과 못 하면 런칭 금지.

> 관련: CLAUDE.md §12(QA 거버넌스), §18(기술부채), §19(인프라 접속정보), §20(이 문서 포인터).
> 본 문서가 인프라·환경 운영 절차의 1차 기준이며, CLAUDE.md와 충돌 시 인프라 영역은 본 문서가 우선.

---

## A. 무엇이 코드 검증의 사각지대인가 (개념 지도)

검증 책임을 두 축으로 분리해 의식한다.

| 영역 | 검증 주체 | 예시 |
|------|-----------|------|
| **코드 로직** | Codex·Gemini·Claude Code QA (§12) | 접근 게이트, IDOR, 인증·세션, CSRF, 권한 분리, SQL 안전성 |
| **환경변수** | ← **이 문서 (사람 점검)** | JWT/ADMIN 시크릿 실제 설정 여부, DB·AWS·API 키, PORT |
| **인프라 구성** | ← **이 문서** | systemd 자동기동, nginx, TLS, 보안그룹, EIP, DNS, S3 정책 |
| **라이브 데이터** | ← **이 문서** (§18 D4b도 동일 취지) | NULL subject_code, 고아 행, 잘린 해시, 시드 정합성 |
| **배포 환경** | ← **이 문서** | 어느 호스트가 실서버인지, 옛 서버 잔존, 헬스체크 |
| **부하·동시성** | Locust (§18 D14, 7월 말) | 좌석 잠금 경쟁, 커넥션 풀 고갈, 타일 폭주 |

> 핵심 문장: **"코드가 맞다 ≠ 배포가 맞다."** 코드는 환경변수를 *읽는 법*을 알 뿐,
> 그 변수가 *실제로 있는지*는 모른다.

---

## B. 런칭 전 종합 체크리스트 (9월 정식 런칭 게이트)

> 사용법: 런칭 직전 이 목록을 **위에서 아래로 한 줄씩 직접 실행·확인**한다.
> AI에게 "확인됐다"고 듣지 말고, 명령 출력 또는 콘솔 화면을 **사람 눈으로** 대조한다.
> 모든 명령은 EC2(Instance Connect)에서 CEO가 직접 실행. AI는 SSH 직접 실행 금지(§12).

### B-1. 환경변수 (가장 비싼 사각지대 — 최우선)

`.env` 13개 키가 **실서버(EC2 ~/SlideAtlas/.env)에 모두 존재하고 값이 비지 않았는지** 확인.
값 자체는 출력하지 말고 **키 존재 + 비어있지 않음**만 본다.

```bash
cd ~/SlideAtlas
# 키 목록만 (값 노출 없이) — 13개가 다 나오는지
grep -oE '^[A-Z_]+=' .env | sort
# 값이 빈 키가 있는지 (= 뒤에 아무것도 없는 줄)
grep -nE '^[A-Z_]+=$' .env && echo "⚠ 위 키는 값이 비었음" || echo "✅ 빈 값 없음"
```

필수 13키 체크 (□에 직접 표시):
- [ ] DB_HOST  [ ] DB_NAME  [ ] DB_USER  [ ] DB_PASSWORD  [ ] DB_PORT
- [ ] ADMIN_SECRET_KEY (미설정 시 앱 기동 실패 = fail-closed, §8/§18 D3)
- [ ] JWT_SECRET_KEY (★ 2026-06 사고 당사자. secrets.token_hex(32)로 생성·고정)
- [ ] ANTHROPIC_API_KEY
- [ ] AWS_ACCESS_KEY_ID  [ ] AWS_SECRET_ACCESS_KEY  [ ] AWS_REGION
- [ ] GMAIL_USER  [ ] GMAIL_APP_PW (→ §18 D2: SES 전환 전까지 임시)
- [ ] PORT (=10000, gunicorn/systemd와 일치)

추가 확인:
- [ ] `.env`가 `.gitignore`에 포함 — `git check-ignore .env` 가 `.env`를 출력하면 OK
- [ ] git에 `.env`가 실수로 커밋된 적 없는지 — `git log --all --oneline -- .env` 가 **빈 결과**여야 함
- [ ] 앱이 실제로 그 변수를 읽고 기동되는지 — `systemctl status slideatlas`가 active이고
      기동 로그에 시크릿 관련 RuntimeError(fail-closed 트립)가 없는지

### B-2. 인프라 구성 — 자동기동 (재부팅 생존)

런칭 후 인스턴스가 재부팅돼도 **모든 서비스가 손 없이 올라와야** 한다.
검증은 말로 하지 말고 **실제 reboot 한 번**으로 한다.

```bash
# 자동기동 등록 여부 (enabled 떠야 함)
systemctl is-enabled slideatlas nginx tileserver 2>&1
# 실제 reboot 검증 (1~2분 후 재접속)
sudo reboot
```
재접속 후:
```bash
systemctl status slideatlas nginx tileserver --no-pager | grep -E "Active:|●"
curl -I https://slide-atlas.net/
```
- [ ] slideatlas.service — enabled + active(running)
- [ ] nginx.service — enabled + active(running)
- [ ] **tileserver — enabled + active(running)** (★ 2026-06 reboot 후 죽어있던 항목.
      수동/nohup 실행이면 systemd 등록 필요 — 부록 F-1 참조)
- [ ] reboot 후 `curl -I https://slide-atlas.net/` → 200

### B-3. 인프라 구성 — 네트워크·TLS·DNS

```bash
# DNS가 EIP를 가리키는지
dig slide-atlas.net +short        # 3.34.35.58
dig www.slide-atlas.net +short    # 3.34.35.58
# TLS 인증서 만료일
echo | openssl s_client -servername slide-atlas.net -connect slide-atlas.net:443 2>/dev/null \
  | openssl x509 -noout -dates
# http→https 강제 리다이렉트
curl -I http://slide-atlas.net/   # 301/308 + Location: https://...
# 자동 갱신 타이머 살아있는지
systemctl status certbot.timer --no-pager | grep Active
```
- [ ] DNS A 레코드 `@`·`www` 둘 다 3.34.35.58 (Gabia)
- [ ] TLS 인증서 유효, 만료 D-30 이상 여유 (Let's Encrypt 90일, 자동갱신)
- [ ] certbot.timer active (자동 갱신 동작)
- [ ] http → https 리다이렉트 정상
- [ ] **보안그룹 인바운드: 22(SSH 제한적)·80·443만**. 그 외 포트(10000 gunicorn,
      타일서버 포트, 5432)는 **외부에 절대 노출 금지** — AWS 콘솔에서 직접 눈으로 확인
- [ ] 10000(gunicorn)은 127.0.0.1 바인드만 (외부 차단) — `ss -tlnp | grep 10000` 이 127.0.0.1만

### B-4. 데이터 저장소 — RDS·S3

```bash
# RDS는 EC2에서만 붙는지 (외부 차단 = VPC 프라이빗) — §19
psql -h <RDS_ENDPOINT> -U slideatlas_admin -d slideatlas -c "SELECT 1;"  # EC2에선 성공
```
- [ ] RDS 퍼블릭 액세스 '아니요' (AWS 콘솔), 보안그룹은 EC2 IP만 인바운드 (§19)
- [ ] **S3 버킷 `slideatlas-slides` 퍼블릭 차단** (Block Public Access ON).
      타일/슬라이드는 토큰 게이트 경유만 노출돼야 함 (§8). 콘솔에서 직접 확인
- [ ] S3 버킷 정책에 광범위 `"Principal":"*"` allow 없는지
- [ ] AWS 자격증명(.env)이 최소 권한인지 (S3 해당 버킷 한정 권장)

### B-5. 라이브 데이터 정합성 (코드 아닌 실제 DB)

> §18 D4b와 같은 취지 — 코드/시드가 맞아도 라이브 DB의 실제 행을 SELECT로 확인.

```bash
psql -h <RDS_ENDPOINT> -U slideatlas_admin -d slideatlas << 'SQL'
-- 1) subject_code NULL 사용자 0건이어야 (§6-2, §18 D4)
SELECT count(*) AS null_subject_users FROM users WHERE subject_code IS NULL;
-- 2) 어드민 해시가 잘리지 않았는지 (★ 2026-06 해시 앞부분 잘림 사고)
SELECT email, left(password_hash,14) AS head, length(password_hash) AS len
FROM admin_users;   -- head가 pbkdf2:sha256: 또는 scrypt: 로 시작해야 정상
-- 3) 슬라이드 배포 상태 분포
SELECT deploy_status, conversion_status, count(*) FROM slides GROUP BY 1,2;
-- 4) 구독 접근창 정합성 (access_open_date <= subscription_end)
SELECT count(*) AS bad_window FROM subscriptions
WHERE access_open_date > subscription_end;
SQL
```
- [ ] `null_subject_users` = 0 (있으면 백필 후 런칭, §18 D4b)
- [ ] 모든 admin_users 해시 `head`가 `pbkdf2:sha256:`/`scrypt:`로 시작 (중간 숫자로 시작 = 잘림)
- [ ] deployed 슬라이드 수가 의도와 일치 (rejected/qc_pending이 학생 노출 안 됨, §15-3)
- [ ] `bad_window` = 0
- [ ] inquiries.privacy_agreed 컬럼 존재 (§18 D1 — 개인정보 동의 저장, 법적 필수)

### B-6. 배포 환경 — 옛 서버 잔존 제거

> ★ 2026-06 교훈: 브라우저가 옛 Render에 붙어 "비번 틀림"으로 오인할 뻔. 실서버 단일화 확인.

```bash
# 실제 응답이 EC2(nginx)에서 오는지 — Server 헤더
curl -I https://slide-atlas.net/admin/login   # Server: nginx/... (render 아님)
```
- [ ] `Server:` 헤더가 nginx (Render 특유 헤더 `x-render-*` 없음)
- [ ] **Render 서비스 Suspend → Delete 완료** (과금 정지 + 혼동 제거)
- [ ] Gabia에 Render 가리키던 잔여 레코드(CNAME 등) 없음
- [ ] 옛 환경의 DB/시크릿이 따로 살아있지 않은지 (이중 진실 제거)

### B-7. 스모크 테스트 (배포 직후 실제 요청)

코드·환경 다 맞아도 **실제로 한 번 때려봐야** 안다. 사람이 직접:
- [ ] `https://slide-atlas.net/` 200, 자물쇠 정상
- [ ] `/admin/login` 실제 어드민 계정 로그인 → 대시보드 진입
- [ ] (구독·roster 세팅된 테스트 기관으로) 학생 가입 → 이메일 인증 → 로그인
- [ ] 슬라이드 뷰어 1장 열어 **타일 실제 렌더** (타일서버 살아있음 + S3 경로 + 토큰 게이트)
- [ ] AI 튜터 1회 질문 응답 (ANTHROPIC_API_KEY 동작)
- [ ] 1:1 문의 1건 → 답변 발송 (메일 경로 동작, §15-10)
- [ ] 워터마킹이 타일에 실제로 찍히는지 (§8)

---

## C. 정기 점검 (런칭 후 운영)

### C-1. 주간 (매주 1회, 5분)
- [ ] `systemctl status slideatlas nginx tileserver` — 셋 다 active
- [ ] `df -h` 디스크 여유 (로그·타일 캐시 누적 주의), `free -m` 메모리
- [ ] `journalctl -u slideatlas --since "1 week ago" | grep -iE "error|traceback|rollback" | tail` — 반복 에러 패턴
- [ ] 미답변 1:1 문의·검수 대기·MPP없음·갱신 임박 (어드민 대시보드 §15-11)

### C-2. 월간 (매월 1회)
- [ ] TLS 인증서 만료 D-day 확인 (자동갱신 신뢰하되 눈으로 1회) — B-3 명령
- [ ] DB 백업 존재·복원 가능성 (RDS 자동 스냅샷 활성 확인, 복원 리허설 분기 1회)
- [ ] AWS 비용 추이 (EC2 t3.medium + RDS + S3, 예상 대비 급증 없는지)
- [ ] 보안그룹·S3 정책 변동 없는지 (의도치 않은 오픈)
- [ ] 라이브 데이터 정합성 (B-5 SQL 재실행) — 특히 NULL subject_code, 고아 세션

### C-3. 학기 경계 (3/1, 9/1 전후 — SlideAtlas 핵심 주기)
- [ ] 신규/갱신 구독의 access_open_date(학기 -30일)·subscription_end 정확 (§16)
- [ ] roster 업로드분과 실제 가입자 수 정합 (좌석 max_seats 대비)
- [ ] 만료 구독의 접근 차단 실제 동작 (fail-closed, §8)
- [ ] 접근창 KST 경계 하루 어긋남 없는지 (§18 D10)
- [ ] 부하 대비 (개강 직후 동시 가입·로그인) — Locust 결과(§18 D14) 반영된 워커 수

---

## D. 사고 대응 (Runbook)

> 원칙: **당황 말고 원인부터 좁힌다 → 확인 → 수정**. 추측으로 DB·인프라 건드리지 않는다.
> except가 메시지를 삼켜 로그가 안 보이면, 임시 traceback으로 진짜 예외를 본다(부록 F-2).

### D-1. 로그인 안 됨 / "처리 중 오류"
1. 어느 페이지·어떤 메시지인지 구분 ("불일치" vs "처리 중 오류" vs "잠김" — 원인이 다름)
2. EC2 로컬로 직접 요청해 응답·로그 확보:
   `curl -i -X POST http://127.0.0.1:10000/admin/login --data-urlencode "email=..." --data-urlencode "password=..."`
3. `journalctl -u slideatlas -n 40` — traceback 있나 (없으면 except가 삼킴 → 부록 F-2)
4. DB 해시 확인: `SELECT left(password_hash,14), status, locked_at FROM admin_users WHERE email=...`
   - head가 숫자로 시작 → **해시 잘림** (부록 F-3 재설정)
   - locked_at NOT NULL → **계정 잠금** (24h 또는 수동 해제: `SET locked_at=NULL, failed_attempts=0`)
   - status != active → 비활성 계정
5. ★ 학생 로그인 안 됨은 **정상일 수 있음** — 구독·roster 선행 안 되면 가입·로그인 거부(§6-3).
   버그로 오인 말 것.

### D-2. 사이트 전체 다운 (502/503/타임아웃)
1. `systemctl status slideatlas nginx` — 어느 게 죽었나
2. slideatlas 죽음 → `journalctl -u slideatlas -n 50` 원인 → `systemctl restart slideatlas`
3. nginx 죽음 → `nginx -t`로 설정 검사 후 `systemctl restart nginx`
4. 둘 다 살았는데 502 → gunicorn 포트(10000) 응답 확인 `curl -I http://127.0.0.1:10000/`
5. RDS 연결 실패 → 보안그룹·RDS 상태·`.env` DB_* 확인 (외부에선 안 붙는 게 정상, §19)

### D-3. 슬라이드 타일 안 보임 (회색/빈 뷰어)
1. 타일서버 살았나: `ps aux | grep -i tile | grep -v grep`, `ss -tlnp | grep <타일포트>`
2. 죽음 → 재기동 (systemd면 `systemctl restart tileserver`, 아니면 부록 F-1로 등록)
3. 살았는데 안 보임 → 타일 토큰 발급/검증(§8), S3 경로(s3_key), deploy_status='deployed' 확인
4. 특정 슬라이드만 → conversion_status·ready_no_mpp·S3 객체 존재 확인

### D-4. TLS 인증서 만료
1. `certbot certificates` 상태 확인
2. 수동 갱신: `sudo certbot renew` → `systemctl reload nginx`
3. 자동갱신 실패 원인: 80 포트 막힘(보안그룹)·DNS 변경 → B-3 재점검

### D-5. 의심스러운 접근 / 보안 사고 정황
1. 즉시 영향 범위 파악 (access_logs, 어드민 session_token 회전 흔적)
2. 어드민 세션 전체 무효화: `UPDATE admin_users SET session_token=NULL;` (재로그인 강제)
3. 필요 시 시크릿 회전 (JWT_SECRET_KEY·ADMIN_SECRET_KEY 재생성 → 전 세션 무효 → 재시작)
4. S3·보안그룹 오픈 여부 재확인, CloudTrail/접근 로그 검토
5. CEO 단독 판단 어려운 사안은 외부 보안 전문가 자문 (코드 검증 AI로는 부족, A절 원칙)

---

## E. 책임 경계 — AI에게 맡길 것 / 사람이 할 것

| 작업 | 누가 | 비고 |
|------|------|------|
| 코드 작성·리팩터 | Claude Code | §12 |
| 코드 보안 검증 | Codex·Gemini·Claude QA | **코드 한정 — 환경 못 봄(A절)** |
| 명령어·진단 방향 제시 | Claude (대화) | 실행은 사람이 |
| **EC2/RDS/S3 실제 실행** | **CEO 직접** | AI SSH 직접 실행 금지(§12) |
| **환경변수 실제 설정·확인** | **CEO 직접** | 코드 검증 사각지대(B-1) |
| **인프라 구성·콘솔 작업** | **CEO 직접** | 보안그룹·DNS·S3 정책 등 |
| 런칭 전 이 체크리스트 통과 | CEO (눈으로 대조) | "AI가 OK했다"로 대체 불가 |

---

## F. 부록 — 자주 쓰는 절차

### F-1. 타일서버 systemd 등록 (reboot 자동기동)
> 현재 수동/nohup 실행이면 등록 필요(2026-06 reboot 후 죽었던 항목).
> 먼저 원래 실행 방법 확인: `history | grep -i tile` 또는 `cat ~/tileserver/*.sh`
```bash
# 원래 실행 명령·포트·워킹디렉토리·venv 경로 확인 후 작성 (값은 실제에 맞춰 치환)
sudo tee /etc/systemd/system/tileserver.service > /dev/null << 'EOF'
[Unit]
Description=SlideAtlas Tile Server (titiler)
After=network.target
[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/tileserver
ExecStart=<실제 실행 명령 — 예: /home/ubuntu/tileserver/.venv/bin/python main.py>
Restart=always
RestartSec=3
[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable tileserver
sudo systemctl start tileserver
sudo systemctl status tileserver --no-pager
```
> ⚠ 시스템 Python 3.14·기존 ~/tileserver 환경을 건드리지 말 것(인계 원칙).
> ExecStart는 반드시 기존에 쓰던 그대로의 인터프리터·인자로.

### F-2. 삼켜진 예외 드러내기 (임시 디버그)
> except가 메시지를 삼켜 로그가 안 보일 때. **확인 후 반드시 원복.**
```bash
cd ~/SlideAtlas && cp server_render.py server_render.py.bak
# 해당 except 블록 직후에 한 줄 삽입 (nano 또는 안전한 치환):
#     import traceback; traceback.print_exc()
sudo systemctl restart slideatlas
# 재현 → journalctl -u slideatlas -n 50 으로 진짜 traceback 확인
# 끝나면 원복:
cp server_render.py.bak server_render.py && sudo systemctl restart slideatlas && rm server_render.py.bak
```

### F-3. 어드민 비밀번호 재설정 (해시 잘림·분실 시)
> 앱은 werkzeug 사용. **pbkdf2 권장**(scrypt는 환경별 검증 이슈 가능 — 2026-06 사례).
> 해시 전체를 한 글자도 빠짐없이 복사할 것(앞부분 잘림이 사고 원인이었음).
```bash
cd ~/SlideAtlas && source .venv/bin/activate && set +H
python3 -c "from werkzeug.security import generate_password_hash; import getpass; \
pw=getpass.getpass('새 비번: '); print(generate_password_hash(pw, method='pbkdf2:sha256'))"
# 출력된 pbkdf2:sha256:... 전체를 복사 → psql:
#   UPDATE admin_users SET password_hash='<전체>', failed_attempts=0,
#     failed_window_start=NULL, locked_at=NULL, session_token=NULL
#   WHERE email='boram@atlaslab.co.kr';
# 검증: SELECT left(password_hash,14) FROM admin_users WHERE email='...';  → 'pbkdf2:sha256:'
```

### F-4. 안전한 재시작·로그 확인 기본기
```bash
sudo systemctl restart slideatlas      # 앱만 재시작
sudo systemctl reload nginx            # nginx 설정만 무중단 반영
sudo journalctl -u slideatlas -f       # 실시간 로그 (Ctrl+C로 종료)
sudo journalctl -u slideatlas -n 50 --no-pager   # 최근 50줄
```

---

*최종 업데이트: 2026-06-03 v1.0 (신설) | 계기: EC2 이전 완료 + JWT_SECRET_KEY 환경변수 사각지대·*
*어드민 해시 잘림·reboot 후 타일서버 미기동 등 코드 검증으로 안 잡히는 사고 경험을 운영 매뉴얼로 집결 |*
*다음: 9월 런칭 전 B절 전수 통과, Render 폐기 후 B-6 갱신, 타일서버 systemd 등록 후 B-2 갱신*
