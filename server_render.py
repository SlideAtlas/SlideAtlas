from dotenv import load_dotenv
load_dotenv()

import os
import sys
import threading
import json
from functools import wraps

from flask import Flask, send_file, Response, request, jsonify, session, redirect, url_for, render_template, g
from werkzeug.security import check_password_hash
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

# -- 어드민 템플릿 컨텍스트 프로세서 -------------------------------------------
# admin_role, admin_name, admin_csrf 를 모든 admin/ 템플릿에 자동 주입.
# g.admin_* 는 admin_required / super_admin_required 통과 후 설정된다.
@app.context_processor
def _admin_context():
    return {
        'admin_role': getattr(g, 'admin_role', None),
        'admin_name': getattr(g, 'admin_name', session.get('admin_name', '')),
        'admin_csrf': session.get('admin_csrf_token', ''),
    }

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
                SELECT id, institution_id AS institution,
                       subject_code AS category, subject_code,
                       title_ko, title_en, description,
                       s3_key, s3_minimap_key, s3_thumbnail_key,
                       mpp, width, height,
                       stain, organ AS system,
                       species, original_format AS format,
                       conversion_status, deploy_status,
                       (deploy_status = 'deployed') AS active,
                       reject_reason, knowledge_base,
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

def _get_admin_user():
    """session에서 admin_user_id를 읽어 DB status 확인. 유효하면 dict, 아니면 None."""
    admin_user_id = session.get('admin_user_id')
    if not admin_user_id:
        return None
    try:
        conn = get_db_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, role, name, status FROM admin_users WHERE id = %s",
                    (admin_user_id,),
                )
                row = cur.fetchone()
        finally:
            release_db_conn(conn)
        if row is None or row[3] != 'active':
            return None
        return {'id': row[0], 'role': row[1], 'name': row[2] or ''}
    except Exception:
        return None


def _admin_json_err(message, status):
    resp = jsonify({'ok': False, 'error': message})
    resp.status_code = status
    resp.headers['Cache-Control'] = 'no-store'
    return resp


def admin_required(f):
    """어드민 로그인 + DB status='active' 확인. staff·super_admin 공용."""
    @wraps(f)
    def decorated(*args, **kwargs):
        admin = _get_admin_user()
        if not admin:
            if request.path.startswith('/admin/api/'):
                return _admin_json_err('로그인이 필요합니다', 401)
            return redirect('/admin/login')
        g.admin_user_id = admin['id']
        g.admin_role = admin['role']
        g.admin_name = admin['name']
        return f(*args, **kwargs)
    return decorated


def super_admin_required(f):
    """role='super_admin' 전용. staff가 URL 직접 호출해도 403."""
    @wraps(f)
    def decorated(*args, **kwargs):
        admin = _get_admin_user()
        if not admin:
            if request.path.startswith('/admin/api/'):
                return _admin_json_err('로그인이 필요합니다', 401)
            return redirect('/admin/login')
        if admin['role'] != 'super_admin':
            if request.path.startswith('/admin/api/'):
                return _admin_json_err('권한이 없습니다', 403)
            # HTML 페이지: 대시보드로 리다이렉트 (staff는 운영 페이지 접근 불가)
            return redirect('/admin')
        g.admin_user_id = admin['id']
        g.admin_role = admin['role']
        g.admin_name = admin['name']
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
    """DB에서 slide의 (institution_id, subject_code, deploy_status) 반환. 없으면 None.

    institution_id는 콘텐츠 소유자 표시('SA')일 뿐 접근 격리 기준이 아니다(§6-1·CEO 결정).
    접근 격리는 subject_code(과목 구독)로 한다. 함수명은 호출부 호환을 위해 유지.
    """
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT institution_id, subject_code, deploy_status FROM slides WHERE id = %s",
                (slide_id,),
            )
            return cur.fetchone()
    finally:
        release_db_conn(conn)


def _institution_subject_access(institution_id, subject_code):
    """기관이 해당 과목 콘텐츠 접근권을 보유하는가? (단일 게이트 (3))

    institution_subject_access.granted=TRUE 이거나, (institution_id, subject_code)에
    매칭되는 active 구독의 접근창(access_open_date <= today <= subscription_end)이 열려 있으면 True.
    좌석 플랜(subscriptions)과 콘텐츠 접근권(institution_subject_access)은 직교(§16).
    """
    from auth.decorators import _today_kst
    if not institution_id or not subject_code:
        return False
    today = _today_kst()
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT
                       EXISTS(SELECT 1 FROM institution_subject_access
                               WHERE institution_id = %s AND subject_code = %s AND granted = TRUE)
                       OR
                       EXISTS(SELECT 1 FROM subscriptions
                               WHERE institution_id = %s AND subject_code = %s
                                 AND status = 'active'
                                 AND access_open_date <= %s AND subscription_end >= %s)""",
                (institution_id, subject_code, institution_id, subject_code, today, today),
            )
            return bool(cur.fetchone()[0])
    finally:
        release_db_conn(conn)


def _tile_err(error, message, status=403):
    from flask import g as _g
    resp = jsonify({"success": False, "error": error, "message": message})
    resp.status_code = status
    resp.headers["Cache-Control"] = "no-store, no-cache"
    return resp


def _slide_access_allowed(slide_id):
    """슬라이드 접근 단일 게이트. (허용여부, 에러응답) 튜플.

    ★ 격리 기준은 '슬라이드 기관 == 사용자 기관'(구 유튜브형 화석)이 아니라 '과목 구독'이다.
       콘텐츠는 institution_id='SA'로 채번되며, 'SA'는 소유자 표시일 뿐 공용/기본제공이 아니다(§6-1).

    일반 사용자는 다음 전부(AND) 충족 시에만 접근:
      (1) deploy_status == 'deployed'
      (2) g.subject_code == slide.subject_code   (등록 과목 == 슬라이드 과목)
      (3) 사용자 기관이 그 과목 접근권 보유 (_institution_subject_access)
    is_special: deploy_status=='rejected'만 차단, institution·subject 축은 우회(§15-8).
    """
    from flask import g
    info = get_slide_institution(slide_id)
    if info is None:
        return False, _tile_err("SLIDE_NOT_FOUND", "슬라이드를 찾을 수 없습니다", 404)
    _inst_id, slide_subject, deploy_status = info
    if getattr(g, 'is_special', False):
        # [M1] 특별계정: rejected(반려)만 차단, 나머지(qc_pending/deployed) 허용 (CEO 결정, §15-8).
        # 반려 원본은 품질 문제/재공급 대상이므로 특별계정에도 노출 금지(§15-3 라이선스 격리).
        if deploy_status == 'rejected':
            return False, _tile_err("FORBIDDEN", "반려된 슬라이드입니다", 403)
        return True, None
    # (1) 미배포 슬라이드 학생 접근 불가 (§8 라이선스 격리)
    if deploy_status != 'deployed':
        return False, _tile_err("FORBIDDEN", "접근 권한이 없습니다", 403)
    # (2) 과목 격리: 사용자 등록 과목과 슬라이드 과목 일치 (§0-4·§8 과목 축)
    if slide_subject != getattr(g, 'subject_code', None):
        return False, _tile_err("FORBIDDEN", "접근 권한이 없습니다", 403)
    # (3) 사용자 기관이 그 과목을 구독/접근권 보유
    if not _institution_subject_access(getattr(g, 'institution_id', None), slide_subject):
        return False, _tile_err("FORBIDDEN", "접근 권한이 없습니다", 403)
    return True, None


def _visible_slides(slides):
    """목록/뷰어용 가시 슬라이드 필터 — _slide_access_allowed와 동일 기준의 단일 진실.

    일반 사용자: deploy_status='deployed' AND slide.subject==g.subject_code AND 기관이 그 과목 접근권 보유.
       (2)가 과목 일치를 강제하므로 (3)은 g.subject_code 접근권 1회 확인으로 충분(과목당 N쿼리 회피).
    is_special: rejected만 제외(§15-8 검수 목적).
    """
    from flask import g
    if getattr(g, 'is_special', False):
        return [s for s in slides if s.get('deploy_status') != 'rejected']
    subject = getattr(g, 'subject_code', None)
    inst = getattr(g, 'institution_id', None)
    if not subject or not _institution_subject_access(inst, subject):
        return []
    return [
        s for s in slides
        if s.get('deploy_status') == 'deployed' and s.get('subject_code') == subject
    ]


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

# ── 공지사항 로드 (announcements 테이블 미존재 시 빈 목록 반환) ──
def _load_notices():
    try:
        conn = get_db_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT title, updated_at
                    FROM announcements
                    WHERE is_published = TRUE AND is_archived = FALSE
                    ORDER BY display_order ASC, updated_at DESC
                    LIMIT 5
                """)
                rows = cur.fetchall()
                return [
                    {
                        'title': r[0],
                        'date': r[1].strftime('%Y.%m.%d') if r[1] else '',
                    }
                    for r in rows
                ]
        finally:
            release_db_conn(conn)
    except Exception:
        return []


# ── 랜딩페이지 ──
@app.route('/')
def landing():
    is_logged = bool(request.cookies.get('access_token'))
    notices = _load_notices()
    return render_template('landing.html', is_logged=is_logged, notices=notices)


@app.route('/login')
def login_page():
    is_logged = bool(request.cookies.get('access_token'))
    # 이미 로그인 상태이면 홈으로 리다이렉트
    if is_logged:
        return redirect('/')
    next_url = request.args.get('next', '/slides')
    # 오픈 리다이렉트 방어: '/'로 시작하는 내부 경로만 허용
    if not next_url.startswith('/') or next_url.startswith('//'):
        next_url = '/slides'
    return render_template('login.html', is_logged=is_logged, next=next_url)


@app.route('/viewer')
@page_login_required
def viewer_default():
    data = load_slides()
    slides = _visible_slides(data.get('slides', []))
    if slides:
        return redirect(f'/viewer/{slides[0]["id"]}')
    return redirect('/')

@app.route('/viewer/<slide_id>')
@page_login_required
def viewer(slide_id):
    data = load_slides()
    slide_info = next((s for s in data.get('slides', []) if s['id'] == slide_id), None)
    if not slide_info:
        return redirect('/slides')
    # 단일 게이트: 과목 구독 기준 접근 판정 — 타일 토큰 발급(아래) 전 반드시 통과 (§8 라이선스 격리).
    allowed, _aerr = _slide_access_allowed(slide_id)
    if not allowed:
        return redirect('/slides')

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
    data = load_slides()
    # 단일 게이트: 과목 구독 기준으로 가시 슬라이드 필터 (기관 일치 화석 제거, §6-1·§8)
    all_slides = _visible_slides(data.get('slides', []))
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

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    # 이미 로그인된 어드민은 대시보드로
    if session.get('admin_user_id') and _get_admin_user():
        return redirect('/admin')

    error = ''
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        if not email or not password:
            error = '이메일과 비밀번호를 입력하세요.'
        else:
            conn = get_db_conn()
            conn.autocommit = False
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id, password_hash, role, name, status FROM admin_users"
                        " WHERE lower(email) = %s",
                        (email,),
                    )
                    row = cur.fetchone()
                    if row is None:
                        error = '이메일 또는 비밀번호가 올바르지 않습니다.'
                    else:
                        admin_id, pw_hash, role, name, status = row
                        if status != 'active':
                            error = '비활성화된 계정입니다. 관리자에게 문의하세요.'
                        elif not check_password_hash(pw_hash, password):
                            error = '이메일 또는 비밀번호가 올바르지 않습니다.'
                        else:
                            cur.execute(
                                "UPDATE admin_users SET last_login = NOW() WHERE id = %s",
                                (admin_id,),
                            )
                            conn.commit()
                            import secrets as _sec_admin
                            session.clear()
                            session['admin_user_id'] = admin_id
                            session['admin_role'] = role
                            session['admin_name'] = name or email.split('@')[0]
                            session['admin_csrf_token'] = _sec_admin.token_hex(32)
                            return redirect('/admin')
            except Exception:
                conn.rollback()
                error = '처리 중 오류가 발생했습니다.'
            finally:
                try:
                    conn.autocommit = True
                except Exception:
                    pass
                release_db_conn(conn)

    return render_template('admin/login.html', error=error)


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_user_id', None)
    session.pop('admin_role', None)
    session.pop('admin_name', None)
    session.pop('admin_csrf_token', None)
    return redirect('/admin/login')


@app.route('/admin')
@admin_required
def admin_dashboard():
    return render_template('admin/dashboard.html', active_page='dash')


def _term_label(term: str) -> str:
    """'2026-fall' → {'year':'2026', 'season':'가을'}"""
    parts = term.split('-')
    if len(parts) == 2:
        season = {'spring': '봄', 'fall': '가을'}.get(parts[1], parts[1])
        return f'{parts[0]} {season}'
    return term


@app.route('/admin/api/dashboard', methods=['GET'])
@admin_required
def api_dashboard():
    from datetime import date, timedelta
    today = date.today()
    d90   = today + timedelta(days=90)

    conn = get_db_conn()
    try:
        with conn.cursor() as cur:

            # ── KPI 1: 활성 구독 기관 수 ──
            cur.execute("""
                SELECT COUNT(DISTINCT institution_id) FROM subscriptions
                WHERE status = 'active' AND subscription_end >= %s
            """, (today,))
            active_inst = cur.fetchone()[0] or 0

            # ── KPI 2: 이번 학기 확정 매출 (현재 접근 가능한 구독만) ──
            cur.execute("""
                SELECT COALESCE(SUM(fee), 0) FROM subscriptions
                WHERE status = 'active'
                  AND access_open_date <= %s
                  AND subscription_end >= %s
                  AND fee IS NOT NULL
            """, (today, today))
            current_revenue = int(cur.fetchone()[0] or 0)

            # ── KPI 3: 활성 사용자 / 좌석 ──
            cur.execute("""
                SELECT COUNT(*) FROM users
                WHERE COALESCE(status, 'active') = 'active'
                  AND COALESCE(is_special, FALSE) = FALSE
            """)
            active_users = cur.fetchone()[0] or 0

            cur.execute("""
                SELECT COALESCE(SUM(max_seats), 0) FROM subscriptions
                WHERE status = 'active' AND subscription_end >= %s
            """, (today,))
            total_seats = int(cur.fetchone()[0] or 0)

            # ── KPI 4: 만료 임박 D-90 ──
            cur.execute("""
                SELECT COUNT(DISTINCT institution_id) FROM subscriptions
                WHERE status = 'active'
                  AND subscription_end >= %s
                  AND subscription_end <= %s
            """, (today, d90))
            expiring_d90 = cur.fetchone()[0] or 0

            # ── 만료 임박 리스트 ──
            cur.execute("""
                SELECT s.institution_id, i.name_ko, s.subject_code,
                       s.subscription_end,
                       (s.subscription_end - %s) AS days_left
                FROM subscriptions s
                JOIN institutions i ON s.institution_id = i.id
                WHERE s.status = 'active' AND s.subscription_end >= %s
                ORDER BY s.subscription_end ASC
                LIMIT 10
            """, (today, today))
            expiry_rows = cur.fetchall()
            expiry_list = []
            for r in expiry_rows:
                dl = r[4]
                if dl <= 90:
                    dday_color = 'danger'
                elif dl <= 180:
                    dday_color = 'warn'
                else:
                    dday_color = 'ok'
                expiry_list.append({
                    'inst_id':   r[0],
                    'inst_name': r[1],
                    'subject':   r[2],
                    'end_date':  r[3].isoformat(),
                    'days_left': dl,
                    'color':     dday_color,
                })

            # ── 학기별 매출 추이 ──
            cur.execute("""
                SELECT start_term,
                       COALESCE(SUM(fee), 0) AS total_fee,
                       MIN(access_open_date) AS term_opens
                FROM subscriptions
                WHERE fee IS NOT NULL
                GROUP BY start_term
                ORDER BY start_term ASC
                LIMIT 8
            """)
            rev_rows = cur.fetchall()
            rev_max = max((r[1] for r in rev_rows), default=1) or 1
            revenue_trend = [{
                'term':   r[0],
                'label':  _term_label(r[0]),
                'fee':    int(r[1]),
                'pct':    round(r[1] / rev_max * 100),
                'future': r[2] > today if r[2] else False,
            } for r in rev_rows]

            # ── 파이프라인 현황 ──
            cur.execute("""
                SELECT
                  COUNT(*) FILTER (WHERE deploy_status = 'deployed')                                          AS deployed,
                  COUNT(*) FILTER (WHERE deploy_status = 'qc_pending'
                                     AND conversion_status IN ('ready','ready_no_mpp'))                       AS qc_pending,
                  COUNT(*) FILTER (WHERE conversion_status IN ('pending','converting','qc_check'))            AS processing,
                  COUNT(*) FILTER (WHERE conversion_status = 'failed' OR deploy_status = 'rejected')         AS failed_rejected
                FROM slides
            """)
            p = cur.fetchone()
            pipeline = {
                'deployed':        p[0] or 0,
                'qc_pending':      p[1] or 0,
                'processing':      p[2] or 0,
                'failed_rejected': p[3] or 0,
            }

            # ── 처리 대기 ──
            open_inquiries = 0
            try:
                cur.execute("SELECT COUNT(*) FROM inquiries WHERE status = 'open'")
                open_inquiries = cur.fetchone()[0] or 0
            except Exception:
                conn.rollback()

            cur.execute("""
                SELECT COUNT(*) FROM slides
                WHERE deploy_status = 'qc_pending'
                  AND conversion_status IN ('ready','ready_no_mpp')
            """)
            qc_pending_slides = cur.fetchone()[0] or 0

            cur.execute("""
                SELECT COUNT(*) FROM slides WHERE conversion_status = 'ready_no_mpp'
            """)
            mpp_missing = cur.fetchone()[0] or 0

        util_pct = round(active_users / total_seats * 100) if total_seats else 0

        return jsonify({
            'ok': True,
            'kpi': {
                'active_inst':     active_inst,
                'current_revenue': current_revenue,
                'active_users':    active_users,
                'total_seats':     total_seats,
                'util_pct':        util_pct,
                'expiring_d90':    expiring_d90,
            },
            'expiry_list':    expiry_list,
            'revenue_trend':  revenue_trend,
            'pipeline':       pipeline,
            'todo': {
                'open_inquiries':   open_inquiries,
                'qc_pending_slides': qc_pending_slides,
                'mpp_missing':      mpp_missing,
                'expiring_renewals': expiring_d90,
            },
        })
    finally:
        release_db_conn(conn)

# ── 슬라이드 관리 (S5-3) ─────────────────────────────────────

@app.route('/admin/slides')
@super_admin_required
def admin_slides_page():
    return render_template('admin/slides.html', active_page='slide')


@app.route('/admin/api/slides/list', methods=['GET'])
@super_admin_required
def api_slides_list():
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, institution_id, subject_code,
                       title_ko, title_en, organ, stain, species,
                       original_format, mpp,
                       conversion_status, deploy_status, reject_reason,
                       knowledge_base,
                       license_source, created_at
                FROM slides
                ORDER BY created_at DESC
            """)
            cols = [d[0] for d in cur.description]
            slides = []
            for row in cur.fetchall():
                s = dict(zip(cols, row))
                s['created_at'] = str(s['created_at'])
                if s['knowledge_base']:
                    try:
                        s['knowledge_base'] = s['knowledge_base'] if isinstance(s['knowledge_base'], dict) else json.loads(s['knowledge_base'])
                    except Exception:
                        s['knowledge_base'] = {}
                slides.append(s)

        # 상태 칩 카운트
        counts = {
            'total': len(slides),
            'processing': sum(1 for s in slides if s['conversion_status'] in ('pending', 'converting', 'qc_check')),
            'qc_pending': sum(1 for s in slides if s['conversion_status'] == 'ready' and s['deploy_status'] == 'qc_pending'),
            'no_mpp': sum(1 for s in slides if s['conversion_status'] == 'ready_no_mpp'),
            'failed': sum(1 for s in slides if s['conversion_status'] == 'failed' or s['deploy_status'] == 'rejected'),
            'deployed': sum(1 for s in slides if s['deploy_status'] == 'deployed'),
        }
        return jsonify({'ok': True, 'slides': slides, 'counts': counts})
    finally:
        release_db_conn(conn)


@app.route('/admin/api/slides/<slide_id>/deploy', methods=['POST'])
@super_admin_required
@admin_csrf_required
def api_slide_deploy(slide_id):
    conn = get_db_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE slides SET deploy_status='deployed', reject_reason=NULL
                    WHERE id=%s AND conversion_status='ready' AND deploy_status='qc_pending'
                    RETURNING id
                """, (slide_id,))
                if not cur.fetchone():
                    return jsonify({'ok': False, 'error': '배포 가능 상태가 아닙니다'}), 409
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        release_db_conn(conn)


@app.route('/admin/api/slides/<slide_id>/revoke', methods=['POST'])
@super_admin_required
@admin_csrf_required
def api_slide_revoke(slide_id):
    conn = get_db_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE slides SET deploy_status='qc_pending'
                    WHERE id=%s AND deploy_status='deployed'
                    RETURNING id
                """, (slide_id,))
                if not cur.fetchone():
                    return jsonify({'ok': False, 'error': '배포 중 상태가 아닙니다'}), 409
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        release_db_conn(conn)


@app.route('/admin/api/slides/<slide_id>/reject', methods=['POST'])
@super_admin_required
@admin_csrf_required
def api_slide_reject(slide_id):
    data = request.get_json(silent=True) or {}
    reason = (data.get('reason') or '').strip()
    detail = (data.get('detail') or '').strip()
    reject_reason = f'{reason}: {detail}' if detail else reason
    if not reject_reason:
        return jsonify({'ok': False, 'error': '반려 사유는 필수입니다'}), 400
    conn = get_db_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE slides SET deploy_status='rejected', reject_reason=%s
                    WHERE id=%s AND deploy_status IN ('qc_pending', 'deployed')
                    RETURNING id
                """, (reject_reason, slide_id))
                if not cur.fetchone():
                    return jsonify({'ok': False, 'error': '반려 가능 상태가 아닙니다'}), 409
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        release_db_conn(conn)


@app.route('/admin/api/slides/<slide_id>/mpp', methods=['POST'])
@super_admin_required
@admin_csrf_required
def api_slide_set_mpp(slide_id):
    data = request.get_json(silent=True) or {}
    try:
        mpp_val = float(data.get('mpp', 0))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': '유효한 MPP 값이 아닙니다'}), 400
    if mpp_val <= 0 or mpp_val > 10:
        return jsonify({'ok': False, 'error': 'MPP 범위를 확인하세요 (0 초과 10 이하)'}), 400
    conn = get_db_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE slides SET mpp=%s, conversion_status='pending'
                    WHERE id=%s AND conversion_status='ready_no_mpp'
                    RETURNING id
                """, (mpp_val, slide_id))
                if not cur.fetchone():
                    return jsonify({'ok': False, 'error': 'MPP 없음 상태가 아닙니다'}), 409
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        release_db_conn(conn)


@app.route('/admin/api/slides/<slide_id>/kb', methods=['PUT'])
@super_admin_required
@admin_csrf_required
def api_slide_kb(slide_id):
    data = request.get_json(silent=True) or {}
    kb = data.get('knowledge_base')
    deploy_after = data.get('deploy', False)
    if kb is None:
        return jsonify({'ok': False, 'error': 'knowledge_base 누락'}), 400
    conn = get_db_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                if deploy_after:
                    cur.execute("""
                        UPDATE slides SET knowledge_base=%s, deploy_status='deployed', reject_reason=NULL
                        WHERE id=%s AND conversion_status='ready' AND deploy_status='qc_pending'
                        RETURNING id
                    """, (json.dumps(kb, ensure_ascii=False), slide_id))
                else:
                    cur.execute("""
                        UPDATE slides SET knowledge_base=%s WHERE id=%s RETURNING id
                    """, (json.dumps(kb, ensure_ascii=False), slide_id))
                if not cur.fetchone():
                    return jsonify({'ok': False, 'error': '슬라이드를 찾을 수 없거나 배포 불가 상태입니다'}), 409
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        release_db_conn(conn)


@app.route('/admin/api/slides/batch', methods=['POST'])
@super_admin_required
@admin_csrf_required
def api_slides_batch():
    data = request.get_json(silent=True) or {}
    action = data.get('action')  # 'deploy' | 'reject'
    ids = data.get('ids') or []
    if not ids or action not in ('deploy', 'reject'):
        return jsonify({'ok': False, 'error': '잘못된 요청'}), 400
    if len(ids) > 200:
        return jsonify({'ok': False, 'error': '한 번에 최대 200건'}), 400

    conn = get_db_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                if action == 'deploy':
                    cur.execute("""
                        UPDATE slides SET deploy_status='deployed', reject_reason=NULL
                        WHERE id = ANY(%s) AND conversion_status='ready' AND deploy_status='qc_pending'
                    """, (ids,))
                else:
                    reason = (data.get('reason') or '일괄 반려').strip()
                    cur.execute("""
                        UPDATE slides SET deploy_status='rejected', reject_reason=%s
                        WHERE id = ANY(%s) AND deploy_status IN ('qc_pending', 'deployed')
                    """, (reason, ids))
                updated = cur.rowcount
        return jsonify({'ok': True, 'updated': updated})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        release_db_conn(conn)


@app.route('/admin/api/slides/add', methods=['POST'])
@super_admin_required
@admin_csrf_required
def api_slide_add():
    """개별 슬라이드 추가 (메타데이터). 파일 업로드는 파이프라인 별도 처리."""
    data = request.get_json(silent=True) or {}
    subject_code = (data.get('subject_code') or '').upper()
    title_ko = (data.get('title_ko') or '').strip()
    if not subject_code or not title_ko:
        return jsonify({'ok': False, 'error': '과목·제목(한국어)은 필수입니다'}), 400

    conn = get_db_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                # SA-{SUBJECT} 접두사로 다음 채번
                cur.execute("""
                    SELECT id FROM slides WHERE id LIKE %s ORDER BY id DESC LIMIT 1
                """, (f'SA-{subject_code}-%',))
                last = cur.fetchone()
                if last:
                    try:
                        last_num = int(last[0].split('-')[-1])
                    except ValueError:
                        last_num = 0
                    next_num = last_num + 1
                else:
                    next_num = 1
                new_id = f'SA-{subject_code}-{next_num:03d}'

                cur.execute("""
                    INSERT INTO slides (
                        id, institution_id, subject_code,
                        title_ko, title_en, description,
                        stain, organ, species, license_source,
                        original_format, conversion_status, deploy_status
                    ) VALUES (%s,'SA',%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending','qc_pending')
                """, (
                    new_id, subject_code,
                    title_ko,
                    (data.get('title_en') or '').strip() or None,
                    (data.get('description') or '').strip() or None,
                    (data.get('stain') or '').strip() or None,
                    (data.get('organ') or '').strip() or None,
                    (data.get('species') or 'human').strip(),
                    (data.get('license_source') or '').strip() or None,
                    (data.get('original_format') or '').upper() or None,
                ))
        return jsonify({'ok': True, 'id': new_id})
    except psycopg2.IntegrityError:
        return jsonify({'ok': False, 'error': f'ID {new_id} 충돌. 재시도하세요'}), 409
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        release_db_conn(conn)


@app.route('/admin/api/slide', methods=['POST'])
@super_admin_required
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
@super_admin_required
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

# ── 기관 관리 (S5-2) ──────────────────────────────────────

import calendar as _calendar
from datetime import date as _date


def _sem_dates(term: str):
    """'2026-fall' → (access_open_date, subscription_end) as date objects.
    윤년은 calendar.monthrange로 자동 처리."""
    year_s, season = term.split('-')
    year = int(year_s)
    if season == 'spring':
        return _date(year, 2, 1), _date(year, 8, 31)
    else:  # fall
        last_feb = _calendar.monthrange(year + 1, 2)[1]
        return _date(year, 8, 1), _date(year + 1, 2, last_feb)


def _sub_status(open_date, end_date):
    today = _date.today()
    if end_date < today:
        return 'expired', '만료'
    if open_date <= today:
        return 'active', '구독중'
    delta = (open_date - today).days
    if delta <= 60:
        return 'upcoming', '오픈예정'
    return 'pending', '대기'


def _next_term(term: str) -> str:
    year_s, season = term.split('-')
    year = int(year_s)
    return f'{year}-fall' if season == 'spring' else f'{year + 1}-spring'


def _term_end_after(start_term: str, term_count: int) -> str:
    """start_term 에서 term_count 학기 후의 마지막 학기 식별자."""
    year_s, season = start_term.split('-')
    year = int(year_s)
    idx = year * 2 + (0 if season == 'spring' else 1)
    idx += term_count - 1
    return f'{idx // 2}-{"spring" if idx % 2 == 0 else "fall"}'


PLAN_SEATS = {'department': 50, 'standard': 150, 'campus': 300, 'institution': 500}


@app.route('/admin/institutions')
@super_admin_required
def admin_institutions_page():
    return render_template('admin/institutions.html', active_page='inst')


@app.route('/admin/api/institutions', methods=['GET'])
@super_admin_required
def api_institutions_list():
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT i.id, i.name_ko, i.name_en, i.university, i.college, i.domain,
                       i.admin_contacts
                FROM institutions i
                ORDER BY i.name_ko
            """)
            cols = [d[0] for d in cur.description]
            insts = [dict(zip(cols, r)) for r in cur.fetchall()]

            for inst in insts:
                # used_seats: institution_rosters가 아직 없을 수 있으므로 0으로 폴백
                try:
                    cur.execute("""
                        SELECT subject_code, COUNT(*) AS used_seats
                        FROM institution_rosters
                        WHERE institution_id = %s
                        GROUP BY subject_code
                    """, (inst['id'],))
                    used_map = {r[0]: r[1] for r in cur.fetchall()}
                except Exception:
                    conn.rollback()
                    used_map = {}

                cur.execute("""
                    SELECT id, subject_code, plan, max_seats,
                           start_term, term_count,
                           access_open_date, subscription_end,
                           fee, payment_method, status
                    FROM subscriptions
                    WHERE institution_id = %s
                    ORDER BY subscription_end DESC
                """, (inst['id'],))
                scols = [d[0] for d in cur.description]
                subs = []
                for row in cur.fetchall():
                    sub = dict(zip(scols, row))
                    open_d = sub['access_open_date']
                    end_d = sub['subscription_end']
                    today = _date.today()
                    status_key, status_label = _sub_status(open_d, end_d)
                    if status_key == 'active':
                        dday = f'D-{(end_d - today).days} 만료'
                    elif status_key in ('upcoming', 'pending'):
                        dday = f'D-{(open_d - today).days} 오픈'
                    else:
                        dday = f'D+{(today - end_d).days} 만료'
                    sub['status_key'] = status_key
                    sub['status_label'] = status_label
                    sub['dday'] = dday
                    sub['used_seats'] = used_map.get(sub['subject_code'], 0)
                    sub['access_open_date'] = str(open_d)
                    sub['subscription_end'] = str(end_d)
                    # 이력 (갱신 모달용)
                    cur.execute("""
                        SELECT event, plan, max_seats, start_term, term_count, fee, note, created_at
                        FROM subscription_history
                        WHERE subscription_id = %s
                        ORDER BY created_at
                    """, (sub['id'],))
                    hcols = [d[0] for d in cur.description]
                    sub['history'] = [
                        {**dict(zip(hcols, h)), 'created_at': str(h[-1])}
                        for h in cur.fetchall()
                    ]
                    subs.append(sub)
                inst['subscriptions'] = subs
                inst['admin_contacts'] = inst.get('admin_contacts') or []

        return jsonify({'ok': True, 'institutions': insts})
    finally:
        release_db_conn(conn)


@app.route('/admin/api/institutions', methods=['POST'])
@super_admin_required
@admin_csrf_required
def api_institution_create():
    data = request.get_json(silent=True) or {}
    inst_id = (data.get('id') or '').strip().upper()
    university = (data.get('university') or '').strip()
    college = (data.get('college') or '').strip()
    name_en = (data.get('name_en') or '').strip() or None
    domain = (data.get('domain') or '').strip() or None
    contacts = data.get('admin_contacts') or []
    subs_data = data.get('subscriptions') or []

    if not inst_id or not university or not college:
        return jsonify({'ok': False, 'error': '기관코드·학교명·단과대는 필수입니다'}), 400
    if not inst_id.replace('-', '').replace('_', '').isalnum():
        return jsonify({'ok': False, 'error': '기관코드는 영문·숫자·하이픈만 허용됩니다'}), 400
    if len(contacts) > 5:
        return jsonify({'ok': False, 'error': '관리자는 최대 5명입니다'}), 400

    name_ko = f'{university} {college}'
    conn = get_db_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM institutions WHERE id = %s", (inst_id,))
                if cur.fetchone():
                    return jsonify({'ok': False, 'error': f'기관코드 {inst_id}는 이미 사용 중입니다'}), 409

                cur.execute("""
                    INSERT INTO institutions (id, name_ko, name_en, university, college, domain, admin_contacts)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (inst_id, name_ko, name_en, university, college, domain,
                      json.dumps(contacts, ensure_ascii=False)))

                for sub in subs_data:
                    start_term = sub.get('start_term', '')
                    term_count = int(sub.get('term_count', 1))
                    plan = (sub.get('plan') or '').lower()
                    max_seats = int(sub.get('max_seats') or PLAN_SEATS.get(plan, 0))
                    subject_code = (sub.get('subject_code') or '').upper()
                    _fee_raw = sub.get('fee')
                    fee = int(str(_fee_raw).replace(',', '')) if _fee_raw else None
                    payment_method = sub.get('payment_method') or '학기 선불'
                    if not start_term or not subject_code:
                        continue
                    end_term = _term_end_after(start_term, term_count)
                    open_date, _ = _sem_dates(start_term)
                    _, end_date = _sem_dates(end_term)
                    cur.execute("""
                        INSERT INTO subscriptions
                            (institution_id, subject_code, plan, max_seats,
                             start_term, term_count, access_open_date, subscription_end,
                             fee, payment_method)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (inst_id, subject_code, plan, max_seats,
                          start_term, term_count, open_date, end_date,
                          fee, payment_method))
                    sub_id = cur.fetchone()[0]
                    cur.execute("""
                        INSERT INTO subscription_history
                            (subscription_id, event, plan, max_seats, start_term, term_count, fee, created_by)
                        VALUES (%s, 'initial', %s, %s, %s, %s, %s, %s)
                    """, (sub_id, plan, max_seats, start_term, term_count, fee,
                          g.admin_user_id))

                    cur.execute("""
                        INSERT INTO institution_subject_access (institution_id, subject_code)
                        VALUES (%s, %s)
                        ON CONFLICT DO NOTHING
                    """, (inst_id, subject_code))

        return jsonify({'ok': True, 'id': inst_id})
    except psycopg2.IntegrityError as e:
        return jsonify({'ok': False, 'error': str(e)}), 409
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        release_db_conn(conn)


@app.route('/admin/api/institutions/<inst_id>', methods=['GET'])
@super_admin_required
def api_institution_detail(inst_id):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name_ko, name_en, university, college, domain, admin_contacts
                FROM institutions WHERE id = %s
            """, (inst_id,))
            row = cur.fetchone()
            if not row:
                return jsonify({'ok': False, 'error': '기관을 찾을 수 없습니다'}), 404
            cols = [d[0] for d in cur.description]
            inst = dict(zip(cols, row))
            inst['admin_contacts'] = inst.get('admin_contacts') or []

            cur.execute("""
                SELECT s.id, s.subject_code, s.plan, s.max_seats,
                       s.start_term, s.term_count,
                       s.access_open_date, s.subscription_end,
                       s.fee, s.payment_method, s.status
                FROM subscriptions s
                WHERE s.institution_id = %s
                ORDER BY s.created_at
            """, (inst_id,))
            scols = [d[0] for d in cur.description]
            subs = []
            for sr in cur.fetchall():
                sub = dict(zip(scols, sr))
                sub['access_open_date'] = str(sub['access_open_date'])
                sub['subscription_end'] = str(sub['subscription_end'])
                cur.execute("""
                    SELECT event, plan, max_seats, start_term, term_count, fee, note, created_at
                    FROM subscription_history
                    WHERE subscription_id = %s
                    ORDER BY created_at
                """, (sub['id'],))
                hcols = [d[0] for d in cur.description]
                sub['history'] = [dict(zip(hcols, h)) for h in cur.fetchall()]
                for h in sub['history']:
                    h['created_at'] = str(h['created_at'])
                subs.append(sub)
            inst['subscriptions'] = subs

        return jsonify({'ok': True, 'institution': inst})
    finally:
        release_db_conn(conn)


@app.route('/admin/api/institutions/<inst_id>', methods=['PUT'])
@super_admin_required
@admin_csrf_required
def api_institution_update(inst_id):
    data = request.get_json(silent=True) or {}
    university = (data.get('university') or '').strip()
    college = (data.get('college') or '').strip()
    if not university or not college:
        return jsonify({'ok': False, 'error': '학교명·단과대는 필수입니다'}), 400
    name_ko = f'{university} {college}'
    name_en = (data.get('name_en') or '').strip() or None
    domain = (data.get('domain') or '').strip() or None
    contacts = data.get('admin_contacts') or []
    if len(contacts) > 5:
        return jsonify({'ok': False, 'error': '관리자는 최대 5명입니다'}), 400

    conn = get_db_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE institutions
                    SET name_ko=%s, name_en=%s, university=%s, college=%s,
                        domain=%s, admin_contacts=%s
                    WHERE id=%s
                """, (name_ko, name_en, university, college, domain,
                      json.dumps(contacts, ensure_ascii=False), inst_id))
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        release_db_conn(conn)


@app.route('/admin/api/institutions/<inst_id>/subscriptions', methods=['POST'])
@super_admin_required
@admin_csrf_required
def api_subscription_add(inst_id):
    data = request.get_json(silent=True) or {}
    start_term = data.get('start_term', '')
    term_count = int(data.get('term_count', 1))
    plan = (data.get('plan') or '').lower()
    max_seats = int(data.get('max_seats') or PLAN_SEATS.get(plan, 0))
    subject_code = (data.get('subject_code') or '').upper()
    _fee_raw = data.get('fee')
    fee = int(str(_fee_raw).replace(',', '')) if _fee_raw else None
    payment_method = data.get('payment_method') or '학기 선불'

    if not start_term or not subject_code or not plan:
        return jsonify({'ok': False, 'error': '필수 항목 누락'}), 400

    end_term = _term_end_after(start_term, term_count)
    open_date, _ = _sem_dates(start_term)
    _, end_date = _sem_dates(end_term)

    conn = get_db_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM institutions WHERE id=%s", (inst_id,))
                if not cur.fetchone():
                    return jsonify({'ok': False, 'error': '기관을 찾을 수 없습니다'}), 404
                cur.execute("""
                    INSERT INTO subscriptions
                        (institution_id, subject_code, plan, max_seats,
                         start_term, term_count, access_open_date, subscription_end,
                         fee, payment_method)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (inst_id, subject_code, plan, max_seats,
                      start_term, term_count, open_date, end_date,
                      fee, payment_method))
                sub_id = cur.fetchone()[0]
                cur.execute("""
                    INSERT INTO subscription_history
                        (subscription_id, event, plan, max_seats, start_term, term_count, fee, created_by)
                    VALUES (%s, 'initial', %s, %s, %s, %s, %s, %s)
                """, (sub_id, plan, max_seats, start_term, term_count, fee, g.admin_user_id))
                cur.execute("""
                    INSERT INTO institution_subject_access (institution_id, subject_code)
                    VALUES (%s, %s) ON CONFLICT DO NOTHING
                """, (inst_id, subject_code))
        return jsonify({'ok': True, 'subscription_id': sub_id})
    except psycopg2.IntegrityError:
        return jsonify({'ok': False, 'error': '이미 동일 기관·과목·시작학기 구독이 존재합니다'}), 409
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        release_db_conn(conn)


@app.route('/admin/api/institutions/<inst_id>/subscriptions/<int:sub_id>/renew', methods=['POST'])
@super_admin_required
@admin_csrf_required
def api_subscription_renew(inst_id, sub_id):
    data = request.get_json(silent=True) or {}
    plan = (data.get('plan') or '').lower()
    extra_seats = int(data.get('extra_seats') or 0)
    term_count = int(data.get('term_count', 1))
    _fee_raw = data.get('fee')
    fee = int(str(_fee_raw).replace(',', '')) if _fee_raw else None
    payment_method = data.get('payment_method') or '학기 선불'
    note = data.get('note') or None

    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT institution_id, subject_code, plan, max_seats, start_term, term_count,
                       subscription_end
                FROM subscriptions WHERE id=%s AND institution_id=%s
            """, (sub_id, inst_id))
            row = cur.fetchone()
        if not row:
            return jsonify({'ok': False, 'error': '구독을 찾을 수 없습니다'}), 404
        _, subject_code, old_plan, old_seats, old_start, old_count, old_end = row
        new_plan = plan or old_plan
        new_seats = (PLAN_SEATS.get(new_plan, old_seats) + extra_seats) if plan else (old_seats + extra_seats)
        old_end_term = _term_end_after(old_start, old_count)
        new_start = _next_term(old_end_term)
        end_term = _term_end_after(new_start, term_count)
        open_date, _ = _sem_dates(new_start)
        _, end_date = _sem_dates(end_term)

        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO subscriptions
                        (institution_id, subject_code, plan, max_seats,
                         start_term, term_count, access_open_date, subscription_end,
                         fee, payment_method)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (inst_id, subject_code, new_plan, new_seats,
                      new_start, term_count, open_date, end_date,
                      fee, payment_method))
                new_sub_id = cur.fetchone()[0]
                cur.execute("""
                    INSERT INTO subscription_history
                        (subscription_id, event, plan, max_seats, start_term, term_count, fee, note, created_by)
                    VALUES (%s, 'renewal', %s, %s, %s, %s, %s, %s, %s)
                """, (new_sub_id, new_plan, new_seats, new_start, term_count, fee, note, g.admin_user_id))
        return jsonify({'ok': True, 'subscription_id': new_sub_id,
                        'start_term': new_start, 'end_term': end_term,
                        'access_open_date': str(open_date),
                        'subscription_end': str(end_date)})
    except psycopg2.IntegrityError:
        return jsonify({'ok': False, 'error': '해당 학기 구독이 이미 존재합니다'}), 409
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        release_db_conn(conn)


# ── 접근 제어 (S5-4) ─────────────────────────────────────────

# v1.0: is_active 컬럼 없이 코드 파생.
# subject_codes 테이블에 is_active BOOLEAN 컬럼 추가는 두 번째 모듈 출시 시 ALTER로 진행.
_ACTIVE_SUBJECTS = frozenset({'HST'})   # v1.0: 조직학만 활성


@app.route('/admin/access')
@super_admin_required
def admin_access_page():
    return render_template('admin/access.html', active_page='access')


@app.route('/admin/api/access/modules', methods=['GET'])
@super_admin_required
def api_access_modules():
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT code, name_ko, name_en FROM subject_codes ORDER BY code")
            subjects = [{'code': r[0], 'name_ko': r[1], 'name_en': r[2]} for r in cur.fetchall()]

            cur.execute("""
                SELECT subject_code, COUNT(*) AS cnt
                FROM slides
                WHERE deploy_status = 'deployed'
                GROUP BY subject_code
            """)
            slide_counts = {r[0]: r[1] for r in cur.fetchall()}

        modules = []
        for s in subjects:
            code = s['code']
            is_active = code in _ACTIVE_SUBJECTS
            modules.append({
                'code': code,
                'name_ko': s['name_ko'],
                'name_en': s['name_en'],
                'is_active': is_active,
                'slide_count': slide_counts.get(code, 0),
                'grant_mode': '전 구독 자동 부여 (기본 모듈)' if is_active else '기관별 토글 (출시 후)',
                'addon': '—' if is_active else '과목별 독립 좌석',
            })
        return jsonify({'ok': True, 'modules': modules})
    finally:
        release_db_conn(conn)


@app.route('/admin/api/access/matrix', methods=['GET'])
@super_admin_required
def api_access_matrix():
    """기관×과목 접근 매트릭스. 읽기 전용 (v1.0 미리보기)."""
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name_ko FROM institutions ORDER BY name_ko")
            institutions = [{'id': r[0], 'name_ko': r[1]} for r in cur.fetchall()]

            # 매트릭스 열: 주요 과목만 (HST·PATH·PARA)
            matrix_subjects = ['HST', 'PATH', 'PARA']

            cur.execute("""
                SELECT institution_id, subject_code, granted
                FROM institution_subject_access
                WHERE subject_code = ANY(%s)
            """, (matrix_subjects,))
            access_map = {}
            for inst_id, subj, granted in cur.fetchall():
                access_map.setdefault(inst_id, {})[subj] = granted

        matrix = []
        for inst in institutions:
            row = {'id': inst['id'], 'name_ko': inst['name_ko'], 'access': {}}
            for subj in matrix_subjects:
                if subj in _ACTIVE_SUBJECTS:
                    # HST: 항상 true (잠김)
                    row['access'][subj] = {'granted': True, 'locked': True}
                else:
                    granted = access_map.get(inst['id'], {}).get(subj, False)
                    row['access'][subj] = {'granted': granted, 'locked': True}  # v1.0: 모두 잠김(미리보기)
            matrix.append(row)

        return jsonify({'ok': True, 'subjects': matrix_subjects, 'matrix': matrix})
    finally:
        release_db_conn(conn)


# ── 이용 리포트 (S5-5) ───────────────────────────────────

@app.route('/admin/reports')
@super_admin_required
def admin_reports_page():
    return render_template('admin/reports.html', active_page='reports')


def _reports_date_range(period: str, inst_id: str, subject_code: str, conn):
    """기간 파라미터 → (start_date, end_date) 또는 (None, None)."""
    from datetime import date, timedelta
    if period == '30d':
        today = date.today()
        return today - timedelta(days=30), today
    if period == 'all':
        return None, None
    # 기본: 현재 활성 구독 기간
    with conn.cursor() as cur:
        cur.execute("""
            SELECT access_open_date, subscription_end
            FROM subscriptions
            WHERE institution_id = %s AND subject_code = %s
              AND status = 'active'
            ORDER BY subscription_end DESC LIMIT 1
        """, (inst_id, subject_code))
        row = cur.fetchone()
    if row:
        return row[0], row[1]
    return None, None


@app.route('/admin/api/reports/institutions', methods=['GET'])
@super_admin_required
def api_reports_institutions():
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name_ko FROM institutions ORDER BY name_ko")
            rows = [{'id': r[0], 'name_ko': r[1]} for r in cur.fetchall()]
        return jsonify({'ok': True, 'institutions': rows})
    finally:
        release_db_conn(conn)


@app.route('/admin/api/reports/kpi', methods=['GET'])
@super_admin_required
def api_reports_kpi():
    inst_id      = request.args.get('inst_id', '').strip()
    subject_code = request.args.get('subject_code', 'HST').strip()
    period       = request.args.get('period', 'term')

    if not inst_id:
        return jsonify({'ok': False, 'error': '기관을 선택하세요'}), 400

    conn = get_db_conn()
    try:
        start_dt, end_dt = _reports_date_range(period, inst_id, subject_code, conn)

        # 날짜 필터 SQL 조건
        date_where = ""
        date_params: list = []
        if start_dt and end_dt:
            date_where = "AND al.accessed_at BETWEEN %s AND %s + INTERVAL '1 day'"
            date_params = [start_dt, end_dt]

        with conn.cursor() as cur:
            # 활성 사용자 수 + 최대 좌석
            cur.execute("""
                SELECT COUNT(u.id)
                FROM users u
                WHERE u.institution_id = %s
                  AND COALESCE(u.status, 'active') = 'active'
                  AND COALESCE(u.is_special, FALSE) = FALSE
            """, (inst_id,))
            active_users = cur.fetchone()[0] or 0

            cur.execute("""
                SELECT COALESCE(SUM(max_seats), 0)
                FROM subscriptions
                WHERE institution_id = %s AND subject_code = %s AND status = 'active'
            """, (inst_id, subject_code))
            max_seats = cur.fetchone()[0] or 0

            # 총 열람 수
            cur.execute(f"""
                SELECT COUNT(al.id)
                FROM access_logs al
                JOIN users u ON al.user_id = u.id
                WHERE u.institution_id = %s {date_where}
            """, [inst_id] + date_params)
            total_views = cur.fetchone()[0] or 0

            # AI 튜터 질문 수 (chat_logs는 created_at 컬럼, access_logs와 별개)
            ai_questions = 0
            chat_date_where = ""
            if start_dt and end_dt:
                chat_date_where = "AND cl.created_at BETWEEN %s AND %s + INTERVAL '1 day'"
            try:
                cur.execute(f"""
                    SELECT COUNT(cl.id)
                    FROM chat_logs cl
                    WHERE cl.institution_id = %s {chat_date_where}
                """, [inst_id] + date_params)
                ai_questions = cur.fetchone()[0] or 0
            except Exception:
                conn.rollback()

            # 마지막 활동
            cur.execute(f"""
                SELECT MAX(al.accessed_at)
                FROM access_logs al
                JOIN users u ON al.user_id = u.id
                WHERE u.institution_id = %s {date_where}
            """, [inst_id] + date_params)
            last_activity = cur.fetchone()[0]

        util_pct = round(active_users / max_seats * 100) if max_seats > 0 else 0
        per_user = round(ai_questions / active_users, 1) if active_users > 0 else 0

        return jsonify({
            'ok': True,
            'active_users': active_users,
            'max_seats':    max_seats,
            'util_pct':     util_pct,
            'total_views':  total_views,
            'ai_questions': ai_questions,
            'per_user':     per_user,
            'last_activity': last_activity.strftime('%Y-%m-%d %H:%M') if last_activity else None,
        })
    finally:
        release_db_conn(conn)


@app.route('/admin/api/reports/weekly', methods=['GET'])
@super_admin_required
def api_reports_weekly():
    inst_id      = request.args.get('inst_id', '').strip()
    subject_code = request.args.get('subject_code', 'HST').strip()
    period       = request.args.get('period', 'term')

    if not inst_id:
        return jsonify({'ok': False, 'error': '기관을 선택하세요'}), 400

    conn = get_db_conn()
    try:
        start_dt, end_dt = _reports_date_range(period, inst_id, subject_code, conn)

        date_where = ""
        date_params: list = []
        if start_dt and end_dt:
            date_where = "AND al.accessed_at BETWEEN %s AND %s + INTERVAL '1 day'"
            date_params = [start_dt, end_dt]

        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT
                    TO_CHAR(DATE_TRUNC('week', al.accessed_at), 'MM/DD') AS week_label,
                    COUNT(DISTINCT al.user_id) AS logins
                FROM access_logs al
                JOIN users u ON al.user_id = u.id
                WHERE u.institution_id = %s {date_where}
                GROUP BY DATE_TRUNC('week', al.accessed_at)
                ORDER BY DATE_TRUNC('week', al.accessed_at)
                LIMIT 12
            """, [inst_id] + date_params)
            rows = cur.fetchall()

        weeks = [{'label': r[0], 'count': r[1]} for r in rows]
        max_val = max((w['count'] for w in weeks), default=1)
        for w in weeks:
            w['pct'] = round(w['count'] / max_val * 100) if max_val else 0

        return jsonify({'ok': True, 'weeks': weeks})
    finally:
        release_db_conn(conn)


@app.route('/admin/api/reports/top-slides', methods=['GET'])
@super_admin_required
def api_reports_top_slides():
    inst_id      = request.args.get('inst_id', '').strip()
    subject_code = request.args.get('subject_code', 'HST').strip()
    period       = request.args.get('period', 'term')

    if not inst_id:
        return jsonify({'ok': False, 'error': '기관을 선택하세요'}), 400

    conn = get_db_conn()
    try:
        start_dt, end_dt = _reports_date_range(period, inst_id, subject_code, conn)

        date_where = ""
        date_params: list = []
        if start_dt and end_dt:
            date_where = "AND al.accessed_at BETWEEN %s AND %s + INTERVAL '1 day'"
            date_params = [start_dt, end_dt]

        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT s.title_ko, s.stain, COUNT(al.id) AS views
                FROM access_logs al
                JOIN users u ON al.user_id = u.id
                JOIN slides s ON al.slide_id = s.id
                WHERE u.institution_id = %s
                  AND s.subject_code = %s {date_where}
                GROUP BY s.id, s.title_ko, s.stain
                ORDER BY views DESC
                LIMIT 5
            """, [inst_id, subject_code] + date_params)
            rows = cur.fetchall()

        slides = [{'title': r[0], 'stain': r[1], 'views': r[2]} for r in rows]
        max_val = slides[0]['views'] if slides else 1
        for sl in slides:
            sl['pct'] = round(sl['views'] / max_val * 100) if max_val else 0

        return jsonify({'ok': True, 'slides': slides})
    finally:
        release_db_conn(conn)


@app.route('/admin/api/reports/export/excel', methods=['GET'])
@super_admin_required
def api_reports_export_excel():
    inst_id      = request.args.get('inst_id', '').strip()
    subject_code = request.args.get('subject_code', 'HST').strip()
    period       = request.args.get('period', 'term')

    if not inst_id:
        return jsonify({'ok': False, 'error': '기관을 선택하세요'}), 400

    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
    except ImportError:
        return jsonify({'ok': False, 'error': 'openpyxl 미설치'}), 500

    conn = get_db_conn()
    try:
        start_dt, end_dt = _reports_date_range(period, inst_id, subject_code, conn)

        date_where = ""
        date_params: list = []
        if start_dt and end_dt:
            date_where = "AND al.accessed_at BETWEEN %s AND %s + INTERVAL '1 day'"
            date_params = [start_dt, end_dt]

        with conn.cursor() as cur:
            # 기관명
            cur.execute("SELECT name_ko FROM institutions WHERE id = %s", (inst_id,))
            row = cur.fetchone()
            inst_name = row[0] if row else inst_id

            # KPI
            cur.execute("""
                SELECT COUNT(u.id) FROM users u
                WHERE u.institution_id = %s
                  AND COALESCE(u.status, 'active') = 'active'
                  AND COALESCE(u.is_special, FALSE) = FALSE
            """, (inst_id,))
            active_users = cur.fetchone()[0] or 0

            cur.execute("""
                SELECT COALESCE(SUM(max_seats), 0) FROM subscriptions
                WHERE institution_id = %s AND subject_code = %s AND status = 'active'
            """, (inst_id, subject_code))
            max_seats = cur.fetchone()[0] or 0

            cur.execute(f"""
                SELECT COUNT(al.id) FROM access_logs al
                JOIN users u ON al.user_id = u.id
                WHERE u.institution_id = %s {date_where}
            """, [inst_id] + date_params)
            total_views = cur.fetchone()[0] or 0

            # 주간 추세
            cur.execute(f"""
                SELECT TO_CHAR(DATE_TRUNC('week', al.accessed_at), 'YYYY-MM-DD') AS wk,
                       COUNT(DISTINCT al.user_id)
                FROM access_logs al
                JOIN users u ON al.user_id = u.id
                WHERE u.institution_id = %s {date_where}
                GROUP BY DATE_TRUNC('week', al.accessed_at)
                ORDER BY 1 LIMIT 12
            """, [inst_id] + date_params)
            weekly_rows = cur.fetchall()

            # 많이 본 슬라이드
            cur.execute(f"""
                SELECT s.id, s.title_ko, s.stain, COUNT(al.id) AS views
                FROM access_logs al
                JOIN users u ON al.user_id = u.id
                JOIN slides s ON al.slide_id = s.id
                WHERE u.institution_id = %s
                  AND s.subject_code = %s {date_where}
                GROUP BY s.id, s.title_ko, s.stain
                ORDER BY views DESC LIMIT 10
            """, [inst_id, subject_code] + date_params)
            top_slides = cur.fetchall()
    finally:
        release_db_conn(conn)

    # Excel 생성
    wb = openpyxl.Workbook()
    HDR = Font(bold=True, color='FFFFFF')
    HDR_FILL = PatternFill('solid', fgColor='0F1F3D')
    center = Alignment(horizontal='center')

    # 시트 1: 요약
    ws = wb.active
    ws.title = '요약'
    ws.append([f'{inst_name} 이용 리포트'])
    ws['A1'].font = Font(bold=True, size=13)
    period_label = {'term': '이번 학기', '30d': '최근 30일', 'all': '전체 기간'}.get(period, period)
    ws.append([f'기간: {period_label}  /  과목: {subject_code}'])
    ws.append([])
    ws.append(['지표', '수치'])
    for cell in ws[4]:
        cell.font = HDR; cell.fill = HDR_FILL; cell.alignment = center
    ws.append(['활성 사용자', active_users])
    ws.append(['최대 좌석', max_seats])
    ws.append(['좌석 소진율 (%)', round(active_users / max_seats * 100) if max_seats else 0])
    ws.append(['총 슬라이드 열람', total_views])
    ws.column_dimensions['A'].width = 22
    ws.column_dimensions['B'].width = 14

    # 시트 2: 주간 추세
    ws2 = wb.create_sheet('주간 추세')
    ws2.append(['주차 시작일', '순방문자(주)'])
    for cell in ws2[1]:
        cell.font = HDR; cell.fill = HDR_FILL
    for wk, cnt in weekly_rows:
        ws2.append([wk, cnt])
    ws2.column_dimensions['A'].width = 16
    ws2.column_dimensions['B'].width = 14

    # 시트 3: 많이 본 슬라이드
    ws3 = wb.create_sheet('많이 본 슬라이드')
    ws3.append(['슬라이드 ID', '제목', '염색', '열람 수'])
    for cell in ws3[1]:
        cell.font = HDR; cell.fill = HDR_FILL
    for slide_id, title, stain, views in top_slides:
        ws3.append([slide_id, title, stain, views])
    for col in ['A', 'B', 'C', 'D']:
        ws3.column_dimensions[col].width = 18

    import io
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    from flask import send_file as _sf
    fname = f'SlideAtlas_report_{inst_id}_{period}.xlsx'
    return _sf(buf, as_attachment=True, download_name=fname,
               mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


# ── 특별 계정 (S5-6) ─────────────────────────────────────

@app.route('/admin/special')
@super_admin_required
def admin_special_page():
    return render_template('admin/special.html', active_page='special')


@app.route('/admin/api/special/accounts', methods=['GET'])
@super_admin_required
def api_special_accounts_list():
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    u.id, u.email, u.institution_id, i.name_ko AS inst_name,
                    u.special_purpose, u.special_expires_at, u.special_review_at,
                    u.special_created_by, a.name AS created_by_name,
                    COALESCE(u.status, 'active') AS status,
                    u.created_at
                FROM users u
                LEFT JOIN institutions i ON u.institution_id = i.id
                LEFT JOIN admin_users  a ON u.special_created_by = a.id
                WHERE COALESCE(u.is_special, FALSE) = TRUE
                ORDER BY u.created_at DESC
            """)
            rows = cur.fetchall()

        from datetime import date, timedelta
        today = date.today()
        accounts = []
        for r in rows:
            expires = r[5]
            review  = r[6]
            dday    = None
            dday_type = None  # 'warn'|'danger'|'ok'
            if expires:
                delta = (expires - today).days
                dday = delta
                dday_type = 'danger' if delta < 0 else ('warn' if delta <= 30 else 'ok')

            accounts.append({
                'id':              r[0],
                'email':           r[1],
                'institution_id':  r[2],
                'inst_name':       r[3],
                'purpose':         r[4],
                'expires_at':      expires.isoformat() if expires else None,
                'review_at':       review.isoformat()  if review  else None,
                'created_by_name': r[8],
                'status':          r[9],
                'dday':            dday,
                'dday_type':       dday_type,
                'no_expiry':       expires is None,
            })

        return jsonify({'ok': True, 'accounts': accounts})
    finally:
        release_db_conn(conn)


@app.route('/admin/api/special/accounts', methods=['POST'])
@super_admin_required
@admin_csrf_required
def api_special_accounts_create():
    data = request.get_json(silent=True) or {}
    email       = (data.get('email') or '').strip().lower()
    purpose     = (data.get('purpose') or '').strip()
    expires_at  = data.get('expires_at') or None
    review_at   = data.get('review_at')  or None
    inst_id     = (data.get('institution_id') or '').strip() or None

    if not email or not purpose:
        return jsonify({'ok': False, 'error': '이메일과 용도는 필수입니다'}), 400

    # 이메일 기본 검증
    if '@' not in email or len(email) > 200:
        return jsonify({'ok': False, 'error': '이메일 형식이 올바르지 않습니다'}), 400

    conn = get_db_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                # 이미 존재하면 is_special 업데이트
                cur.execute("SELECT id FROM users WHERE email = %s", (email,))
                existing = cur.fetchone()
                if existing:
                    cur.execute("""
                        UPDATE users SET
                            is_special         = TRUE,
                            special_purpose    = %s,
                            special_expires_at = %s,
                            special_review_at  = %s,
                            special_created_by = %s,
                            institution_id     = COALESCE(%s, institution_id),
                            status             = 'active'
                        WHERE id = %s
                    """, (purpose, expires_at, review_at,
                          g.admin_user_id, inst_id, existing[0]))
                    user_id = existing[0]
                else:
                    from werkzeug.security import generate_password_hash as _gph
                    import secrets as _sec
                    temp_pw = _gph(_sec.token_hex(16))
                    cur.execute("""
                        INSERT INTO users
                            (email, password_hash, institution_id, is_special,
                             special_purpose, special_expires_at, special_review_at,
                             special_created_by, status)
                        VALUES (%s, %s, %s, TRUE, %s, %s, %s, %s, 'active')
                        RETURNING id
                    """, (email, temp_pw, inst_id, purpose,
                          expires_at, review_at, g.admin_user_id))
                    user_id = cur.fetchone()[0]

        return jsonify({'ok': True, 'user_id': user_id})
    finally:
        release_db_conn(conn)


@app.route('/admin/api/special/accounts/<int:user_id>/deactivate', methods=['POST'])
@super_admin_required
@admin_csrf_required
def api_special_accounts_deactivate(user_id):
    conn = get_db_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE users SET status = 'suspended'
                    WHERE id = %s AND COALESCE(is_special, FALSE) = TRUE
                    RETURNING id
                """, (user_id,))
                if not cur.fetchone():
                    return jsonify({'ok': False, 'error': '계정을 찾을 수 없습니다'}), 404
        return jsonify({'ok': True})
    finally:
        release_db_conn(conn)


@app.route('/admin/api/special/accounts/<int:user_id>/activate', methods=['POST'])
@super_admin_required
@admin_csrf_required
def api_special_accounts_activate(user_id):
    conn = get_db_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE users SET status = 'active'
                    WHERE id = %s AND COALESCE(is_special, FALSE) = TRUE
                    RETURNING id
                """, (user_id,))
                if not cur.fetchone():
                    return jsonify({'ok': False, 'error': '계정을 찾을 수 없습니다'}), 404
        return jsonify({'ok': True})
    finally:
        release_db_conn(conn)


# ── 공지 관리 (S5-7) ─────────────────────────────────────

@app.route('/admin/notices')
@admin_required
def admin_notices_page():
    return render_template('admin/notices.html', active_page='notice')


@app.route('/admin/api/notices/list', methods=['GET'])
@admin_required
def api_notices_list():
    view = request.args.get('view', 'active')   # 'active' | 'archive'
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            if view == 'archive':
                cur.execute("""
                    SELECT id, title, body, is_published, display_order,
                           created_by, updated_by, archived_at, updated_at,
                           ac.name AS created_name, ac.role AS created_role,
                           au.name AS updated_name, au.role AS updated_role
                    FROM announcements a
                    LEFT JOIN admin_users ac ON a.created_by = ac.id
                    LEFT JOIN admin_users au ON a.updated_by = au.id
                    WHERE is_archived = TRUE
                    ORDER BY archived_at DESC
                """)
            else:
                cur.execute("""
                    SELECT id, title, body, is_published, display_order,
                           created_by, updated_by, archived_at, updated_at,
                           ac.name AS created_name, ac.role AS created_role,
                           au.name AS updated_name, au.role AS updated_role
                    FROM announcements a
                    LEFT JOIN admin_users ac ON a.created_by = ac.id
                    LEFT JOIN admin_users au ON a.updated_by = au.id
                    WHERE is_archived = FALSE
                    ORDER BY is_published DESC, display_order ASC, updated_at DESC
                """)
            rows = cur.fetchall()

            # 게시 중 개수
            cur.execute("""
                SELECT COUNT(*) FROM announcements
                WHERE is_published = TRUE AND is_archived = FALSE
            """)
            published_count = cur.fetchone()[0] or 0

            cur.execute("""
                SELECT COUNT(*) FROM announcements WHERE is_archived = TRUE
            """)
            archive_count = cur.fetchone()[0] or 0

        def _row(r):
            editor = r[11] or r[9]  # updated_name 우선, 없으면 created_name
            editor_role = r[12] or r[10]
            return {
                'id':             r[0],
                'title':          r[1],
                'body':           r[2],
                'is_published':   r[3],
                'display_order':  r[4],
                'archived_at':    r[7].strftime('%m-%d') if r[7] else None,
                'updated_at':     r[8].strftime('%m-%d') if r[8] else None,
                'editor':         editor or '',
                'editor_role':    'super' if editor_role == 'super_admin' else 'staff',
            }

        return jsonify({
            'ok': True,
            'items': [_row(r) for r in rows],
            'published_count': published_count,
            'archive_count':   archive_count,
        })
    finally:
        release_db_conn(conn)


@app.route('/admin/api/notices', methods=['POST'])
@admin_required
@admin_csrf_required
def api_notices_create():
    data = request.get_json(silent=True) or {}
    title   = (data.get('title') or '').strip()
    body    = (data.get('body')  or '').strip()
    publish = bool(data.get('is_published', False))

    if not title:
        return jsonify({'ok': False, 'error': '제목을 입력하세요'}), 400

    conn = get_db_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                # 게시 순서: 기존 최대 display_order + 1
                if publish:
                    cur.execute("""
                        SELECT COALESCE(MAX(display_order), 0)
                        FROM announcements WHERE is_published = TRUE AND is_archived = FALSE
                    """)
                    next_order = (cur.fetchone()[0] or 0) + 1
                else:
                    next_order = 0

                cur.execute("""
                    INSERT INTO announcements
                        (title, body, is_published, display_order, created_by, updated_by)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (title, body, publish, next_order,
                      g.admin_user_id, g.admin_user_id))
                new_id = cur.fetchone()[0]

        return jsonify({'ok': True, 'id': new_id})
    finally:
        release_db_conn(conn)


@app.route('/admin/api/notices/<int:notice_id>', methods=['PUT'])
@admin_required
@admin_csrf_required
def api_notices_update(notice_id):
    data = request.get_json(silent=True) or {}
    title         = (data.get('title') or '').strip()
    body          = data.get('body', '')
    is_published  = data.get('is_published')   # None = don't change
    display_order = data.get('display_order')  # None = don't change

    if not title:
        return jsonify({'ok': False, 'error': '제목을 입력하세요'}), 400

    conn = get_db_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM announcements WHERE id = %s AND is_archived = FALSE", (notice_id,))
                if not cur.fetchone():
                    return jsonify({'ok': False, 'error': '공지를 찾을 수 없습니다'}), 404

                set_clauses = ["title = %s", "body = %s", "updated_by = %s", "updated_at = NOW()"]
                params: list = [title, body or '', g.admin_user_id]

                if is_published is not None:
                    set_clauses.append("is_published = %s")
                    params.append(bool(is_published))
                if display_order is not None:
                    set_clauses.append("display_order = %s")
                    params.append(int(display_order))

                params.append(notice_id)
                cur.execute(
                    f"UPDATE announcements SET {', '.join(set_clauses)} WHERE id = %s",
                    params,
                )

        return jsonify({'ok': True})
    finally:
        release_db_conn(conn)


@app.route('/admin/api/notices/<int:notice_id>/toggle', methods=['POST'])
@admin_required
@admin_csrf_required
def api_notices_toggle(notice_id):
    conn = get_db_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT is_published, display_order
                    FROM announcements WHERE id = %s AND is_archived = FALSE
                """, (notice_id,))
                row = cur.fetchone()
                if not row:
                    return jsonify({'ok': False, 'error': '공지를 찾을 수 없습니다'}), 404

                currently_published = row[0]
                new_published = not currently_published

                if new_published:
                    cur.execute("""
                        SELECT COALESCE(MAX(display_order), 0)
                        FROM announcements WHERE is_published = TRUE AND is_archived = FALSE AND id != %s
                    """, (notice_id,))
                    new_order = (cur.fetchone()[0] or 0) + 1
                else:
                    new_order = 0

                cur.execute("""
                    UPDATE announcements
                    SET is_published = %s, display_order = %s,
                        updated_by = %s, updated_at = NOW()
                    WHERE id = %s
                """, (new_published, new_order, g.admin_user_id, notice_id))

        return jsonify({'ok': True, 'is_published': new_published})
    finally:
        release_db_conn(conn)


@app.route('/admin/api/notices/<int:notice_id>/archive', methods=['POST'])
@admin_required
@admin_csrf_required
def api_notices_archive(notice_id):
    conn = get_db_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE announcements
                    SET is_archived = TRUE, is_published = FALSE, display_order = 0,
                        archived_at = NOW(), updated_by = %s, updated_at = NOW()
                    WHERE id = %s AND is_archived = FALSE
                    RETURNING id
                """, (g.admin_user_id, notice_id))
                if not cur.fetchone():
                    return jsonify({'ok': False, 'error': '공지를 찾을 수 없습니다'}), 404

        return jsonify({'ok': True})
    finally:
        release_db_conn(conn)


@app.route('/admin/api/notices/<int:notice_id>/restore', methods=['POST'])
@admin_required
@admin_csrf_required
def api_notices_restore(notice_id):
    conn = get_db_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE announcements
                    SET is_archived = FALSE, is_published = FALSE, display_order = 0,
                        archived_at = NULL, updated_by = %s, updated_at = NOW()
                    WHERE id = %s AND is_archived = TRUE
                    RETURNING id
                """, (g.admin_user_id, notice_id))
                if not cur.fetchone():
                    return jsonify({'ok': False, 'error': '공지를 찾을 수 없습니다'}), 404

        return jsonify({'ok': True})
    finally:
        release_db_conn(conn)


@app.route('/admin/api/notices/<int:notice_id>', methods=['DELETE'])
@admin_required
@admin_csrf_required
def api_notices_hard_delete(notice_id):
    conn = get_db_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                # 보관함에 있는 항목만 완전 삭제 가능
                cur.execute("""
                    DELETE FROM announcements
                    WHERE id = %s AND is_archived = TRUE
                    RETURNING id
                """, (notice_id,))
                if not cur.fetchone():
                    return jsonify({'ok': False, 'error': '보관함에 있는 공지만 완전 삭제할 수 있습니다'}), 404

        return jsonify({'ok': True})
    finally:
        release_db_conn(conn)


# ── 1:1 문의 (S5-8) ──────────────────────────────────────

def _send_inquiry_reply_email(to_email: str, inquiry_title: str, reply_body: str) -> bool:
    """답변 이메일 발송 (현재: Gmail SMTP 임시 구현).

    # TODO: SES 도메인 인증(slide-atlas.net) 완료 후 boto3 SES로 교체.
    #   교체 시 이 함수만 수정하면 됨 — 호출부는 변경 없음.
    #   SES 발신 주소: noreply@slide-atlas.net (인증 후 확정).
    #   자격증명은 환경변수 AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_REGION.
    #   (하드코딩 금지 — .env 또는 Render 환경변수에만 설정)
    """
    try:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText as _MIMEText
        # GMAIL_USER / GMAIL_APP_PW 는 .env 또는 Render 환경변수에서만 읽음 (하드코딩 금지)
        sender = os.environ.get('GMAIL_USER', '')
        if not sender:
            return False
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'[SlideAtlas] "{inquiry_title}" 문의 답변'
        msg['From']    = sender
        msg['To']      = to_email
        html = f"""<p>안녕하세요, SlideAtlas입니다.</p>
<p><b>'{inquiry_title}'</b> 문의에 대한 답변입니다.</p>
<hr style="border:none;border-top:1px solid #eee;margin:16px 0">
<p style="white-space:pre-wrap">{reply_body}</p>
<p style="color:#888;font-size:12px;margin-top:24px">SlideAtlas | atlaslab.co.kr</p>"""
        msg.attach(_MIMEText(html, 'html'))
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as s:
            s.login(sender, os.environ['GMAIL_APP_PW'])
            s.send_message(msg)
        return True
    except Exception as e:
        print(f'[S5-8] 답변 이메일 발송 실패: {e}')
        return False


@app.route('/admin/inquiries')
@admin_required
def admin_inquiries_page():
    return render_template('admin/inquiries.html', active_page='inquiry')


@app.route('/admin/api/inquiries/list', methods=['GET'])
@admin_required
def api_inquiries_list():
    status_filter = request.args.get('status', 'all')   # 'all'|'open'|'answered'
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            where = ""
            params: list = []
            if status_filter in ('open', 'answered'):
                where = "WHERE i.status = %s"
                params = [status_filter]

            cur.execute(f"""
                SELECT i.id, i.title, i.status,
                       i.user_email, i.user_name,
                       i.institution_id, inst.name_ko AS inst_name,
                       i.created_at
                FROM inquiries i
                LEFT JOIN institutions inst ON i.institution_id = inst.id
                {where}
                ORDER BY
                    CASE WHEN i.status = 'open' THEN 0 ELSE 1 END,
                    i.created_at DESC
            """, params)
            rows = cur.fetchall()

            # 미답변 수
            cur.execute("SELECT COUNT(*) FROM inquiries WHERE status = 'open'")
            open_count = cur.fetchone()[0] or 0

        items = [{
            'id':         r[0],
            'title':      r[1] or '(제목 없음)',
            'status':     r[2],
            'email':      r[3] or '',
            'name':       r[4] or '',
            'inst_id':    r[5] or '',
            'inst_name':  r[6] or '',
            'created_at': r[7].strftime('%m-%d') if r[7] else '',
        } for r in rows]

        return jsonify({'ok': True, 'items': items, 'open_count': open_count})
    finally:
        release_db_conn(conn)


@app.route('/admin/api/inquiries/<int:inq_id>', methods=['GET'])
@admin_required
def api_inquiries_detail(inq_id):
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT i.id, i.title, i.body, i.status,
                       i.user_email, i.user_name,
                       i.institution_id, inst.name_ko AS inst_name,
                       i.created_at
                FROM inquiries i
                LEFT JOIN institutions inst ON i.institution_id = inst.id
                WHERE i.id = %s
            """, (inq_id,))
            row = cur.fetchone()
            if not row:
                return jsonify({'ok': False, 'error': '문의를 찾을 수 없습니다'}), 404

            cur.execute("""
                SELECT r.id, r.body, r.sent_via_ses, r.created_at,
                       a.name, a.role
                FROM inquiry_replies r
                LEFT JOIN admin_users a ON r.created_by = a.id
                WHERE r.inquiry_id = %s
                ORDER BY r.created_at ASC
            """, (inq_id,))
            reply_rows = cur.fetchall()

        inq = {
            'id':        row[0],
            'title':     row[1] or '(제목 없음)',
            'body':      row[2] or '',
            'status':    row[3],
            'email':     row[4] or '',
            'name':      row[5] or '',
            'inst_id':   row[6] or '',
            'inst_name': row[7] or '',
            'created_at': row[8].strftime('%Y-%m-%d %H:%M') if row[8] else '',
        }
        replies = [{
            'id':           r[0],
            'body':         r[1],
            'sent_via_ses': r[2],
            'created_at':   r[3].strftime('%Y-%m-%d %H:%M') if r[3] else '',
            'author':       r[4] or '',
            'author_role':  'super' if r[5] == 'super_admin' else 'staff',
        } for r in reply_rows]

        return jsonify({'ok': True, 'inquiry': inq, 'replies': replies})
    finally:
        release_db_conn(conn)


@app.route('/admin/api/inquiries/<int:inq_id>/reply', methods=['POST'])
@admin_required
@admin_csrf_required
def api_inquiries_reply(inq_id):
    data = request.get_json(silent=True) or {}
    body = (data.get('body') or '').strip()
    if not body:
        return jsonify({'ok': False, 'error': '답변 내용을 입력하세요'}), 400

    conn = get_db_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT title, user_email FROM inquiries WHERE id = %s
                """, (inq_id,))
                row = cur.fetchone()
                if not row:
                    return jsonify({'ok': False, 'error': '문의를 찾을 수 없습니다'}), 404

                title, to_email = row

                # 이메일 발송 (실패해도 DB 기록은 정상 진행)
                sent = _send_inquiry_reply_email(to_email or '', title or '', body)

                cur.execute("""
                    INSERT INTO inquiry_replies
                        (inquiry_id, body, created_by, sent_via_ses)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                """, (inq_id, body, g.admin_user_id, sent))
                reply_id = cur.fetchone()[0]

                # 상태 → answered
                cur.execute("""
                    UPDATE inquiries SET status = 'answered' WHERE id = %s
                """, (inq_id,))

        return jsonify({'ok': True, 'reply_id': reply_id, 'sent_via_ses': sent})
    finally:
        release_db_conn(conn)


# ── 고객센터 ──────────────────────────────────────────────

@app.route('/faq')
def faq():
    is_logged = bool(request.cookies.get('access_token'))
    return render_template('faq.html', is_logged=is_logged)


@app.route('/manual')
def manual():
    is_logged = bool(request.cookies.get('access_token'))
    return render_template('manual.html', is_logged=is_logged)


@app.route('/support', methods=['GET', 'POST'])
def support():
    is_logged = bool(request.cookies.get('access_token'))

    if request.method == 'GET':
        return render_template('support.html', is_logged=is_logged,
                               success=False, error=None, form={})

    # POST: 문의 접수
    name    = request.form.get('name', '').strip()
    email   = request.form.get('email', '').strip()
    phone   = request.form.get('phone', '').strip()
    subject = request.form.get('subject', '').strip()
    content = request.form.get('content', '').strip()
    privacy = request.form.get('privacy_agreed', '')

    form_data = {'name': name, 'email': email, 'phone': phone,
                 'subject': subject, 'content': content,
                 'privacy_agreed': bool(privacy)}

    # 서버측 필수값 검증
    if not email or not subject or not content or not privacy:
        return render_template('support.html', is_logged=is_logged,
                               success=False,
                               error='필수 항목을 모두 입력해 주세요.',
                               form=form_data)

    # [H2] 로그인 사용자면 user_id·institution_id 자동 캡처(§15-10), 비로그인이면 NULL.
    # access_token 쿠키를 best-effort 디코드(인증 게이트 아님 — 익명 접수도 허용).
    user_id = None
    inst_id = None
    if is_logged:
        try:
            from auth.decorators import decode_token, COOKIE_NAME
            _payload = decode_token(request.cookies.get(COOKIE_NAME, ''))
            user_id = _payload.get('sub')
            inst_id = _payload.get('institution_id')
        except Exception:
            user_id = None
            inst_id = None

    # [H2] inquiries 실제 스키마 컬럼에 매핑: subject→title, content→body,
    #      email→user_email, name→user_name, status='open'.
    #      phone·privacy_agreed는 스키마에 컬럼이 없어 저장하지 않는다(아래 CEO 승인 항목 참조).
    #      ★실패 은폐(except: pass) 제거 — INSERT 실패 시 사용자에게 실패를 알리고 서버 로그 기록.
    inserted = False
    try:
        conn = get_db_conn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO inquiries
                            (user_id, institution_id, title, body,
                             user_email, user_name, status)
                        VALUES (%s, %s, %s, %s, %s, %s, 'open')
                    """, (user_id, inst_id, subject, content, email, name or None))
            inserted = True
        finally:
            release_db_conn(conn)
    except Exception:
        app.logger.exception("1:1 문의 INSERT 실패 (email=%s)", email)
        inserted = False

    if not inserted:
        return render_template('support.html', is_logged=is_logged,
                               success=False,
                               error='문의 접수에 실패했습니다. 잠시 후 다시 시도해 주세요.',
                               form=form_data)

    return render_template('support.html', is_logged=is_logged,
                           success=True, error=None, form={})


if __name__ == '__main__':
    print(f"\n✅ SlideAtlas 서버 시작!")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, threaded=True)
