# Flask JSON → RDS 교체 패치 가이드

이 문서는 `server_render.py`에서 `slides.json` / `institutions.json` 파일을 직접 읽는 코드를
psycopg2 + Connection Pool 방식으로 교체하는 방법을 정리합니다.

**실제 파일 수정은 이 문서 확인 후 보람님이 직접 승인 후 진행.**

---

## 1. 영향 범위 (server_render.py 기준)

| 함수 / 위치 | 현재 동작 | 교체 후 동작 |
|---|---|---|
| `load_slides()` L.18-22 | slides.json 파일 읽기 | DB `slides` 테이블 SELECT |
| `save_slides(data)` L.24-26 | slides.json 파일 쓰기 | DB INSERT / UPDATE |
| `load_institutions()` L.28-32 | institutions.json 파일 읽기 | DB `institutions` + `subject_codes` SELECT |
| `admin_save_slide()` L.1371 | `save_slides()` 호출 | DB UPSERT |
| `admin_delete_slide()` L.1394 | `save_slides()` 호출 | DB DELETE |

---

## 2. 추가할 코드 (server_render.py 상단 import 바로 아래)

```python
# ── DB Connection Pool ────────────────────────────────────────────────
import psycopg2
from psycopg2 import pool as pg_pool

_db_pool = None

def get_db_pool():
    global _db_pool
    if _db_pool is None:
        _db_pool = pg_pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=5,
            host=os.environ["DB_HOST"],
            dbname=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            port=int(os.environ.get("DB_PORT", "5432")),
        )
    return _db_pool

def get_db_conn():
    return get_db_pool().getconn()

def release_db_conn(conn):
    get_db_pool().putconn(conn)
```

**설정 필요 환경변수** (Render 대시보드 → Environment):
```
DB_HOST=slideatlas-db.c94iwikwox6l.ap-northeast-2.rds.amazonaws.com
DB_NAME=slideatlas
DB_USER=slideatlas_admin
DB_PASSWORD=<비밀번호>
DB_PORT=5432
```

---

## 3. 교체 전 → 교체 후: load_slides()

### 교체 전 (현재 코드, L.18-22)
```python
def load_slides():
    if os.path.exists(SLIDES_JSON):
        with open(SLIDES_JSON, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"slides": []}
```

### 교체 후
```python
def load_slides():
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, institution_id, subject_code,
                       title_ko, title_en, description,
                       s3_key, s3_minimap_key, s3_thumbnail_key,
                       mpp, width, height,
                       stain, organ AS system,
                       species, original_format AS format,
                       conversion_status, is_public AS active,
                       knowledge_base
                FROM slides
                ORDER BY created_at
            """)
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
            # active 컬럼: DB는 BOOLEAN, 기존 코드는 bool 그대로 사용 → 호환됨
            # institution 컬럼명: 기존 코드는 s.get('institution') 사용
            for r in rows:
                r['institution'] = r.pop('institution_id', None)
            return {"slides": rows}
    finally:
        release_db_conn(conn)
```

> **주의**: 기존 코드 전체에서 `s.get('institution', 'SA')` 패턴을 사용 중 →
> `institution_id` → `institution` 으로 rename 처리 필수 (위 코드에 포함됨).

---

## 4. 교체 전 → 교체 후: save_slides()

### 교체 전 (현재 코드, L.24-26)
```python
def save_slides(data):
    with open(SLIDES_JSON, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
```

### 교체 후
```python
def save_slides(data):
    # 기존 인터페이스 호환 유지: {"slides": [...]} 형태로 전달받음
    # admin_save_slide에서 slide dict 전체를 넘기므로 UPSERT 처리
    slides = data.get("slides", [])
    conn = get_db_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                # 전체 교체 대신 개별 upsert — admin_save_slide 참고
                for s in slides:
                    cur.execute("""
                        INSERT INTO slides (
                            id, institution_id, subject_code,
                            title_ko, title_en, description,
                            s3_key, mpp, width, height,
                            stain, organ, original_format,
                            conversion_status, is_public
                        ) VALUES (
                            %(id)s, %(institution)s, %(category)s,
                            %(title_ko)s, %(title_en)s, %(description)s,
                            %(s3_key)s, %(mpp)s, %(width)s, %(height)s,
                            %(stain)s, %(system)s, %(format)s,
                            'ready', %(active)s
                        )
                        ON CONFLICT (id) DO UPDATE SET
                            institution_id    = EXCLUDED.institution_id,
                            title_ko          = EXCLUDED.title_ko,
                            title_en          = EXCLUDED.title_en,
                            description       = EXCLUDED.description,
                            s3_key            = EXCLUDED.s3_key,
                            stain             = EXCLUDED.stain,
                            organ             = EXCLUDED.organ,
                            is_public         = EXCLUDED.is_public
                    """, {
                        **s,
                        'active': bool(s.get('active', False)),
                        'mpp':    s.get('mpp'),
                        'width':  s.get('width'),
                        'height': s.get('height'),
                        'format': (s.get('format') or '').upper() or None,
                    })
    finally:
        release_db_conn(conn)
```

---

## 5. 교체 전 → 교체 후: load_institutions()

### 교체 전 (현재 코드, L.28-32)
```python
def load_institutions():
    if os.path.exists(INSTITUTIONS_JSON):
        with open(INSTITUTIONS_JSON, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"institutions": [], "subjects": []}
```

### 교체 후
```python
def load_institutions():
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id AS code, name_ko, name_en FROM institutions ORDER BY id")
            cols = [d[0] for d in cur.description]
            institutions = [dict(zip(cols, row)) for row in cur.fetchall()]

            cur.execute("SELECT code, name_ko, name_en FROM subject_codes ORDER BY code")
            cols = [d[0] for d in cur.description]
            subjects = [dict(zip(cols, row)) for row in cur.fetchall()]

        return {"institutions": institutions, "subjects": subjects}
    finally:
        release_db_conn(conn)
```

---

## 6. admin_save_slide / admin_delete_slide 교체

현재 두 함수 모두 `load_slides()` → 리스트 수정 → `save_slides()` 패턴.
DB 전환 후에는 직접 SQL로 처리하는 것이 더 깔끔합니다.

### admin_save_slide (L.1371) 교체 후
```python
@app.route('/admin/api/slide', methods=['POST'])
@admin_required
def admin_save_slide():
    try:
        payload = request.get_json()
        edit_id = payload.pop('edit_id', None)
        conn = get_db_conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    if edit_id:
                        cur.execute("""
                            UPDATE slides SET
                                title_ko = %s, title_en = %s,
                                description = %s, stain = %s,
                                organ = %s, s3_key = %s,
                                is_public = %s
                            WHERE id = %s
                        """, (
                            payload.get('title_ko'), payload.get('title_en'),
                            payload.get('description'), payload.get('stain'),
                            payload.get('system'), payload.get('s3_key'),
                            bool(payload.get('active', False)),
                            edit_id,
                        ))
                    else:
                        cur.execute("""
                            INSERT INTO slides (
                                id, institution_id, subject_code,
                                title_ko, title_en, description,
                                s3_key, stain, organ,
                                original_format, is_public
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            payload['id'],
                            payload.get('institution'),
                            CATEGORY_MAP.get(payload.get('category', '').lower()),
                            payload.get('title_ko'), payload.get('title_en'),
                            payload.get('description'),
                            payload.get('s3_key'),
                            payload.get('stain'), payload.get('system'),
                            (payload.get('format') or '').upper() or None,
                            bool(payload.get('active', False)),
                        ))
        finally:
            release_db_conn(conn)
        return jsonify({'ok': True})
    except psycopg2.IntegrityError:
        return jsonify({'ok': False, 'error': '이미 존재하는 ID입니다.'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})
```

### admin_delete_slide (L.1394) 교체 후
```python
@app.route('/admin/api/slide/<slide_id>', methods=['DELETE'])
@admin_required
def admin_delete_slide(slide_id):
    try:
        conn = get_db_conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM slides WHERE id = %s", (slide_id,))
        finally:
            release_db_conn(conn)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})
```

---

## 7. CATEGORY_MAP 상수 추가

`admin_save_slide`에서 사용하는 카테고리→과목코드 변환 맵.
`server_render.py` 상단 상수 영역에 추가:

```python
CATEGORY_MAP = {
    "histology":    "HST",
    "pathology":    "PATH",
    "parasitology": "PARA",
    "anatomy":      "ANAT",
    "embryology":   "EMBRY",
}
```

---

## 8. requirements.txt 추가 항목

```
psycopg2-binary==2.9.9
```

---

## 9. 작업 순서 (아침 실행 체크리스트)

```
□ 1. RDS 비밀번호 확인 (AWS Console → RDS → slideatlas-db → 수정)
□ 2. EC2 접속: ssh 또는 EC2 Instance Connect
□ 3. DB 스키마 적용: psql ... -f db/schema.sql
□ 4. 마이그레이션 실행:
       export DB_HOST=slideatlas-db.c94iwikwox6l.ap-northeast-2.rds.amazonaws.com
       export DB_NAME=slideatlas
       export DB_USER=slideatlas_admin
       export DB_PASSWORD=<비밀번호>
       python db/migrate_json_to_rds.py
□ 5. 결과 확인:
       psql ... -c "SELECT id, title_ko, conversion_status FROM slides;"
□ 6. Render 환경변수 설정 (DB_HOST, DB_NAME, DB_USER, DB_PASSWORD)
□ 7. server_render.py 교체 (이 문서 섹션 2-8 적용)
□ 8. Render 재배포 후 /slides, /admin 동작 확인
```
