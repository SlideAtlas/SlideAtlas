"""SlideAtlas 최초 슈퍼관리자 시드 스크립트 (S5-1).

환경변수 (필수):
  ADMIN_EMAIL    : 초기 슈퍼관리자 이메일
  ADMIN_PASSWORD : 초기 슈퍼관리자 비밀번호 (bcrypt 해시 후 DB 저장, 평문 저장 금지)
  DB_HOST / DB_NAME / DB_USER / DB_PASSWORD / DB_PORT

멱등 조건:
  role='super_admin' 계정이 이미 존재하면 시드를 건너뜀.
  시드 완료 후 ADMIN_PASSWORD 환경변수는 인증에 사용되지 않음 (폐기 경로).

실행:
  python db/seed_admin.py
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()


def seed():
    email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("ADMIN_PASSWORD", "").strip()

    if not email or not password:
        print("❌ ADMIN_EMAIL, ADMIN_PASSWORD 환경변수를 설정하세요.")
        sys.exit(1)

    try:
        import psycopg2
        from werkzeug.security import generate_password_hash
    except ImportError as e:
        print(f"❌ 의존성 누락: {e}")
        print("   pip install psycopg2-binary werkzeug")
        sys.exit(1)

    conn = psycopg2.connect(
        host=os.environ["DB_HOST"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        port=int(os.environ.get("DB_PORT", "5432")),
    )
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            # 멱등 체크: super_admin이 이미 있으면 건너뜀
            cur.execute(
                "SELECT COUNT(*) FROM admin_users WHERE role = 'super_admin'"
            )
            count = cur.fetchone()[0]
            if count > 0:
                print(f"⏭  super_admin 계정이 이미 {count}개 존재합니다. 시드를 건너뜁니다.")
                conn.rollback()
                return

            # bcrypt 기반 해시 (werkzeug 기본 방식)
            pw_hash = generate_password_hash(password)

            # 이름: 이메일 로컬 파트에서 자동 추출 (관리자 페이지에서 나중에 변경 가능)
            name = email.split("@")[0]

            cur.execute(
                """INSERT INTO admin_users (email, password_hash, role, name, status)
                   VALUES (%s, %s, 'super_admin', %s, 'active')""",
                (email, pw_hash, name),
            )
        conn.commit()
        print(f"✅ 최초 슈퍼관리자 생성 완료: {email}")
        print("   ⚠️  시드 완료. ADMIN_PASSWORD는 더 이상 인증에 사용되지 않습니다.")
        print("   ✅  이후 비밀번호 관리는 어드민 콘솔(/admin) 내에서 진행하세요.")
    except Exception as e:
        conn.rollback()
        print(f"❌ 시드 실패: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    seed()
