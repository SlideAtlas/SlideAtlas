/* interceptor.js — 전역 fetch 래퍼 + CSRF 자동 주입 + 401 에러 처리 */
(function () {
  'use strict';

  var _origFetch = window.fetch;

  /* ── getCookie ─────────────────────────────────────── */
  function getCookie(name) {
    var m = document.cookie.match('(^|;)\\s*' + name + '=([^;]*)');
    return m ? decodeURIComponent(m[2]) : '';
  }
  window._getCookie = getCookie; // login_terminal.js 공유

  /* ── 전역 모달 동적 생성 ─────────────────────────────── */
  var _modalsCreated = false;

  function _ensureModals() {
    if (_modalsCreated) return;
    _modalsCreated = true;

    function makeOverlay(id, msg) {
      var el = document.createElement('div');
      el.id = id;
      el.className = 'sa-modal-overlay';
      el.style.display = 'none';
      el.innerHTML =
        '<div class="sa-modal-box">' +
          '<p class="sa-modal-msg">' + msg + '</p>' +
          '<button class="sa-modal-btn" onclick="location.href=\'/login\'">로그인 페이지로</button>' +
        '</div>';
      document.body.appendChild(el);
    }

    makeOverlay('sa-modal-revoked',  '다른 기기에서 로그인되었습니다.');
    makeOverlay('sa-modal-sub-expired', '구독이 만료되었습니다.<br>과 사무실에 문의하세요.');
  }

  function _showModal(id) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function () { _showModal(id); });
      return;
    }
    _ensureModals();
    var el = document.getElementById(id);
    if (el) el.style.display = 'flex';
  }

  /* ── fetch 래퍼 ─────────────────────────────────────── */
  window.fetch = async function (input, init) {
    init = Object.assign({}, init || {});

    // credentials: include 기본값
    if (!('credentials' in init)) {
      init.credentials = 'include';
    }

    // POST/PUT/DELETE/PATCH → csrf_token 쿠키 읽어 X-CSRF-Token 헤더 자동 주입
    var method = String(init.method || 'GET').toUpperCase();
    if (method === 'POST' || method === 'PUT' || method === 'DELETE' || method === 'PATCH') {
      var csrf = getCookie('csrf_token');
      if (csrf) {
        if (!init.headers) {
          init.headers = {};
        }
        if (init.headers instanceof Headers) {
          if (!init.headers.has('X-CSRF-Token')) init.headers.set('X-CSRF-Token', csrf);
        } else {
          init.headers = Object.assign({}, init.headers);
          if (!init.headers['X-CSRF-Token']) init.headers['X-CSRF-Token'] = csrf;
        }
      }
    }

    var resp = await _origFetch.call(window, input, init);

    // 401 에러 분기 처리
    if (resp.status === 401) {
      var errCode = '';
      try {
        errCode = (await resp.clone().json()).error || '';
      } catch (_) {}

      if (errCode === 'SESSION_REVOKED') {
        _showModal('sa-modal-revoked');
      } else if (errCode === 'SUBSCRIPTION_EXPIRED') {
        _showModal('sa-modal-sub-expired');
      } else if (errCode === 'ACCOUNT_LOCKED') {
        location.href = '/login?view=locked';
      } else if (errCode === 'TILE_TOKEN_INVALID' || errCode === 'TOKEN_EXPIRED') {
        // 뷰어 전용 에러 — 로그인 재유도 금지. [2-2#2] 재발급 경로가 있으면 토큰 갱신 시도.
        if (typeof window.refreshTileToken === 'function') {
          window.refreshTileToken();
        } else if (typeof window.showToast === 'function') {
          window.showToast('뷰어를 새로고침하세요');
        }
      } else if (errCode === 'TOKEN_INVALID' || errCode === 'INVALID_TOKEN' || errCode === 'DB_UNAVAILABLE') {
        // 쿠키 없음·JWT 만료·변조 — 조용히 로그인 페이지로
        if (!location.pathname.startsWith('/login')) location.href = '/login';
      }
      // INVALID_CREDENTIALS 등 기타 401은 호출부에서 직접 처리
    }

    return resp;
  };
})();
