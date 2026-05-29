"""
SlideAtlas JSON -> RDS 마이그레이션 스크립트

실행 전 환경변수 설정:
    export DB_HOST=slideatlas-db.c94iwikwox6l.ap-northeast-2.rds.amazonaws.com
    export DB_NAME=slideatlas
    export DB_USER=slideatlas_admin
    export DB_PASSWORD=<비밀번호>

실행 방법 (프로젝트 루트에서):
    python db/migrate_json_to_rds.py

주의:
    - 중복 row는 건너뜀 (ON CONFLICT DO NOTHING) - 재실행 안전
    - 중간 에러 발생 시 전체 롤백
    - schema.sql이 먼저 실행된 상태여야 함
"""

import os
import json
import sys

try:
    import psycopg2
    from psycopg2 import sql as psql
except ImportError:
    print("ERROR: psycopg2 미설치 -> pip install psycopg2-binary")
    sys.exit(1)


# -- DB 접속 정보 (환경변수 필수) ----------------------------------------------
def get_conn():
    required = ["DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        print(f"ERROR: 환경변수 미설정 -> {', '.join(missing)}")
        sys.exit(1)

    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        port=int(os.environ.get("DB_PORT", "5432")),
        connect_timeout=10,
    )


# -- JSON 로드 -----------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_json(filename):
    path = os.path.join(BASE_DIR, filename)
    if not os.path.exists(path):
        print(f"ERROR: {path} 파일 없음")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# -- 카테고리 -> subject_code 변환 ---------------------------------------------
CATEGORY_MAP = {
    "histology":   "HST",
    "pathology":   "PATH",
    "parasitology": "PARA",
    "anatomy":     "ANAT",
    "embryology":  "EMBRY",
}


def migrate_institutions(cur, institutions_data):
    """institutions.json -> institutions 테이블"""
    rows = institutions_data.get("institutions", [])
    inserted = 0
    skipped = 0

    for inst in rows:
        cur.execute(
            """
            INSERT INTO institutions (id, name_ko, name_en)
            VALUES (%s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (inst["code"], inst.get("name_ko"), inst.get("name_en")),
        )
        if cur.rowcount == 1:
            inserted += 1
        else:
            skipped += 1

    print(f"  [institutions] 삽입: {inserted}건, 건너뜀(중복): {skipped}건")
    return inserted


def migrate_subject_codes(cur, institutions_data):
    """institutions.json의 subjects -> subject_codes 테이블"""
    rows = institutions_data.get("subjects", [])
    inserted = 0
    skipped = 0

    for subj in rows:
        cur.execute(
            """
            INSERT INTO subject_codes (code, name_ko, name_en)
            VALUES (%s, %s, %s)
            ON CONFLICT (code) DO NOTHING
            """,
            (subj["code"], subj.get("name_ko"), subj.get("name_en")),
        )
        if cur.rowcount == 1:
            inserted += 1
        else:
            skipped += 1

    print(f"  [subject_codes] 삽입: {inserted}건, 건너뜀(중복): {skipped}건")
    return inserted


def migrate_slides(cur, slides_data):
    """slides.json -> slides 테이블"""
    rows = slides_data.get("slides", [])
    inserted = 0
    skipped = 0
    warnings = []

    for slide in rows:
        slide_id = slide["id"]
        category = slide.get("category", "")
        subject_code = CATEGORY_MAP.get(category)
        if not subject_code:
            warnings.append(f"  WARN: {slide_id} - 알 수 없는 category '{category}', subject_code=NULL")

        # active 여부 -> conversion_status 결정
        # JSON에는 변환 상태 개념이 없으므로 active=True -> ready, False -> pending 처리
        if slide.get("active"):
            conversion_status = "ready"
        else:
            conversion_status = "pending"

        # MPP가 null이면 ready_no_mpp
        if slide.get("active") and slide.get("mpp") is None:
            conversion_status = "ready_no_mpp"

        cur.execute(
            """
            INSERT INTO slides (
                id, institution_id, subject_code,
                title_ko, title_en, description,
                s3_key,
                mpp, width, height,
                stain, organ,
                original_format,
                conversion_status,
                is_public
            ) VALUES (
                %s, %s, %s,
                %s, %s, %s,
                %s,
                %s, %s, %s,
                %s, %s,
                %s,
                %s,
                %s
            )
            ON CONFLICT (id) DO NOTHING
            """,
            (
                slide_id,
                slide.get("institution"),
                subject_code,
                slide.get("title_ko"),
                slide.get("title_en"),
                slide.get("description"),
                slide.get("s3_key"),
                slide.get("mpp"),
                slide.get("width"),
                slide.get("height"),
                slide.get("stain"),
                slide.get("system"),          # JSON의 system -> DB의 organ
                (slide.get("format") or "").upper() or None,
                conversion_status,
                bool(slide.get("active", False)),
            ),
        )
        if cur.rowcount == 1:
            inserted += 1
        else:
            skipped += 1

    for w in warnings:
        print(w)
    print(f"  [slides] 삽입: {inserted}건, 건너뜀(중복): {skipped}건")
    return inserted


# -- 메인 ----------------------------------------------------------------------
def main():
    print("=== SlideAtlas JSON -> RDS 마이그레이션 시작 ===\n")

    slides_data       = load_json("slides.json")
    institutions_data = load_json("institutions.json")

    print(f"로드 완료: slides {len(slides_data.get('slides', []))}건, "
          f"institutions {len(institutions_data.get('institutions', []))}건\n")

    conn = get_conn()
    print(f"DB 접속 성공: {os.environ['DB_HOST']}\n")

    try:
        with conn:                          # with conn: -> 성공 시 commit, 예외 시 rollback
            with conn.cursor() as cur:
                print("[1/3] institutions 마이그레이션...")
                migrate_institutions(cur, institutions_data)

                print("[2/3] subject_codes 마이그레이션...")
                migrate_subject_codes(cur, institutions_data)

                print("[3/3] slides 마이그레이션...")
                migrate_slides(cur, slides_data)

        print("\n=== 마이그레이션 완료 (commit) ===")

    except Exception as e:
        print(f"\n!!! 오류 발생 - 전체 롤백: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
