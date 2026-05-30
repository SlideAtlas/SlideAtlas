#!/usr/bin/env python3
"""
SlideAtlas JWT 인증 테스트 실행 스크립트
pytest 설치가 불가능한 환경에서 unittest 사용

NOTE: RDS PostgreSQL 접속 불가 예외 처리
RDS는 EC2 전용 VPC에 있어 로컬에서 직접 접속 불가.
unittest.mock을 사용하여 DB 레이어를 mock
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock
from unittest.mock import MagicMock, patch

# 환경변수 설정
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-pytest"
os.environ["GMAIL_USER"] = "test@gmail.com"
os.environ["GMAIL_APP_PW"] = "test-app-pw"
os.environ["DB_HOST"] = "dummy"
os.environ["DB_NAME"] = "dummy"
os.environ["DB_USER"] = "dummy"
os.environ["DB_PASSWORD"] = "dummy"

# Flask 앱 로딩
from server_render import app
from auth.decorators import encode_token, COOKIE_NAME


class AuthTestCase(unittest.TestCase):
    """JWT 인증 테스트"""
    
    def setUp(self):
        """테스트 전 설정"""
        app.config["TESTING"] = True
        self.client = app.test_client()
        
        # Mock DB 연결
        self.mock_conn = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_conn.cursor.return_value.__enter__.return_value = self.mock_cursor
        self.mock_conn.cursor.return_value.__exit__.return_value = None
        self.mock_conn.commit.return_value = None
        self.mock_conn.rollback.return_value = None
        self.mock_conn.autocommit = False
    
    # ─────────────────────────────────────────────
    # 회원가입 테스트
    # ─────────────────────────────────────────────
    
    def test_register_missing_fields(self):
        """회원가입: 필수값 누락 → 400"""
        with patch("server_render.get_db_conn") as mock_get_db, \
             patch("server_render.release_db_conn"):
            mock_get_db.return_value = self.mock_conn
            
            resp = self.client.post("/api/auth/register", 
                                   json={"email": "test@example.com"})
            
            self.assertEqual(resp.status_code, 400)
            data = resp.get_json()
            self.assertEqual(data["error"], "MISSING_FIELDS")
    
    def test_register_roster_mismatch(self):
        """회원가입: 명단에 없는 이메일 → 403 ROSTER_MISMATCH"""
        with patch("server_render.get_db_conn") as mock_get_db, \
             patch("server_render.release_db_conn"):
            mock_get_db.return_value = self.mock_conn
            self.mock_cursor.fetchone.return_value = None
            
            resp = self.client.post("/api/auth/register",
                                   json={
                                       "email": "unknown@test.com",
                                       "password": "pass123",
                                       "role": "student",
                                       "institution_id": "YU"
                                   })
            
            self.assertEqual(resp.status_code, 403)
            data = resp.get_json()
            self.assertEqual(data["error"], "ROSTER_MISMATCH")
    
    def test_register_email_exists(self):
        """회원가입: 이미 가입된 이메일 → 409 EMAIL_EXISTS"""
        with patch("server_render.get_db_conn") as mock_get_db, \
             patch("server_render.release_db_conn"):
            mock_get_db.return_value = self.mock_conn
            self.mock_cursor.fetchone.side_effect = [(1,), (1,)]
            
            resp = self.client.post("/api/auth/register",
                                   json={
                                       "email": "existing@test.com",
                                       "password": "pass123",
                                       "role": "student",
                                       "institution_id": "YU"
                                   })
            
            self.assertEqual(resp.status_code, 409)
            data = resp.get_json()
            self.assertEqual(data["error"], "EMAIL_EXISTS")
    
    def test_register_capacity_exceeded(self):
        """회원가입: 정원 초과 → 409 CAPACITY_EXCEEDED"""
        with patch("server_render.get_db_conn") as mock_get_db, \
             patch("server_render.release_db_conn"), \
             patch("auth.auth.send_verification_email"):
            mock_get_db.return_value = self.mock_conn
            self.mock_cursor.fetchone.side_effect = [
                (1,),      # 명단
                None,      # 이메일
                (10,),     # max_users
                (10,),     # active_count
            ]
            
            resp = self.client.post("/api/auth/register",
                                   json={
                                       "email": "new@test.com",
                                       "password": "pass123",
                                       "role": "student",
                                       "institution_id": "YU"
                                   })
            
            self.assertEqual(resp.status_code, 409)
            data = resp.get_json()
            self.assertEqual(data["error"], "CAPACITY_EXCEEDED")
    
    def test_register_success(self):
        """회원가입: 성공 → 200"""
        with patch("server_render.get_db_conn") as mock_get_db, \
             patch("server_render.release_db_conn"), \
             patch("auth.auth.send_verification_email") as mock_send:
            mock_get_db.return_value = self.mock_conn
            self.mock_cursor.fetchone.side_effect = [
                (1,),       # 명단
                None,       # 이메일
                (100,),     # max_users
                (5,),       # active_count
            ]
            
            resp = self.client.post("/api/auth/register",
                                   json={
                                       "email": "new@test.com",
                                       "password": "secure123",
                                       "role": "student",
                                       "institution_id": "YU"
                                   })
            
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertTrue(data["success"])
            self.assertIn("인증코드", data["data"]["message"])
            self.assertTrue(mock_send.called)
    
    # ─────────────────────────────────────────────
    # 이메일 인증 테스트
    # ─────────────────────────────────────────────
    
    def test_verify_email_code_expired(self):
        """인증코드: 만료된 코드 → 410 CODE_EXPIRED"""
        with patch("server_render.get_db_conn") as mock_get_db, \
             patch("server_render.release_db_conn"):
            mock_get_db.return_value = self.mock_conn
            self.mock_cursor.fetchone.side_effect = [
                (1, "YU", "student", False),
                (1, "123456",
                 datetime.now(timezone.utc) - timedelta(minutes=20),
                 False, 0)
            ]
            
            resp = self.client.post("/api/auth/verify-email",
                                   json={
                                       "email": "test@example.com",
                                       "code": "123456"
                                   })
            
            self.assertEqual(resp.status_code, 410)
            data = resp.get_json()
            self.assertEqual(data["error"], "CODE_EXPIRED")
    
    def test_verify_email_too_many_attempts(self):
        """인증코드: 시도 초과 → 429 TOO_MANY_ATTEMPTS"""
        with patch("server_render.get_db_conn") as mock_get_db, \
             patch("server_render.release_db_conn"):
            mock_get_db.return_value = self.mock_conn
            self.mock_cursor.fetchone.side_effect = [
                (1, "YU", "student", False),
                (1, "123456",
                 datetime.now(timezone.utc) + timedelta(minutes=5),
                 False, 5)
            ]
            
            resp = self.client.post("/api/auth/verify-email",
                                   json={
                                       "email": "test@example.com",
                                       "code": "999999"
                                   })
            
            self.assertEqual(resp.status_code, 429)
            data = resp.get_json()
            self.assertEqual(data["error"], "TOO_MANY_ATTEMPTS")
    
    def test_verify_email_code_mismatch(self):
        """인증코드: 잘못된 코드 → 400 CODE_MISMATCH (remaining)"""
        with patch("server_render.get_db_conn") as mock_get_db, \
             patch("server_render.release_db_conn"):
            mock_get_db.return_value = self.mock_conn
            self.mock_cursor.fetchone.side_effect = [
                (1, "YU", "student", False),
                (1, "123456",
                 datetime.now(timezone.utc) + timedelta(minutes=5),
                 False, 3)
            ]
            
            resp = self.client.post("/api/auth/verify-email",
                                   json={
                                       "email": "test@example.com",
                                       "code": "999999"
                                   })
            
            self.assertEqual(resp.status_code, 400)
            data = resp.get_json()
            self.assertEqual(data["error"], "CODE_MISMATCH")
            self.assertIn("remaining", data)
            self.assertEqual(data["remaining"], 1)
    
    def test_verify_email_code_mismatch_last_attempt(self):
        """인증코드: attempt_count=4 불일치 → remaining=0"""
        with patch("server_render.get_db_conn") as mock_get_db, \
             patch("server_render.release_db_conn"):
            mock_get_db.return_value = self.mock_conn
            self.mock_cursor.fetchone.side_effect = [
                (1, "YU", "student", False),
                (1, "123456",
                 datetime.now(timezone.utc) + timedelta(minutes=5),
                 False, 4)
            ]
            
            resp = self.client.post("/api/auth/verify-email",
                                   json={
                                       "email": "test@example.com",
                                       "code": "wrong"
                                   })
            
            self.assertEqual(resp.status_code, 400)
            data = resp.get_json()
            self.assertEqual(data["remaining"], 0)
    
    def test_verify_email_capacity_exceeded(self):
        """인증: TO 재검사에서 초과 → 409 CAPACITY_EXCEEDED"""
        with patch("server_render.get_db_conn") as mock_get_db, \
             patch("server_render.release_db_conn"):
            mock_get_db.return_value = self.mock_conn
            self.mock_cursor.fetchone.side_effect = [
                (1, "YU", "student", False),
                (1, "123456",
                 datetime.now(timezone.utc) + timedelta(minutes=5),
                 False, 0),
                (100,),
                (100,),
            ]
            
            resp = self.client.post("/api/auth/verify-email",
                                   json={
                                       "email": "test@example.com",
                                       "code": "123456"
                                   })
            
            self.assertEqual(resp.status_code, 409)
            data = resp.get_json()
            self.assertEqual(data["error"], "CAPACITY_EXCEEDED")
    
    def test_verify_email_success(self):
        """인증: 성공 → 200 (쿠키 + csrf_token)"""
        with patch("server_render.get_db_conn") as mock_get_db, \
             patch("server_render.release_db_conn"):
            mock_get_db.return_value = self.mock_conn
            self.mock_cursor.fetchone.side_effect = [
                (1, "YU", "student", False),
                (1, "123456",
                 datetime.now(timezone.utc) + timedelta(minutes=5),
                 False, 0),
                (100,),
                (5,),
            ]
            
            resp = self.client.post("/api/auth/verify-email",
                                   json={
                                       "email": "test@example.com",
                                       "code": "123456"
                                   })
            
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertTrue(data["success"])
            self.assertIn("csrf_token", data["data"])
    
    # ─────────────────────────────────────────────
    # 로그인 테스트
    # ─────────────────────────────────────────────
    
    def test_login_invalid_credentials_not_found(self):
        """로그인: 존재하지 않는 이메일 → 401"""
        with patch("server_render.get_db_conn") as mock_get_db, \
             patch("server_render.release_db_conn"):
            mock_get_db.return_value = self.mock_conn
            self.mock_cursor.fetchone.return_value = None
            
            resp = self.client.post("/api/auth/login",
                                   json={
                                       "email": "nonexistent@test.com",
                                       "password": "pass123"
                                   })
            
            self.assertEqual(resp.status_code, 401)
            data = resp.get_json()
            self.assertEqual(data["error"], "INVALID_CREDENTIALS")
    
    def test_login_invalid_credentials_wrong_password(self):
        """로그인: 비밀번호 불일치 → 401"""
        with patch("server_render.get_db_conn") as mock_get_db, \
             patch("server_render.release_db_conn"):
            mock_get_db.return_value = self.mock_conn
            
            from werkzeug.security import generate_password_hash
            correct_hash = generate_password_hash("correct_password")
            
            self.mock_cursor.fetchone.return_value = (
                1, "YU", "student", False,
                correct_hash,
                "active",
                datetime.now(timezone.utc) + timedelta(days=365)
            )
            
            resp = self.client.post("/api/auth/login",
                                   json={
                                       "email": "test@example.com",
                                       "password": "wrong_password"
                                   })
            
            self.assertEqual(resp.status_code, 401)
            data = resp.get_json()
            self.assertEqual(data["error"], "INVALID_CREDENTIALS")
    
    def test_login_email_not_verified(self):
        """로그인: 미인증 계정 → 403 EMAIL_NOT_VERIFIED"""
        with patch("server_render.get_db_conn") as mock_get_db, \
             patch("server_render.release_db_conn"):
            mock_get_db.return_value = self.mock_conn
            
            from werkzeug.security import generate_password_hash
            
            self.mock_cursor.fetchone.return_value = (
                1, "YU", "student", False,
                generate_password_hash("password"),
                "pending_verification",
                datetime.now(timezone.utc) + timedelta(days=365)
            )
            
            resp = self.client.post("/api/auth/login",
                                   json={
                                       "email": "test@example.com",
                                       "password": "password"
                                   })
            
            self.assertEqual(resp.status_code, 403)
            data = resp.get_json()
            self.assertEqual(data["error"], "EMAIL_NOT_VERIFIED")
    
    def test_login_subscription_expired(self):
        """로그인: 구독 만료 (is_special=False) → 403"""
        with patch("server_render.get_db_conn") as mock_get_db, \
             patch("server_render.release_db_conn"):
            mock_get_db.return_value = self.mock_conn
            
            from werkzeug.security import generate_password_hash
            
            self.mock_cursor.fetchone.return_value = (
                1, "YU", "student", False,
                generate_password_hash("password"),
                "active",
                datetime.now(timezone.utc).date() - timedelta(days=1)
            )
            
            resp = self.client.post("/api/auth/login",
                                   json={
                                       "email": "test@example.com",
                                       "password": "password"
                                   })
            
            self.assertEqual(resp.status_code, 403)
            data = resp.get_json()
            self.assertEqual(data["error"], "SUBSCRIPTION_EXPIRED")
    
    def test_login_subscription_expired_but_special(self):
        """로그인: 구독 만료이지만 is_special=True → 200"""
        with patch("server_render.get_db_conn") as mock_get_db, \
             patch("server_render.release_db_conn"):
            mock_get_db.return_value = self.mock_conn
            
            from werkzeug.security import generate_password_hash
            
            self.mock_cursor.fetchone.return_value = (
                1, "YU", "student", True,
                generate_password_hash("password"),
                "active",
                datetime.now(timezone.utc).date() - timedelta(days=1)
            )
            
            resp = self.client.post("/api/auth/login",
                                   json={
                                       "email": "test@example.com",
                                       "password": "password"
                                   })
            
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertTrue(data["success"])
    
    def test_login_success(self):
        """로그인: 성공 → 200"""
        with patch("server_render.get_db_conn") as mock_get_db, \
             patch("server_render.release_db_conn"):
            mock_get_db.return_value = self.mock_conn
            
            from werkzeug.security import generate_password_hash
            
            self.mock_cursor.fetchone.return_value = (
                1, "YU", "student", False,
                generate_password_hash("password"),
                "active",
                datetime.now(timezone.utc).date() + timedelta(days=365)
            )
            
            resp = self.client.post("/api/auth/login",
                                   json={
                                       "email": "test@example.com",
                                       "password": "password"
                                   })
            
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertTrue(data["success"])
            self.assertIn("csrf_token", data["data"])
    
    def test_login_missing_fields(self):
        """로그인: 필수값 누락 → 400"""
        with patch("server_render.get_db_conn") as mock_get_db, \
             patch("server_render.release_db_conn"):
            mock_get_db.return_value = self.mock_conn
            
            resp = self.client.post("/api/auth/login",
                                   json={"email": "test@example.com"})
            
            self.assertEqual(resp.status_code, 400)
            data = resp.get_json()
            self.assertEqual(data["error"], "MISSING_FIELDS")
    
    # ─────────────────────────────────────────────
    # login_required 데코레이터 테스트
    # ─────────────────────────────────────────────
    
    def test_login_required_no_cookie(self):
        """login_required: 쿠키 없음 → 401 SESSION_EXPIRED"""
        resp = self.client.get("/api/auth/me")
        
        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertEqual(data["error"], "SESSION_EXPIRED")
    
    def test_login_required_invalid_token(self):
        """login_required: 유효하지 않은 JWT → 401"""
        self.client.set_cookie("localhost", COOKIE_NAME, "invalid.jwt.token")
        
        resp = self.client.get("/api/auth/me")
        
        self.assertEqual(resp.status_code, 401)
    
    def test_login_required_expired_token(self):
        """login_required: 만료된 JWT → 401 SESSION_EXPIRED"""
        with patch("auth.decorators.decode_token") as mock_decode:
            import jwt
            mock_decode.side_effect = jwt.ExpiredSignatureError()
            
            self.client.set_cookie("localhost", COOKIE_NAME, "dummy-token")
            resp = self.client.get("/api/auth/me")
            
            self.assertEqual(resp.status_code, 401)
            data = resp.get_json()
            self.assertEqual(data["error"], "SESSION_EXPIRED")
    
    def test_login_required_session_token_mismatch(self):
        """login_required: session_token 불일치 → 401 SESSION_EXPIRED"""
        with patch("server_render.get_db_conn") as mock_get_db, \
             patch("server_render.release_db_conn"):
            mock_get_db.return_value = self.mock_conn
            
            payload = {
                "sub": 1,
                "institution_id": "YU",
                "role": "student",
                "session_token": "old-session-token",
                "is_special": False,
            }
            token = encode_token(payload)
            self.client.set_cookie("localhost", COOKIE_NAME, token)
            
            self.mock_cursor.fetchone.return_value = (
                "new-session-token",
                "active"
            )
            
            resp = self.client.get("/api/auth/me")
            
            self.assertEqual(resp.status_code, 401)
            data = resp.get_json()
            self.assertEqual(data["error"], "SESSION_EXPIRED")
    
    def test_login_required_pending_verification(self):
        """login_required: status='pending_verification' → 401"""
        with patch("server_render.get_db_conn") as mock_get_db, \
             patch("server_render.release_db_conn"):
            mock_get_db.return_value = self.mock_conn
            
            payload = {
                "sub": 1,
                "institution_id": "YU",
                "role": "student",
                "session_token": "valid-session-123",
                "is_special": False,
            }
            token = encode_token(payload)
            self.client.set_cookie("localhost", COOKIE_NAME, token)
            
            self.mock_cursor.fetchone.return_value = (
                "valid-session-123",
                "pending_verification"
            )
            
            resp = self.client.get("/api/auth/me")
            
            self.assertEqual(resp.status_code, 401)
    
    def test_login_required_success(self):
        """login_required: 유효한 JWT + DB 일치 → 200"""
        with patch("server_render.get_db_conn") as mock_get_db, \
             patch("server_render.release_db_conn"):
            mock_get_db.return_value = self.mock_conn
            
            payload = {
                "sub": 1,
                "institution_id": "YU",
                "role": "student",
                "session_token": "valid-session-123",
                "is_special": False,
            }
            token = encode_token(payload)
            self.client.set_cookie("localhost", COOKIE_NAME, token)
            
            self.mock_cursor.fetchone.side_effect = [
                ("valid-session-123", "active"),
                (1, "test@example.com", "student", "YU", False, "active", None)
            ]
            
            resp = self.client.get("/api/auth/me")
            
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertTrue(data["success"])
            self.assertEqual(data["data"]["user_id"], 1)
    
    # ─────────────────────────────────────────────
    # 응답 헤더 테스트
    # ─────────────────────────────────────────────
    
    def test_response_headers_cache_control(self):
        """응답 헤더: Cache-Control: no-store"""
        with patch("server_render.get_db_conn") as mock_get_db, \
             patch("server_render.release_db_conn"):
            mock_get_db.return_value = self.mock_conn
            
            self.mock_cursor.fetchone.return_value = None
            resp = self.client.post("/api/auth/register",
                                   json={
                                       "email": "test@example.com",
                                       "password": "pass",
                                       "role": "student",
                                       "institution_id": "YU"
                                   })
            self.assertIn("Cache-Control", resp.headers)
            self.assertIn("no-store", resp.headers["Cache-Control"])
    
    def test_logout_success(self):
        """로그아웃: 성공 → 200, 쿠키 삭제"""
        with patch("server_render.get_db_conn") as mock_get_db, \
             patch("server_render.release_db_conn"):
            mock_get_db.return_value = self.mock_conn
            
            payload = {
                "sub": 1,
                "institution_id": "YU",
                "role": "student",
                "session_token": "valid-session-123",
                "is_special": False,
            }
            token = encode_token(payload)
            self.client.set_cookie("localhost", COOKIE_NAME, token)
            
            self.mock_cursor.fetchone.return_value = (
                "valid-session-123", "active"
            )
            
            resp = self.client.post("/api/auth/logout")
            
            self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    # 테스트 실행
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(AuthTestCase)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 결과 요약
    print("\n" + "="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Success: {result.testsRun - len(result.failures) - len(result.errors)}")
    print("="*70)
    
    # 실패한 테스트만 보고
    if result.failures:
        print("\nFAILURES:")
        for test, traceback in result.failures:
            print(f"\n{test}:")
            print(traceback)
    
    if result.errors:
        print("\nERRORS:")
        for test, traceback in result.errors:
            print(f"\n{test}:")
            print(traceback)
    
    sys.exit(0 if result.wasSuccessful() else 1)
