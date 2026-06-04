/* login_terminal.js — 로그인 터미널 7개 뷰 상태 관리 */
(function () {
  'use strict';

  /* ── 상태 ───────────────────────────────────────────── */
  var _view = 'LOGIN';
  var _email = '';
  var _resetToken = '';
  var _verifyTimer = null;
  var _verifySecondsLeft = 600;
  var _resendTimer = null;
  var _resendSecondsLeft = 0;
  var _codeExhausted = false;

  /* ── next URL (오픈 리다이렉트 방어) ─────────────────── */
  var _nextUrl = (function () {
    var n = new URLSearchParams(location.search).get('next') || '/slides';
    // '/'로 시작하는 내부 경로만 허용, '//'나 외부 URL 차단
    if (!n.startsWith('/') || n.startsWith('//')) n = '/slides';
    return n;
  })();

  /* ── 로그인/인증 후 목적지 결정 ────────────────────────
     순수 admin-only(role='admin' AND subject_code 없음)는 슬라이드 0개 화면 대신 /portal로.
     겸직 admin(subject_code 보유)·일반 viewer는 next(기본 /slides)로. 게이트 판정은 서버 단일
     게이트가 담당하며, 여기선 "어디로 보내나"만 결정한다(§8 무관). */
  function _postLoginDest(d) {
    var noSubject = (d.subject_code === null || d.subject_code === undefined || d.subject_code === '');
    if (d.role === 'admin' && noSubject) return '/portal';
    return _nextUrl;
  }

  /* ── 타이머 헬퍼 ─────────────────────────────────────── */
  function _clearTimers() {
    if (_verifyTimer)  { clearInterval(_verifyTimer);  _verifyTimer  = null; }
    if (_resendTimer)  { clearInterval(_resendTimer);  _resendTimer  = null; }
  }

  function _startVerifyTimer() {
    _verifySecondsLeft = 600;
    if (_verifyTimer) clearInterval(_verifyTimer);
    _verifyTimer = setInterval(function () {
      _verifySecondsLeft--;
      var el = document.getElementById('t-vtimer');
      if (el) {
        var m = Math.floor(_verifySecondsLeft / 60);
        var s = _verifySecondsLeft % 60;
        el.textContent = m + ':' + (s < 10 ? '0' + s : s);
      }
      if (_verifySecondsLeft <= 0) {
        clearInterval(_verifyTimer); _verifyTimer = null;
        var wrap = document.getElementById('t-vtimer-wrap');
        if (wrap) wrap.innerHTML = '<span style="color:#e76f51;">인증코드가 만료되었습니다.</span>';
      }
    }, 1000);
  }

  function _startResendCooldown(sec) {
    _resendSecondsLeft = sec;
    var btn = document.getElementById('t-resend');
    if (btn) btn.disabled = true;
    if (_resendTimer) clearInterval(_resendTimer);
    _resendTimer = setInterval(function () {
      _resendSecondsLeft--;
      var b = document.getElementById('t-resend');
      if (!b) { clearInterval(_resendTimer); _resendTimer = null; return; }
      if (_resendSecondsLeft <= 0) {
        b.disabled = false;
        b.textContent = '인증코드 재발송';
        clearInterval(_resendTimer); _resendTimer = null;
      } else {
        b.textContent = '재발송 (' + _resendSecondsLeft + 's)';
      }
    }, 1000);
  }

  /* ── 에러 / 성공 메시지 ──────────────────────────────── */
  function _showErr(msg) {
    var el = document.getElementById('t-err');
    if (!el) return;
    el.style.color = '#e76f51';
    el.textContent = msg;
    el.style.display = 'block';
  }
  function _showMsg(msg) {
    var el = document.getElementById('t-err');
    if (!el) return;
    el.style.color = '#0F1F3D';
    el.textContent = msg;
    el.style.display = 'block';
  }
  function _hideErr() {
    var el = document.getElementById('t-err');
    if (el) { el.textContent = ''; el.style.display = 'none'; }
  }

  /* ── 뷰 전환 ─────────────────────────────────────────── */
  function _goView(v, email) {
    _view = v;
    if (email !== undefined) _email = email;
    if (v === 'VERIFY') _codeExhausted = false;
    _render();
  }

  /* ── 공통 로고 ───────────────────────────────────────── */
  function _logo() {
    return '<div class="terminal-logo">' +
      '<img src="/static/slideatlas_logo_hor.png" alt="SlideAtlas" class="terminal-logo-img">' +
      '</div>';
  }

  /* ── 뷰별 HTML ───────────────────────────────────────── */
  function _loginHTML() {
    return _logo() +
      '<h2 class="terminal-view-title">로그인</h2>' +
      '<label class="terminal-label" for="t-email">이메일</label>' +
      '<input class="terminal-input" type="email" id="t-email" placeholder="your@edu.kr" autocomplete="email">' +
      '<label class="terminal-label" for="t-pw">비밀번호</label>' +
      '<input class="terminal-input" type="password" id="t-pw" placeholder="••••••••" autocomplete="current-password">' +
      '<button class="terminal-btn" id="t-submit">로그인</button>' +
      '<div class="terminal-error" id="t-err" style="display:none"></div>' +
      '<div class="terminal-links">' +
        '<button class="terminal-link" id="to-signup">회원가입</button>' +
        '<span class="terminal-divider">·</span>' +
        '<button class="terminal-link" id="to-forgot">비밀번호 찾기</button>' +
      '</div>';
  }

  function _signupHTML() {
    return _logo() +
      '<h2 class="terminal-view-title">회원가입</h2>' +
      '<label class="terminal-label" for="t-inst">기관</label>' +
      '<select class="terminal-select" id="t-inst">' +
        '<option value="">기관을 선택하세요</option>' +
      '</select>' +
      '<label class="terminal-label" for="t-email">이메일</label>' +
      '<input class="terminal-input" type="email" id="t-email" placeholder="소속 기관에 등록된 이메일" autocomplete="email">' +
      '<label class="terminal-label" for="t-pw">비밀번호</label>' +
      '<input class="terminal-input" type="password" id="t-pw" placeholder="8자 이상" autocomplete="new-password">' +
      '<label class="terminal-label" for="t-pw2">비밀번호 확인</label>' +
      '<input class="terminal-input" type="password" id="t-pw2" placeholder="••••••••" autocomplete="new-password">' +
      '<button class="terminal-btn" id="t-submit">회원가입</button>' +
      '<div class="terminal-error" id="t-err" style="display:none"></div>' +
      '<div class="terminal-links">' +
        '<button class="terminal-link" id="to-login">이미 계정이 있나요?</button>' +
      '</div>';
  }

  function _verifyHTML() {
    return _logo() +
      '<h2 class="terminal-view-title">이메일 인증</h2>' +
      '<p class="terminal-info">이메일로 전송된 6자리 인증코드를 입력하세요.<br>' +
        '<small style="color:#9B9490;font-size:12px;">' + _email + '</small></p>' +
      '<input class="terminal-code-input" type="text" id="t-code" maxlength="6" placeholder="000000" inputmode="numeric" autocomplete="one-time-code">' +
      '<button class="terminal-btn" id="t-submit">인증 확인</button>' +
      '<div class="terminal-error" id="t-err" style="display:none"></div>' +
      '<div class="terminal-timer" id="t-vtimer-wrap">' +
        '남은 시간: <span id="t-vtimer">10:00</span>' +
      '</div>' +
      '<button class="terminal-resend-btn" id="t-resend">인증코드 재발송</button>' +
      '<div class="terminal-links">' +
        '<button class="terminal-link" id="to-login">← 로그인으로</button>' +
      '</div>';
  }

  function _forgotHTML() {
    return _logo() +
      '<h2 class="terminal-view-title">비밀번호 찾기</h2>' +
      '<p class="terminal-info" style="margin-bottom:16px;">가입한 이메일 주소를 입력하시면<br>비밀번호 재설정 링크를 보내드립니다.</p>' +
      '<label class="terminal-label" for="t-email">이메일</label>' +
      '<input class="terminal-input" type="email" id="t-email" placeholder="your@edu.kr" autocomplete="email">' +
      '<button class="terminal-btn" id="t-submit">재설정 링크 발송</button>' +
      '<div class="terminal-error" id="t-err" style="display:none"></div>' +
      '<div class="terminal-links">' +
        '<button class="terminal-link" id="to-login">← 로그인으로</button>' +
      '</div>';
  }

  function _resetHTML() {
    return _logo() +
      '<h2 class="terminal-view-title">비밀번호 재설정</h2>' +
      '<label class="terminal-label" for="t-pw">새 비밀번호</label>' +
      '<input class="terminal-input" type="password" id="t-pw" placeholder="8자 이상" autocomplete="new-password">' +
      '<label class="terminal-label" for="t-pw2">비밀번호 확인</label>' +
      '<input class="terminal-input" type="password" id="t-pw2" placeholder="••••••••" autocomplete="new-password">' +
      '<button class="terminal-btn" id="t-submit">비밀번호 변경</button>' +
      '<div class="terminal-error" id="t-err" style="display:none"></div>' +
      '<div class="terminal-links">' +
        '<button class="terminal-link" id="to-login">← 로그인으로</button>' +
      '</div>';
  }

  function _lockedHTML() {
    return _logo() +
      '<div class="terminal-static-icon">&#128274;</div>' +
      '<div class="terminal-info">' +
        '<strong>보안상 계정이 잠겼습니다.</strong><br>' +
        '과 사무실에 문의하세요.' +
      '</div>' +
      '<div class="terminal-links" style="margin-top:24px;">' +
        '<button class="terminal-link" id="to-login">← 로그인으로</button>' +
      '</div>';
  }

  function _expiredHTML() {
    return _logo() +
      '<div class="terminal-static-icon">&#128340;</div>' +
      '<div class="terminal-info">' +
        '<strong>구독이 만료되었습니다.</strong><br>' +
        '과 사무실에 문의하세요.' +
      '</div>' +
      '<div class="terminal-links" style="margin-top:24px;">' +
        '<button class="terminal-link" id="to-login">← 로그인으로</button>' +
      '</div>';
  }

  /* ── 렌더 ────────────────────────────────────────────── */
  function _render() {
    var root = document.getElementById('login-terminal-root');
    if (!root) return;
    _clearTimers();
    var html = '<div class="terminal-wrap">';
    switch (_view) {
      case 'LOGIN':   html += _loginHTML();   break;
      case 'SIGNUP':  html += _signupHTML();  break;
      case 'VERIFY':  html += _verifyHTML();  break;
      case 'FORGOT':  html += _forgotHTML();  break;
      case 'RESET':   html += _resetHTML();   break;
      case 'LOCKED':  html += _lockedHTML();  break;
      case 'EXPIRED': html += _expiredHTML(); break;
      default:        html += _loginHTML();
    }
    html += '</div>';
    root.innerHTML = html;
    _attachHandlers();
    if (_view === 'VERIFY') _startVerifyTimer();
  }

  /* ── API 호출 ─────────────────────────────────────────── */
  async function _doLogin() {
    var email = (document.getElementById('t-email').value || '').trim();
    var pw    = document.getElementById('t-pw').value || '';
    _hideErr();
    if (!email || !pw) { _showErr('이메일과 비밀번호를 입력하세요.'); return; }
    var btn = document.getElementById('t-submit');
    if (btn) btn.disabled = true;
    try {
      var res  = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email, password: pw })
      });
      var data = await res.json();
      if (data.success) {
        location.href = _postLoginDest(data.data || {});
        return;
      }
      var code = data.error || '';
      if (code === 'EMAIL_NOT_VERIFIED' || code === 'PENDING_VERIFICATION') {
        _goView('VERIFY', email);
      } else if (code === 'ACCOUNT_LOCKED') {
        _goView('LOCKED');
      } else if (code === 'SUBSCRIPTION_EXPIRED') {
        _goView('EXPIRED');
      } else {
        _showErr(data.message || '로그인에 실패했습니다.');
        if (btn) btn.disabled = false;
      }
    } catch (_e) {
      _showErr('네트워크 오류가 발생했습니다.');
      if (btn) btn.disabled = false;
    }
  }

  async function _doSignup() {
    var inst  = (document.getElementById('t-inst').value  || '').trim();
    var email = (document.getElementById('t-email').value || '').trim();
    var pw    = document.getElementById('t-pw').value || '';
    var pw2   = document.getElementById('t-pw2').value || '';
    _hideErr();
    // 지위·역할·과목·이름은 입력받지 않는다 — 서버가 roster 두 트랙으로 결정하고
    //   표시용 이름은 roster.name을 단일 출처로 쓴다(§6-4).
    if (!inst || !email || !pw) { _showErr('모든 항목을 입력하세요.'); return; }
    if (pw.length < 8) { _showErr('비밀번호는 8자 이상이어야 합니다.'); return; }
    if (pw !== pw2) { _showErr('비밀번호가 일치하지 않습니다.'); return; }
    var btn = document.getElementById('t-submit');
    if (btn) btn.disabled = true;
    try {
      var res  = await fetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ institution_id: inst, email: email, password: pw })
      });
      var data = await res.json();
      if (data.success) {
        _goView('VERIFY', email);
        return;
      }
      var code = data.error || '';
      if (code === 'NOT_ON_ROSTER') {
        _showErr('명단에 없습니다. 과 사무실에 문의하세요.');
      } else if (code === 'EMAIL_EXISTS') {
        _showErr('이미 가입된 이메일입니다. 로그인 화면으로 이동합니다.');
        setTimeout(function () { _goView('LOGIN', email); }, 1800);
      } else if (code === 'SUBSCRIPTION_INACTIVE') {
        _showErr('해당 과목 구독이 활성화되지 않았습니다. 과 사무실에 문의하세요.');
      } else if (code === 'SEAT_FULL') {
        _showErr('정원이 초과되었습니다. 과 사무실에 문의하세요.');
      } else if (code === 'MULTI_SUBJECT_AMBIGUOUS') {
        _showErr('여러 과목 명단에 등록되어 있습니다. 과 사무실에 문의하세요.');
      } else {
        _showErr(data.message || '회원가입에 실패했습니다.');
      }
      if (btn) btn.disabled = false;
    } catch (_e) {
      _showErr('네트워크 오류가 발생했습니다.');
      if (btn) btn.disabled = false;
    }
  }

  async function _doVerify() {
    var code = (document.getElementById('t-code').value || '').trim();
    _hideErr();
    if (!code || code.length !== 6) { _showErr('6자리 인증코드를 입력하세요.'); return; }
    if (!_email) { _showErr('이메일 정보가 없습니다. 다시 로그인해주세요.'); return; }
    var btn = document.getElementById('t-submit');
    if (btn) btn.disabled = true;
    try {
      var res  = await fetch('/api/auth/verify-email', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: _email, code: code })
      });
      var data = await res.json();
      if (data.success) {
        location.href = _postLoginDest(data.data || {});
        return;
      }
      var errCode = data.error || '';
      if (errCode === 'TOO_MANY_ATTEMPTS' || errCode === 'CODE_ATTEMPTS_EXCEEDED') {
        _codeExhausted = true;
        _showErr('시도 횟수를 초과했습니다. 인증코드를 재발송하세요.');
        var inp = document.getElementById('t-code');
        if (inp) inp.disabled = true;
        if (btn) btn.disabled = true;
      } else if (errCode === 'ACCOUNT_LOCKED') {
        _goView('LOCKED');
      } else if (errCode === 'CODE_EXPIRED') {
        _showErr('인증코드가 만료되었습니다. 재발송 버튼을 눌러주세요.');
        if (btn) btn.disabled = false;
      } else if (errCode === 'CODE_MISMATCH') {
        var rem = typeof data.remaining === 'number' ? data.remaining : '';
        _showErr('인증코드가 일치하지 않습니다.' + (rem !== '' ? ' (남은 시도: ' + rem + '회)' : ''));
        if (btn) btn.disabled = false;
      } else {
        _showErr(data.message || '인증에 실패했습니다.');
        if (btn) btn.disabled = false;
      }
    } catch (_e) {
      _showErr('네트워크 오류가 발생했습니다.');
      if (btn) btn.disabled = false;
    }
  }

  async function _doResend() {
    if (!_email) { _showErr('이메일 정보가 없습니다.'); return; }
    var btn = document.getElementById('t-resend');
    if (btn) btn.disabled = true;
    _hideErr();
    try {
      var res  = await fetch('/api/auth/resend-code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: _email })
      });
      var data = await res.json();
      if (data.success) {
        _codeExhausted = false;
        var inp = document.getElementById('t-code');
        if (inp) { inp.disabled = false; inp.value = ''; inp.focus(); }
        var subBtn = document.getElementById('t-submit');
        if (subBtn) subBtn.disabled = false;
        _startResendCooldown(60);
        _startVerifyTimer();
        _showMsg('새 인증코드가 발송되었습니다.');
        return;
      }
      var code = data.error || '';
      if (code === 'RESEND_TOO_SOON') {
        var m = (data.message || '').match(/(\d+)/);
        _startResendCooldown(m ? parseInt(m[1], 10) : 60);
        _showErr(data.message || '잠시 후 다시 시도하세요.');
      } else if (code === 'RESEND_LIMIT_EXCEEDED') {
        _showErr('오늘 재발송 한도를 초과했습니다. 내일 다시 시도하세요.');
        if (btn) btn.disabled = true;
      } else if (code === 'ACCOUNT_LOCKED') {
        _goView('LOCKED');
      } else {
        _showErr(data.message || '재발송에 실패했습니다.');
        if (btn) btn.disabled = false;
      }
    } catch (_e) {
      _showErr('네트워크 오류가 발생했습니다.');
      if (btn) btn.disabled = false;
    }
  }

  async function _doForgot() {
    var email = (document.getElementById('t-email').value || '').trim();
    _hideErr();
    if (!email) { _showErr('이메일을 입력하세요.'); return; }
    var btn = document.getElementById('t-submit');
    if (btn) btn.disabled = true;
    try {
      var res  = await fetch('/api/auth/forgot-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email })
      });
      if (res.status === 404) {
        _showErr('서비스 준비 중입니다.');
        if (btn) btn.disabled = false;
        return;
      }
      var data = await res.json();
      if (data.success) {
        _email = email;
        _resetToken = (data.data && data.data.reset_token) ? data.data.reset_token : '';
        _goView('RESET');
      } else {
        _showErr(data.message || '처리에 실패했습니다.');
        if (btn) btn.disabled = false;
      }
    } catch (_e) {
      _showErr('서비스 준비 중입니다.');
      if (btn) btn.disabled = false;
    }
  }

  async function _doReset() {
    var pw  = document.getElementById('t-pw').value  || '';
    var pw2 = document.getElementById('t-pw2').value || '';
    _hideErr();
    if (!pw || !pw2)  { _showErr('비밀번호를 입력하세요.'); return; }
    if (pw !== pw2)   { _showErr('비밀번호가 일치하지 않습니다.'); return; }
    if (pw.length < 8){ _showErr('비밀번호는 8자 이상이어야 합니다.'); return; }
    var btn = document.getElementById('t-submit');
    if (btn) btn.disabled = true;
    try {
      var res  = await fetch('/api/auth/reset-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: _email, reset_token: _resetToken, password: pw })
      });
      if (res.status === 404) {
        _showErr('서비스 준비 중입니다.');
        if (btn) btn.disabled = false;
        return;
      }
      var data = await res.json();
      if (data.success) {
        _goView('LOGIN');
      } else {
        _showErr(data.message || '비밀번호 변경에 실패했습니다.');
        if (btn) btn.disabled = false;
      }
    } catch (_e) {
      _showErr('서비스 준비 중입니다.');
      if (btn) btn.disabled = false;
    }
  }

  /* ── 이벤트 핸들러 연결 ──────────────────────────────── */
  function _attachHandlers() {
    var submit   = document.getElementById('t-submit');
    var toSignup = document.getElementById('to-signup');
    var toLogin  = document.getElementById('to-login');
    var toForgot = document.getElementById('to-forgot');
    var resend   = document.getElementById('t-resend');

    if (submit) {
      var fn = { LOGIN: _doLogin, SIGNUP: _doSignup, VERIFY: _doVerify,
                 FORGOT: _doForgot, RESET: _doReset }[_view];
      if (fn) submit.addEventListener('click', fn);
    }
    if (toSignup) toSignup.addEventListener('click', function () { _goView('SIGNUP'); });
    if (toLogin)  toLogin.addEventListener('click',  function () { _goView('LOGIN');  });
    if (toForgot) toForgot.addEventListener('click', function () { _goView('FORGOT'); });
    if (resend)   resend.addEventListener('click',   _doResend);

    // Enter 키 제출 지원
    ['t-email','t-pw','t-pw2','t-code','t-inst'].forEach(function (id) {
      var el = document.getElementById(id);
      if (el && submit) {
        el.addEventListener('keydown', function (e) {
          if (e.key === 'Enter' && !submit.disabled) submit.click();
        });
      }
    });

    // 회원가입 화면: 기관 드롭다운을 /api/institutions 공개 목록으로 채운다(§6-4 v3.4).
    if (_view === 'SIGNUP') _loadInstitutions();
  }

  /* ── 기관 드롭다운 로딩 ───────────────────────────────── */
  async function _loadInstitutions() {
    var sel = document.getElementById('t-inst');
    if (!sel) return;
    try {
      var res = await fetch('/api/institutions');
      var data = await res.json();
      if (!data.success || !Array.isArray(data.institutions)) return;
      data.institutions.forEach(function (it) {
        var opt = document.createElement('option');
        opt.value = it.id;            // 값 = institution_id
        opt.textContent = it.name_ko; // 표시 = 학교명
        sel.appendChild(opt);
      });
    } catch (_e) { /* 목록 로딩 실패 시 빈 드롭다운 유지 */ }
  }

  /* ── 공개 API ─────────────────────────────────────────── */
  window.LoginTerminal = {
    init: function (initialView) {
      _clearTimers();
      if (initialView === 'locked')       _view = 'LOCKED';
      else if (initialView === 'expired') _view = 'EXPIRED';
      else                                _view = 'LOGIN';
      _render();
    }
  };

  /* ── DOMContentLoaded 자동 초기화 ─────────────────────── */
  document.addEventListener('DOMContentLoaded', function () {
    var vp = new URLSearchParams(location.search).get('view');
    window.LoginTerminal.init(vp);
  });
})();
