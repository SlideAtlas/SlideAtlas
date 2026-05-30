from dotenv import load_dotenv
load_dotenv()

import os
import sys
import threading
import json
from functools import wraps

from flask import Flask, send_file, Response, request, jsonify, session, redirect, url_for, render_template
from PIL import Image
import io

# -- DB Connection Pool (RDS PostgreSQL) ---------------------------------------
try:
    import psycopg2
    from psycopg2 import pool as pg_pool
    _PSYCOPG2_AVAILABLE = True
except ImportError:
    _PSYCOPG2_AVAILABLE = False

_db_pool = None

def get_db_pool():
    global _db_pool
    if _db_pool is None:
        if not _PSYCOPG2_AVAILABLE:
            raise RuntimeError("psycopg2 미설치 -- pip install psycopg2-binary")
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

CATEGORY_MAP = {
    "histology":    "HST",
    "pathology":    "PATH",
    "parasitology": "PARA",
    "anatomy":      "ANAT",
    "embryology":   "EMBRY",
}

app = Flask(__name__)
app.secret_key = os.environ.get('ADMIN_SECRET_KEY', 'slideatlas-dev-secret-2026')

# -- JWT 인증 Blueprint 등록 ---------------------------------------------------
from auth.auth import auth_bp
app.register_blueprint(auth_bp)
from auth.decorators import (
    login_required, page_login_required,
    generate_tile_token, verify_tile_token,
)

# -- JSON 데이터 경로 (롤백용 주석 보존) ----------------------------------------
SLIDES_JSON = os.path.join(os.path.dirname(__file__), 'slides.json')
INSTITUTIONS_JSON = os.path.join(os.path.dirname(__file__), 'institutions.json')

# [ROLLBACK] JSON 파일 직접 읽기 -- RDS 전환 전 코드
# def load_slides():
#     if os.path.exists(SLIDES_JSON):
#         with open(SLIDES_JSON, 'r', encoding='utf-8') as f:
#             return json.load(f)
#     return {"slides": []}

def load_slides():
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, institution_id AS institution, subject_code AS category,
                       title_ko, title_en, description,
                       s3_key, s3_minimap_key, s3_thumbnail_key,
                       mpp, width, height,
                       stain, organ AS system,
                       species, original_format AS format,
                       conversion_status, is_public AS active,
                       knowledge_base,
                       'ec2' AS tileserver
                FROM slides
                ORDER BY created_at
            """)
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        return {"slides": rows}
    finally:
        release_db_conn(conn)

# [ROLLBACK] JSON 파일 직접 쓰기 -- RDS 전환 전 코드
# def save_slides(data):
#     with open(SLIDES_JSON, 'w', encoding='utf-8') as f:
#         json.dump(data, f, ensure_ascii=False, indent=2)

def save_slides(data):
    # admin_save_slide / admin_delete_slide 가 직접 SQL 처리하므로 no-op.
    pass

# [ROLLBACK] JSON 파일 직접 읽기 -- RDS 전환 전 코드
# def load_institutions():
#     if os.path.exists(INSTITUTIONS_JSON):
#         with open(INSTITUTIONS_JSON, 'r', encoding='utf-8') as f:
#             return json.load(f)
#     return {"institutions": [], "subjects": []}

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

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect('/admin/login')
        return f(*args, **kwargs)
    return decorated


def admin_csrf_required(f):
    """Admin 세션 기반 CSRF 검증 (JWT CSRF와 별개). POST/PUT/DELETE에만 적용."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
            import secrets as _sec
            client_token = request.headers.get('X-CSRF-Token')
            stored_token = session.get('admin_csrf_token')
            if not client_token or not stored_token or not _sec.compare_digest(client_token, stored_token):
                return jsonify({'ok': False, 'error': 'CSRF 검증 실패'}), 403
        return f(*args, **kwargs)
    return decorated


def get_slide_institution(slide_id):
    """DB에서 slide의 institution_id와 is_public 반환. 없으면 None."""
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT institution_id, is_public FROM slides WHERE id = %s", (slide_id,))
            return cur.fetchone()
    finally:
        release_db_conn(conn)


def _tile_err(error, message, status=403):
    from flask import g as _g
    resp = jsonify({"success": False, "error": error, "message": message})
    resp.status_code = status
    resp.headers["Cache-Control"] = "no-store, no-cache"
    return resp


def _slide_access_allowed(slide_id):
    """institution_id + is_public 검사. (허용여부, 에러응답) 튜플."""
    from flask import g
    info = get_slide_institution(slide_id)
    if info is None:
        return False, _tile_err("SLIDE_NOT_FOUND", "슬라이드를 찾을 수 없습니다", 404)
    inst_id, is_public = info
    if getattr(g, 'is_special', False):
        return True, None
    # is_public=FALSE: 비공개 슬라이드 일반 사용자 접근 불가 (§12-4 ⑤)
    if not is_public:
        return False, _tile_err("FORBIDDEN", "접근 권한이 없습니다", 403)
    if inst_id != getattr(g, 'institution_id', None):
        return False, _tile_err("FORBIDDEN", "접근 권한이 없습니다", 403)
    return True, None


def _verify_tile_request(slide_id):
    """타일 접근 토큰(?t=) 검증. 통과 시 None, 실패 시 에러 응답."""
    from flask import g
    t = request.args.get("t")
    if not t or not verify_tile_token(
        t, str(getattr(g, 'user_id', '')),
        getattr(g, 'institution_id', ''), slide_id
    ):
        # TILE_TOKEN_INVALID: 로그인 세션과 무관한 타일 전용 에러.
        # 프론트 인터셉터가 SESSION_REVOKED·SUBSCRIPTION_EXPIRED와 오판하지 않도록
        # 코드 문자열을 명확히 구분한다.
        return _tile_err("TILE_TOKEN_INVALID", "타일 접근 토큰이 만료되었습니다. 뷰어를 새로고침하세요.", 401)
    return None

# ── 온디맨드 슬라이드 캐시 ──
SLIDE_CACHE = {}
SLIDE_LOCKS = {}
SLIDE_STATUS = {}
TILE_SIZE = 256
OVERLAP = 1
SLIDES_DIR = "/tmp/slides"

EC2_TILESERVER = "http://43.200.171.90:8000"

def get_s3_client():
    import boto3
    return boto3.client(
        's3',
        region_name=os.environ.get('AWS_REGION', 'ap-northeast-2'),
        aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY')
    )

def init_slide(slide_id):
    if slide_id not in SLIDE_LOCKS:
        SLIDE_LOCKS[slide_id] = threading.Lock()
    with SLIDE_LOCKS[slide_id]:
        if slide_id in SLIDE_CACHE:
            return True
        SLIDE_STATUS[slide_id] = {"done": False, "error": None}
        try:
            import openslide
            from openslide import deepzoom

            data = load_slides()
            slide_info = next((s for s in data.get('slides', []) if s['id'] == slide_id), None)
            if not slide_info:
                SLIDE_STATUS[slide_id]["error"] = "슬라이드 정보를 찾을 수 없습니다."
                return False

            if slide_info.get('tileserver') == 'ec2':
                ec2_w = slide_info.get("width", 83663)
                ec2_h = slide_info.get("height", 60416)
                SLIDE_CACHE[slide_id] = {"ec2": True, "W": ec2_w, "H": ec2_h, "levels": 18}
                SLIDE_STATUS[slide_id]["done"] = True
                print(f"✅ [{slide_id}] EC2 타일서버 모드 {ec2_w}x{ec2_h}")
                return True

            bucket = os.environ.get('AWS_S3_BUCKET', 'slideatlas-slides')
            s3_key = slide_info.get('s3_key', '')
            fmt = slide_info.get('format', 'dcm').lower()

            os.makedirs(SLIDES_DIR, exist_ok=True)

            if fmt == 'svs':
                local_path = os.path.join(SLIDES_DIR, f"{slide_id}.svs")
                if not os.path.exists(local_path):
                    print(f"SVS 다운로드 중: {s3_key}")
                    s3 = get_s3_client()
                    s3.download_file(bucket, s3_key, local_path)
                slide_obj = openslide.OpenSlide(local_path)
            else:
                dcm_files = slide_info.get('dcm_files', [])
                dcm_entry = slide_info.get('dcm_entry', dcm_files[0] if dcm_files else '')
                slide_dir = os.path.join(SLIDES_DIR, slide_id)
                os.makedirs(slide_dir, exist_ok=True)
                s3 = get_s3_client()
                for fname in dcm_files:
                    local_f = os.path.join(slide_dir, fname)
                    if not os.path.exists(local_f):
                        print(f"DCM 다운로드: {fname}")
                        s3.download_file(bucket, fname, local_f)
                local_path = os.path.join(slide_dir, dcm_entry)
                slide_obj = openslide.OpenSlide(local_path)

            W, H = slide_obj.dimensions
            dz = deepzoom.DeepZoomGenerator(slide_obj, tile_size=TILE_SIZE, overlap=OVERLAP, limit_bounds=True)
            SLIDE_CACHE[slide_id] = {"slide": slide_obj, "dz": dz, "W": W, "H": H, "levels": dz.level_count}
            SLIDE_STATUS[slide_id]["done"] = True
            print(f"✅ [{slide_id}] 로드 완료! {W}x{H}, {dz.level_count}레벨")
            return True
        except Exception as e:
            SLIDE_STATUS[slide_id]["error"] = str(e)
            print(f"❌ [{slide_id}] 오류: {e}")
            return False

# ── EC2 타일서버 프록시 ──
@app.route('/ec2tile/<path:subpath>')
@login_required
def ec2_proxy(subpath):
    # slide_id 추출: "dzi/SA-HST-001.dzi" → "SA-HST-001"
    parts = subpath.split('/')
    raw = parts[1] if len(parts) > 1 else parts[0]
    slide_id = raw.replace('.dzi', '').split('_files')[0]
    # 기관·is_public 격리 (§12-4 ①⑤)
    allowed, aerr = _slide_access_allowed(slide_id)
    if not allowed:
        return aerr
    # 타일 토큰 검증 (TTL 5분)
    err = _verify_tile_request(slide_id)
    if err:
        return err

    import urllib.request
    url = f"{EC2_TILESERVER}/{subpath}"
    try:
        with urllib.request.urlopen(url, timeout=120) as resp:
            data = resp.read()
            ct = resp.headers.get('Content-Type', 'image/jpeg')
            r = Response(data, mimetype=ct)
            r.headers['Cache-Control'] = 'no-store, no-cache'
            return r
    except Exception as e:
        print(f"EC2 proxy error {url}: {e}")
        return Response(str(e), status=502)

# ── 랜딩페이지 ──
@app.route('/')
def landing():
    is_logged = bool(request.cookies.get('access_token'))
    return render_template('landing.html', is_logged=is_logged)


@app.route('/login')
def login_page():
    is_logged = bool(request.cookies.get('access_token'))
    next_url = request.args.get('next', '/')
    return render_template('login.html', is_logged=is_logged, next=next_url)


@app.route('/viewer')
@page_login_required
def viewer_default():
    from flask import g
    data = load_slides()
    slides = [s for s in data.get('slides', []) if s.get('active') and
              (getattr(g, 'is_special', False) or s.get('institution') == getattr(g, 'institution_id', None))]
    if slides:
        return redirect(f'/viewer/{slides[0]["id"]}')
    return redirect('/')

@app.route('/viewer/<slide_id>')
@page_login_required
def viewer(slide_id):
    from flask import g
    data = load_slides()
    slide_info = next((s for s in data.get('slides', []) if s['id'] == slide_id), None)
    if not slide_info:
        return redirect('/slides')
    # 기관 격리 + is_public=FALSE 차단: 타일 토큰 발급 전 검증 (§12-4 ⑤)
    if not getattr(g, 'is_special', False):
        if slide_info.get('institution') != getattr(g, 'institution_id', None):
            return redirect('/')
        if not slide_info.get('active'):   # active = is_public
            return redirect('/')

    use_ec2 = slide_info.get('tileserver') == 'ec2'

    if slide_id not in SLIDE_CACHE:
        t = threading.Thread(target=init_slide, args=(slide_id,))
        t.daemon = True
        t.start()

    status = SLIDE_STATUS.get(slide_id, {"done": False, "error": None})

    if status.get("error"):
        return f'''<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>SlideAtlas</title>
<style>body{{background:#0d1219;color:white;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}}</style>
</head><body><div style="text-align:center">
<h2 style="color:#e76f51">오류 발생</h2>
<p style="color:rgba(255,255,255,0.5)">{status["error"]}</p>
<a href="/slides" style="color:#2A9D8F;margin-top:16px;display:block;">← 목록으로</a>
</div></body></html>'''

    if not status.get("done"):
        return f'''<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>SlideAtlas — 로딩 중</title>
<meta http-equiv="refresh" content="3">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#0d1219; color:white; font-family:"Segoe UI",sans-serif;
  display:flex; align-items:center; justify-content:center; height:100vh; }}
.progress-bar {{ width:160px; height:2px; background:rgba(91,184,212,0.2);
  border-radius:2px; overflow:hidden; margin:0 auto 20px; }}
.progress-bar::after {{ content:''; display:block; height:100%;
  width:40%; background:#5BB8D4; border-radius:2px;
  animation:progress 1.2s ease-in-out infinite; }}
@keyframes progress {{ 0% {{ transform:translateX(-100%); }} 100% {{ transform:translateX(350%); }} }}
p {{ color:rgba(255,255,255,0.45); font-size:14px; }}
small {{ color:rgba(255,255,255,0.25); font-size:12px; margin-top:8px; display:block; }}
</style>
</head>
<body>
<div style="text-align:center">
  <img src="/static/slideatlas_logo.png" alt="SlideAtlas" style="height:160px;width:auto;margin-bottom:32px;">
  <p>{slide_info.get("title_ko", slide_id)} 로딩 중...</p>
  <small>처음 접속 시 잠시 소요됩니다. 페이지가 자동으로 새로고침됩니다.</small>
</div>
</body></html>'''

    cache = SLIDE_CACHE[slide_id]
    W = cache.get("W", 83663)
    H = cache.get("H", 13119)
    DZ_LEVELS = cache.get("levels", 18)
    title_ko = slide_info.get("title_ko", slide_id)
    title_en = slide_info.get("title_en", "")
    system = slide_info.get("system", "")
    stain = slide_info.get("stain", "H&E")
    mpp = slide_info.get("mpp") or 0.25

    # 타일 접근 토큰 발급 (TTL 5분, §8 Presigned URL)
    from flask import g as _g
    tile_token = generate_tile_token(str(getattr(_g, 'user_id', '')), getattr(_g, 'institution_id', ''), slide_id)

    if use_ec2:
        tile_source_url = f"/ec2tile/dzi/{slide_id}.dzi?t={tile_token}"
        thumbnail_url = f"/ec2tile/thumbnail/{slide_id}?t={tile_token}"
        W = slide_info.get("width", W)
        H = slide_info.get("height", H)
    else:
        tile_source_url = f"/dzi/{slide_id}.dzi?t={tile_token}"
        thumbnail_url = f"/thumbnail/{slide_id}?t={tile_token}"

    # ── 뷰어 HTML ──
    return render_template('viewer.html',
        slide_id=slide_id,
        slide_info=slide_info,
        tile_token=tile_token,
        tile_source_url=tile_source_url,
        thumbnail_url=thumbnail_url,
        W=W, H=H, mpp=mpp,
        title_ko=title_ko,
        title_en=title_en,
        system=system,
        stain=stain,
    )

# ─────────────────────────────────────────────
# 이하 /slides, /api/chat, /dzi, /thumbnail, /admin 등은 원본과 동일
# ─────────────────────────────────────────────

@app.route('/slides')
@page_login_required
def slides():
    from flask import g
    data = load_slides()
    # 기관 격리: 자신의 기관 슬라이드만 표시
    all_slides = [s for s in data.get('slides', []) if s.get('active') and
                  (getattr(g, 'is_special', False) or s.get('institution') == getattr(g, 'institution_id', None))]
    systems = {}
    stains = {}
    for s in all_slides:
        sys = s.get('system', '기타')
        stain = s.get('stain', '기타')
        systems[sys] = systems.get(sys, 0) + 1
        stains[stain] = stains.get(stain, 0) + 1
    total = len(all_slides)
    stain_class = {'H&E': 'he', 'PAS': 'pas', 'Masson Trichrome': 'masson', 'Silver': 'silver'}
    return render_template('slides.html',
        slides=all_slides,
        systems=systems,
        stains=stains,
        total=total,
        stain_class=stain_class,
    )

@app.route('/api/chat', methods=['POST'])
@login_required
def api_chat():
    import urllib.request
    import json as json_mod
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        return jsonify({'reply': '서버에 API 키가 설정되지 않았습니다.'}), 500
    data = request.get_json()
    user_msg = data.get('message', '')
    # 탈옥 방어: 클라이언트 system 파라미터 무시, 서버 측 가드레일만 사용 (§12-4 ③)
    system_prompt = (
        '당신은 SlideAtlas의 병리학·조직학 AI 튜터입니다. '
        'SlideAtlas 학습(병리학, 조직학, 슬라이드 판독, 관련 의학 지식)과 무관한 질문에는 '
        '"SlideAtlas 학습 관련 질문만 답변합니다"라고만 응답하세요. '
        '한국어로 답변하세요.'
    )
    if not user_msg:
        return jsonify({'reply': '메시지가 없습니다.'}), 400

    if 'JSON' in system_prompt or '형식으로만 응답' in system_prompt:
        payload = json_mod.dumps({
            'model': 'claude-sonnet-4-5',
            'max_tokens': 800,
            'system': system_prompt,
            'messages': [{'role': 'user', 'content': user_msg}]
        }).encode('utf-8')
        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages',
            data=payload,
            headers={'Content-Type': 'application/json', 'x-api-key': api_key, 'anthropic-version': '2023-06-01'},
            method='POST'
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json_mod.loads(resp.read().decode('utf-8'))
                reply = result['content'][0]['text'] if result.get('content') else '응답 없음'
                return jsonify({'reply': reply})
        except Exception as e:
            return jsonify({'reply': f'API 오류: {str(e)}'}), 500

    payload = json_mod.dumps({
        'model': 'claude-sonnet-4-5',
        'max_tokens': 600,
        'stream': True,
        'system': system_prompt,
        'messages': [{'role': 'user', 'content': user_msg}]
    }).encode('utf-8')
    req = urllib.request.Request(
        'https://api.anthropic.com/v1/messages',
        data=payload,
        headers={
            'Content-Type': 'application/json',
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01'
        },
        method='POST'
    )

    def generate():
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                for line in resp:
                    line = line.decode('utf-8').strip()
                    if line.startswith('data: '):
                        chunk = line[6:]
                        if chunk == '[DONE]':
                            break
                        try:
                            obj = json_mod.loads(chunk)
                            if obj.get('type') == 'content_block_delta':
                                text = obj.get('delta', {}).get('text', '')
                                if text:
                                    yield f"data: {json_mod.dumps({'text': text})}\n\n"
                        except Exception:
                            pass
        except Exception as e:
            yield f"data: {json_mod.dumps({'error': str(e)})}\n\n"

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )

@app.route('/dzi/<slide_id>.dzi')
@login_required
def dzi_descriptor(slide_id):
    allowed, aerr = _slide_access_allowed(slide_id)
    if not allowed:
        return aerr
    err = _verify_tile_request(slide_id)
    if err:
        return err
    if slide_id not in SLIDE_CACHE:
        return Response("Loading...", status=503)
    cache = SLIDE_CACHE[slide_id]
    if cache.get('ec2'):
        return Response("Use EC2 tileserver", status=404)
    dz = cache["dz"]
    w, h = dz.level_dimensions[-1]
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<Image xmlns="http://schemas.microsoft.com/deepzoom/2008"
  Format="jpeg" Overlap="{OVERLAP}" TileSize="{TILE_SIZE}">
  <Size Width="{w}" Height="{h}"/>
</Image>'''
    resp = Response(xml, mimetype='application/xml')
    resp.headers['Cache-Control'] = 'no-store, no-cache'
    return resp

@app.route('/dzi/<slide_id>_files/<int:level>/<int:col>_<int:row>.jpeg')
@app.route('/dzi/<slide_id>_files/<int:level>/<int:col>_<int:row>.jpg')
@login_required
def dzi_tile(slide_id, level, col, row):
    allowed, aerr = _slide_access_allowed(slide_id)
    if not allowed:
        return aerr
    err = _verify_tile_request(slide_id)
    if err:
        return err
    if slide_id not in SLIDE_CACHE:
        img = Image.new('RGB', (TILE_SIZE, TILE_SIZE), (245, 240, 235))
        buf = io.BytesIO()
        img.save(buf, 'JPEG')
        buf.seek(0)
        r = send_file(buf, mimetype='image/jpeg')
        r.headers['Cache-Control'] = 'no-store, no-cache'
        return r
    try:
        dz = SLIDE_CACHE[slide_id]["dz"]
        tile = dz.get_tile(level, (col, row))
        buf = io.BytesIO()
        tile.save(buf, format='JPEG', quality=88)
        buf.seek(0)
        r = send_file(buf, mimetype='image/jpeg')
        r.headers['Cache-Control'] = 'no-store, no-cache'
        return r
    except Exception as e:
        img = Image.new('RGB', (TILE_SIZE, TILE_SIZE), (255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, 'JPEG')
        buf.seek(0)
        r = send_file(buf, mimetype='image/jpeg')
        r.headers['Cache-Control'] = 'no-store, no-cache'
        return r

@app.route('/thumbnail/<slide_id>')
@login_required
def thumbnail(slide_id):
    allowed, aerr = _slide_access_allowed(slide_id)
    if not allowed:
        return aerr
    err = _verify_tile_request(slide_id)
    if err:
        return err
    if slide_id not in SLIDE_CACHE:
        return Response("Not loaded", status=503)
    cache = SLIDE_CACHE[slide_id]
    if cache.get('ec2'):
        return Response("Use EC2 thumbnail", status=404)
    try:
        slide_obj = cache["slide"]
        thumb = slide_obj.get_thumbnail((280, 200))
        buf = io.BytesIO()
        thumb.save(buf, format='JPEG', quality=80)
        buf.seek(0)
        r = send_file(buf, mimetype='image/jpeg')
        r.headers['Cache-Control'] = 'no-store, no-cache'
        return r
    except Exception as e:
        img = Image.new('RGB', (280, 200), (245, 240, 235))
        buf = io.BytesIO()
        img.save(buf, 'JPEG')
        buf.seek(0)
        return send_file(buf, mimetype='image/jpeg')

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'slideatlas2026')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    error = ''
    if request.method == 'POST':
        pw = request.form.get('password', '')
        if pw == ADMIN_PASSWORD:
            import secrets as _sec_admin
            session['admin_logged_in'] = True
            session['admin_csrf_token'] = _sec_admin.token_hex(32)  # admin CSRF 토큰
            return redirect('/admin')
        else:
            error = '비밀번호가 올바르지 않습니다.'
    return render_template('admin/login.html', error=error)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect('/admin/login')

@app.route('/admin')
@admin_required
def admin_dashboard():
    data = load_slides()
    inst_data = load_institutions()
    slides = data.get('slides', [])
    institutions = inst_data.get('institutions', [])
    subjects = inst_data.get('subjects', [])
    return render_template('admin/dashboard.html',
        slides=slides,
        institutions=institutions,
        subjects=subjects,
        csrf_token=session.get('admin_csrf_token', ''),
    )

@app.route('/admin/api/slide', methods=['POST'])
@admin_required
@admin_csrf_required
def admin_save_slide():
    # [ROLLBACK] JSON 방식 -- RDS 전환 전 코드
    # try:
    #     payload = request.get_json()
    #     data = load_slides()
    #     slides = data.get('slides', [])
    #     edit_id = payload.pop('edit_id', None)
    #     if edit_id:
    #         for i, s in enumerate(slides):
    #             if s['id'] == edit_id:
    #                 slides[i] = payload
    #                 break
    #     else:
    #         if any(s['id'] == payload['id'] for s in slides):
    #             return jsonify({'ok': False, 'error': '이미 존재하는 ID입니다.'})
    #         slides.append(payload)
    #     data['slides'] = slides
    #     save_slides(data)
    #     return jsonify({'ok': True})
    # except Exception as e:
    #     return jsonify({'ok': False, 'error': str(e)})
    try:
        payload = request.get_json()
        edit_id = payload.pop('edit_id', None)
        subject_code = payload.get('category', '').upper() or None
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
                            subject_code,
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

@app.route('/admin/api/slide/<slide_id>', methods=['DELETE'])
@admin_required
@admin_csrf_required
def admin_delete_slide(slide_id):
    # [ROLLBACK] JSON 방식 -- RDS 전환 전 코드
    # try:
    #     data = load_slides()
    #     data['slides'] = [s for s in data.get('slides', []) if s['id'] != slide_id]
    #     save_slides(data)
    #     return jsonify({'ok': True})
    # except Exception as e:
    #     return jsonify({'ok': False, 'error': str(e)})
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

if __name__ == '__main__':
    print(f"\n✅ SlideAtlas 서버 시작!")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, threaded=True)
