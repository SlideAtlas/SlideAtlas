import os
import sys
import threading
import json
from functools import wraps

from flask import Flask, send_file, Response, request, jsonify, session, redirect, url_for
from PIL import Image
import io

app = Flask(__name__)
app.secret_key = os.environ.get('ADMIN_SECRET_KEY', 'slideatlas-dev-secret-2026')

# ── JSON 데이터 경로 ──
SLIDES_JSON = os.path.join(os.path.dirname(__file__), 'slides.json')
INSTITUTIONS_JSON = os.path.join(os.path.dirname(__file__), 'institutions.json')

def load_slides():
    if os.path.exists(SLIDES_JSON):
        with open(SLIDES_JSON, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"slides": []}

def save_slides(data):
    with open(SLIDES_JSON, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_institutions():
    if os.path.exists(INSTITUTIONS_JSON):
        with open(INSTITUTIONS_JSON, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"institutions": [], "subjects": []}

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect('/admin/login')
        return f(*args, **kwargs)
    return decorated

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

            # EC2 타일서버를 쓰는 SVS는 Render에서 로드하지 않음
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

# ── EC2 타일서버 프록시 (Mixed Content 해결) ──
@app.route('/ec2tile/<path:subpath>')
def ec2_proxy(subpath):
    import urllib.request
    url = f"{EC2_TILESERVER}/{subpath}"
    try:
        with urllib.request.urlopen(url, timeout=120) as resp:
            data = resp.read()
            ct = resp.headers.get('Content-Type', 'image/jpeg')
            return Response(data, mimetype=ct)
    except Exception as e:
        print(f"EC2 proxy error {url}: {e}")
        return Response(str(e), status=502)

# ── 랜딩페이지 ──
@app.route('/')
def landing():
    return '''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SlideAtlas — 디지털 병리 슬라이드 교육 플랫폼</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
@import url('https://cdn.jsdelivr.net/gh/sunn-us/SUIT/fonts/variable/woff2/SUIT-Variable.css');
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: "SUIT Variable", "SUIT", sans-serif; background: #F7F4EF; color: #0F1F3D; min-height: 100vh; overflow-x: hidden; }
nav { background: #0F1F3D; padding: 0 40px; height: 58px; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 100; }
.logo { display: flex; flex-direction: column; line-height: 1; gap: 1px; }
.logo-slide { font-size: 8px; font-weight: 500; letter-spacing: 0.22em; color: #2A9D8F; text-transform: uppercase; font-family: "DM Mono", monospace; }
.logo-atlas { font-size: 20px; font-weight: 800; color: #fff; letter-spacing: 0.04em; }
.nav-right { display: flex; gap: 10px; align-items: center; }
.nav-badge { font-size: 12px; color: #2A9D8F; border: 1px solid rgba(42,157,143,0.4); padding: 4px 12px; border-radius: 20px; letter-spacing: 0.03em; font-weight: 500; }
.btn-nav { background: #2A9D8F; color: #fff; border: none; padding: 7px 18px; border-radius: 6px; font-size: 13px; font-family: "SUIT Variable", sans-serif; font-weight: 600; cursor: pointer; text-decoration: none; display: inline-block; }
.hero { display: grid; grid-template-columns: 1fr 1fr; min-height: 480px; }
.hero-left { background: #0F1F3D; padding: 64px 48px 64px 52px; display: flex; flex-direction: column; justify-content: center; }
.hero-tag { display: inline-flex; align-items: center; gap: 7px; margin-bottom: 28px; }
.hero-dot { width: 7px; height: 7px; border-radius: 50%; background: #2A9D8F; animation: pulse 2s infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
.hero-tag-text { font-size: 12px; letter-spacing: 0.12em; color: rgba(255,255,255,0.9); text-transform: uppercase; font-family: "DM Mono", monospace; }
.hero-title { font-weight: 800; font-size: 46px; line-height: 1.15; color: #fff; margin-bottom: 18px; letter-spacing: -0.03em; word-break: keep-all; }
.hero-title .accent { color: #2A9D8F; }
.hero-desc { font-size: 15px; line-height: 1.7; color: rgba(255,255,255,0.78); margin-bottom: 36px; max-width: 380px; font-weight: 400; word-break: keep-all; }
.hero-cta { display: flex; gap: 12px; align-items: center; }
.btn-primary { background: #2A9D8F; color: #fff; border: none; padding: 13px 26px; border-radius: 7px; font-size: 14px; font-family: "SUIT Variable", sans-serif; font-weight: 600; cursor: pointer; letter-spacing: -0.01em; text-decoration: none; display: inline-block; }
.btn-primary:hover { background: #238b7f; }
.btn-secondary { background: transparent; color: rgba(255,255,255,0.65); border: 1px solid rgba(255,255,255,0.2); padding: 13px 24px; border-radius: 7px; font-size: 14px; font-family: "SUIT Variable", sans-serif; font-weight: 400; cursor: pointer; }
.hero-stats { display: flex; gap: 36px; margin-top: 48px; padding-top: 36px; border-top: 1px solid rgba(255,255,255,0.08); }
.stat-num { font-weight: 700; font-size: 28px; color: #fff; line-height: 1; letter-spacing: -0.02em; }
.stat-label { font-size: 12px; color: rgba(255,255,255,0.6); margin-top: 5px; font-weight: 400; }
.hero-right { background: #111c32; display: flex; flex-direction: column; }
.slide-viewer-mock { flex: 1; position: relative; background: radial-gradient(ellipse at 50% 50%, #1e2f4a 0%, #0d1626 100%); min-height: 320px; overflow: hidden; }
.tissue-bg { position: absolute; inset: 0; background: radial-gradient(ellipse 140px 100px at 38% 42%, rgba(220,150,170,0.55) 0%, transparent 70%), radial-gradient(ellipse 80px 80px at 62% 38%, rgba(200,120,145,0.6) 0%, transparent 65%), radial-gradient(ellipse 60px 70px at 45% 65%, rgba(210,135,160,0.5) 0%, transparent 60%), radial-gradient(ellipse 100px 85px at 72% 60%, rgba(190,110,135,0.5) 0%, transparent 65%), radial-gradient(ellipse 120px 90px at 25% 70%, rgba(215,140,165,0.45) 0%, transparent 60%), linear-gradient(135deg, #f5e8ee 0%, #f0dce6 30%, #e8d0dc 60%, #f2e4ea 100%); opacity: 0.9; }
.viewer-overlay { position: absolute; inset: 0; display: flex; flex-direction: column; justify-content: space-between; padding: 14px; }
.viewer-top { display: flex; align-items: center; justify-content: space-between; }
.viewer-badge { background: rgba(42,157,143,0.9); color: #fff; font-size: 10px; padding: 4px 10px; border-radius: 4px; letter-spacing: 0.08em; font-weight: 600; font-family: "DM Mono", monospace; }
.viewer-info-badge { background: rgba(15,31,61,0.92); color: rgba(255,255,255,0.95); font-size: 12px; padding: 5px 12px; border-radius: 4px; font-family: "DM Mono", monospace; }
.viewer-bottom { display: flex; align-items: flex-end; justify-content: space-between; }
.viewer-meta { background: rgba(15,31,61,0.88); border-radius: 7px; padding: 10px 14px; }
.viewer-meta-title { font-size: 13px; font-weight: 700; color: #fff; margin-bottom: 4px; letter-spacing: -0.01em; }
.viewer-meta-sub { font-size: 12px; color: rgba(255,255,255,0.8); font-family: "DM Mono", monospace; }
.viewer-magnify { display: flex; gap: 4px; }
.mag-btn { background: rgba(15,31,61,0.85); color: rgba(255,255,255,0.65); border: none; width: 32px; height: 26px; border-radius: 4px; font-size: 11px; cursor: pointer; font-family: "DM Mono", monospace; }
.mag-btn.active { background: #2A9D8F; color: #fff; }
.hero-right-info { background: #0a1628; padding: 18px 24px; display: flex; align-items: center; justify-content: space-between; }
.hri-label { font-size: 12px; color: rgba(255,255,255,0.7); letter-spacing: 0.05em; font-family: "DM Mono", monospace; margin-bottom: 4px; }
.hri-value { font-size: 14px; color: #fff; font-weight: 600; }
.hri-divider { width: 1px; height: 32px; background: rgba(255,255,255,0.08); }
.mvp-notice { margin: 40px 52px 0; background: #fff; border: 1px solid #E5E0D8; border-left: 3px solid #E9C46A; border-radius: 8px; padding: 14px 20px; display: flex; align-items: center; gap: 12px; }
.mvp-dot { width: 7px; height: 7px; border-radius: 50%; background: #E9C46A; flex-shrink: 0; }
.mvp-text { font-size: 14px; color: #5a5550; line-height: 1.5; word-break: keep-all; }
.mvp-text strong { color: #0F1F3D; font-weight: 600; }
.section-discipline { padding: 64px 52px 80px; background: #F7F4EF; }
.section-label { font-size: 11px; letter-spacing: 0.14em; color: #2A9D8F; text-transform: uppercase; margin-bottom: 10px; font-family: "DM Mono", monospace; }
.section-title { font-weight: 800; font-size: 30px; color: #0F1F3D; margin-bottom: 36px; letter-spacing: -0.03em; }
.discipline-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; }
.discipline-card { background: #fff; border: 1px solid #E5E0D8; border-radius: 12px; padding: 28px; cursor: pointer; transition: all 0.2s; position: relative; overflow: hidden; text-decoration: none; display: block; color: inherit; }
.discipline-card:hover { border-color: #2A9D8F; transform: translateY(-2px); box-shadow: 0 8px 24px rgba(15,31,61,0.08); }
.discipline-card:hover .card-arrow { color: #2A9D8F; }
.card-icon { width: 40px; height: 40px; border-radius: 8px; background: #EBF6F5; display: flex; align-items: center; justify-content: center; margin-bottom: 16px; }
.card-icon svg { width: 20px; height: 20px; stroke: #2A9D8F; fill: none; stroke-width: 1.5; }
.card-count { font-size: 12px; color: #2A9D8F; font-weight: 600; letter-spacing: 0.04em; margin-bottom: 5px; font-family: "DM Mono", monospace; }
.card-title-ko { font-size: 20px; font-weight: 700; color: #0F1F3D; margin-bottom: 2px; letter-spacing: -0.02em; }
.card-title-en { font-size: 13px; color: #7a7470; margin-bottom: 14px; font-family: "DM Mono", monospace; }
.card-desc { font-size: 13px; color: #6B6560; line-height: 1.65; word-break: keep-all; }
.card-arrow { position: absolute; bottom: 24px; right: 24px; font-size: 16px; color: #C8C4BC; transition: color 0.2s; }
.card-core-badge { position: absolute; top: 16px; right: 16px; background: #EBF6F5; color: #0F6E56; font-size: 11px; font-weight: 600; padding: 3px 8px; border-radius: 20px; letter-spacing: 0.06em; font-family: "DM Mono", monospace; }
footer { background: #0F1F3D; padding: 28px 52px; display: flex; align-items: center; justify-content: space-between; }
.footer-logo { font-weight: 800; font-size: 16px; color: #fff; letter-spacing: -0.01em; }
.footer-copy { font-size: 13px; color: rgba(255,255,255,0.5); }
.footer-links { display: flex; gap: 24px; }
.footer-links a { font-size: 13px; color: rgba(255,255,255,0.55); text-decoration: none; }
.footer-links a:hover { color: rgba(255,255,255,0.9); }
</style>
</head>
<body>
<nav>
  <div style="display:flex;align-items:center;gap:14px;">
    <a href="/" style="display:flex;align-items:center;text-decoration:none;">
      <img src="/static/slideatlas_logo.png" alt="SlideAtlas" style="height:36px;width:auto;">
    </a>
    <span style="background:#E9C46A;color:#0F1F3D;font-size:11px;font-weight:800;padding:4px 10px;border-radius:5px;letter-spacing:0.12em;font-family:'DM Mono',monospace;">BETA</span>
  </div>
  <div class="nav-right">
    <span class="nav-badge">Beta · 무료 체험 중</span>
    <a class="btn-nav" href="/slides">슬라이드 열람</a>
  </div>
</nav>
<section class="hero">
  <div class="hero-left">
    <div class="hero-tag">
      <div class="hero-dot"></div>
      <span class="hero-tag-text">Whole-Slide Imaging · Digital Pathology</span>
    </div>
    <h1 class="hero-title">
      디지털 병리<br>슬라이드<br><span class="accent">교육 플랫폼</span>
    </h1>
    <p class="hero-desc">의과대학 학생과 전공의를 위한 고해상도 디지털 슬라이드 아카이브. 현미경 수업의 연장선에서, 언제 어디서나 40배율까지 자유롭게 관찰하세요.</p>
    <div class="hero-cta">
      <a class="btn-primary" href="/slides">슬라이드 체험하기 →</a>
      <button class="btn-secondary">기관 구독 문의</button>
    </div>
    <div class="hero-stats">
      <div><div class="stat-num">2+</div><div class="stat-label">샘플 슬라이드</div></div>
      <div><div class="stat-num">40×</div><div class="stat-label">최대 배율</div></div>
      <div><div class="stat-num">WSI</div><div class="stat-label">고해상도 이미징</div></div>
    </div>
  </div>
  <div class="hero-right">
    <div class="slide-viewer-mock">
      <div class="tissue-bg"></div>
      <div class="viewer-overlay">
        <div class="viewer-top">
          <span class="viewer-badge">● LIVE DEMO</span>
          <span class="viewer-info-badge">WSI · 소장 H&amp;E · 57,344 × 60,416 px</span>
        </div>
        <div class="viewer-bottom">
          <div class="viewer-meta">
            <div class="viewer-meta-title">소장 · Small Intestine</div>
            <div class="viewer-meta-sub">Hematoxylin &amp; Eosin · 3DHISTECH Sample</div>
          </div>
          <div class="viewer-magnify">
            <button class="mag-btn">1×</button>
            <button class="mag-btn">4×</button>
            <button class="mag-btn active">10×</button>
            <button class="mag-btn">40×</button>
          </div>
        </div>
      </div>
    </div>
    <div class="hero-right-info">
      <div><div class="hri-label">조직</div><div class="hri-value">소장 · 융모 구조</div></div>
      <div class="hri-divider"></div>
      <div><div class="hri-label">염색법</div><div class="hri-value">H&amp;E Stain</div></div>
      <div class="hri-divider"></div>
      <div><div class="hri-label">해상도</div><div class="hri-value">57K × 60K px</div></div>
    </div>
  </div>
</section>
<div class="mvp-notice">
  <div class="mvp-dot"></div>
  <p class="mvp-text"><strong>베타 서비스 안내</strong> — 현재 시범 운영 중입니다. 샘플 슬라이드를 무료로 체험하실 수 있으며, 기관 구독 및 콘텐츠 확장은 순차적으로 진행될 예정입니다.</p>
</div>
<section class="section-discipline">
  <div class="section-label">Browse by Discipline</div>
  <h2 class="section-title">과목별 슬라이드 라이브러리</h2>
  <div class="discipline-grid">
    <a class="discipline-card" href="/slides">
      <div class="card-core-badge">CORE</div>
      <div class="card-icon"><svg viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg></div>
      <div class="card-count">2 SLIDES · SAMPLE</div>
      <div class="card-title-ko">조직학 · 병리학</div>
      <div class="card-title-en">Histology · Pathology</div>
      <p class="card-desc">정상 조직 및 병변 조직의 미시적 구조를 고해상도 디지털 슬라이드로 관찰합니다.</p>
      <span class="card-arrow">→</span>
    </a>
    <div class="discipline-card" style="opacity:0.55; cursor:default;">
      <div class="card-icon"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M4.22 4.22l2.12 2.12M17.66 17.66l2.12 2.12M2 12h3M19 12h3M4.22 19.78l2.12-2.12M17.66 6.34l2.12-2.12"/></svg></div>
      <div class="card-count">준비 중</div>
      <div class="card-title-ko">기생충학</div>
      <div class="card-title-en">Parasitology</div>
      <p class="card-desc">기생충의 조직학적 특징과 숙주 반응을 고해상도로 학습합니다.</p>
      <span class="card-arrow">→</span>
    </div>
    <div class="discipline-card" style="opacity:0.55; cursor:default;">
      <div class="card-icon"><svg viewBox="0 0 24 24"><path d="M8 3c0 0 1 2 1 5s-2 5-2 8c0 2.21 1.79 4 4 4s4-1.79 4-4c0-3-2-5-2-8s1-5 1-5"/></svg></div>
      <div class="card-count">준비 중</div>
      <div class="card-title-ko">발생학</div>
      <div class="card-title-en">Embryology</div>
      <p class="card-desc">발생 단계별 조직 변화를 슬라이드로 학습합니다.</p>
      <span class="card-arrow">→</span>
    </div>
  </div>
</section>
<footer>
  <span class="footer-logo">SlideAtlas</span>
  <span class="footer-copy">© 2026 Lami International Co., Ltd.</span>
  <div class="footer-links">
    <a href="mailto:mcmajo@naver.com">문의</a>
    <a href="#">기관 구독</a>
    <a href="/slides">슬라이드 열람</a>
  </div>
</footer>
</body>
</html>'''

@app.route('/viewer')
def viewer_default():
    data = load_slides()
    slides = [s for s in data.get('slides', []) if s.get('active')]
    if slides:
        return redirect(f'/viewer/{slides[0]["id"]}')
    return redirect('/')

@app.route('/viewer/<slide_id>')
def viewer(slide_id):
    data = load_slides()
    slide_info = next((s for s in data.get('slides', []) if s['id'] == slide_id), None)
    if not slide_info:
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
body {{ background:#0F1F3D; color:white; font-family:"Segoe UI",sans-serif;
  display:flex; align-items:center; justify-content:center; height:100vh; }}
.splash {{ text-align:center; }}
.splash img {{ height:80px; width:auto; margin-bottom:32px; }}
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
<div class="splash">
  <img src="/static/slideatlas_logo.png" alt="SlideAtlas">
  <div class="progress-bar"></div>
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

    if use_ec2:
        tile_source_url = f"/ec2tile/dzi/{slide_id}.dzi"
        # slides.json에서 실제 크기 가져오기
        W = slide_info.get("width", W)
        H = slide_info.get("height", H)
    else:
        tile_source_url = f"/dzi/{slide_id}.dzi"

    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>SlideAtlas — {title_ko}</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/openseadragon/4.1.0/openseadragon.min.js"></script>
<style>
@import url('https://cdn.jsdelivr.net/gh/sunn-us/SUIT/fonts/variable/woff2/SUIT-Variable.css');
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{background:#0d1219;font-family:"SUIT Variable","SUIT",sans-serif;overflow:hidden;height:100vh;display:flex;flex-direction:column;}}
#header{{background:rgba(15,31,61,0.97);border-bottom:1px solid rgba(255,255,255,0.08);padding:0 20px;height:50px;display:flex;align-items:center;justify-content:space-between;flex-shrink:0;z-index:100;}}
.logo{{display:flex;flex-direction:column;line-height:1;gap:1px;text-decoration:none;}}
.logo-slide{{font-size:7px;letter-spacing:0.22em;color:#2A9D8F;font-family:"DM Mono",monospace;font-weight:500;}}
.logo-atlas{{font-size:18px;font-weight:800;color:#fff;}}
#hdr-center{{font-size:11px;color:rgba(255,255,255,0.4);font-family:"DM Mono",monospace;}}
#hdr-right{{display:flex;align-items:center;gap:8px;}}
.hdr-back{{color:#2A9D8F;font-size:12px;text-decoration:none;border:1px solid rgba(42,157,143,0.3);padding:4px 10px;border-radius:5px;}}
.hdr-btn{{background:transparent;color:rgba(255,255,255,0.45);border:1px solid rgba(255,255,255,0.12);padding:4px 10px;border-radius:5px;font-size:12px;cursor:pointer;font-family:"SUIT Variable",sans-serif;}}
#main{{display:grid;grid-template-columns:1fr 310px;flex:1;overflow:hidden;}}
#viewer-wrap{{position:relative;overflow:hidden;background:#111824;}}
#viewer{{position:absolute;inset:0;}}
#toolbar{{position:absolute;bottom:16px;left:50%;transform:translateX(-50%);background:rgba(15,31,61,0.95);border:1px solid rgba(255,255,255,0.12);border-radius:10px;padding:8px 16px;display:flex;align-items:center;gap:6px;z-index:50;box-shadow:0 8px 32px rgba(0,0,0,0.4);}}
.mb{{background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.15);color:rgba(255,255,255,0.8);padding:5px 12px;border-radius:6px;cursor:pointer;font-size:11px;font-family:"DM Mono",monospace;transition:all 0.15s;}}
.mb:hover{{background:rgba(42,157,143,0.3);border-color:#2A9D8F;color:white;}}
.mb.active{{background:#2A9D8F;border-color:#2A9D8F;color:#fff;}}
#md{{font-family:"DM Mono",monospace;font-size:14px;color:white;min-width:48px;text-align:center;font-weight:500;}}
#scale{{position:absolute;bottom:16px;left:16px;background:rgba(0,0,0,0.6);color:rgba(255,255,255,0.7);padding:5px 12px;border-radius:6px;font-family:"DM Mono",monospace;font-size:11px;border:1px solid rgba(255,255,255,0.08);z-index:50;}}
#ai-panel{{background:#F7F4EF;border-left:1px solid #E5E0D8;display:flex;flex-direction:column;overflow:hidden;}}
.slide-meta{{padding:14px 18px;border-bottom:1px solid #E5E0D8;background:#fff;flex-shrink:0;}}
.meta-title{{font-size:15px;font-weight:800;letter-spacing:-0.02em;color:#0F1F3D;margin-bottom:3px;}}
.meta-sub{{font-size:11px;color:#9B9490;font-family:"DM Mono",monospace;}}
.meta-badges{{display:flex;gap:5px;margin-top:8px;}}
.mbadge{{font-size:10px;font-weight:600;padding:3px 9px;border-radius:4px;font-family:"DM Mono",monospace;}}
.mbadge-he{{background:#EBF6F5;color:#0F6E56;border:1px solid rgba(42,157,143,0.2);}}
.mbadge-sys{{background:#F0EDE8;color:#6B6560;border:1px solid #E5E0D8;}}
.mbadge-mag{{background:#FEF7E6;color:#8B6010;border:1px solid rgba(233,196,106,0.3);}}
.tabs{{display:flex;border-bottom:1px solid #E5E0D8;background:#fff;flex-shrink:0;}}
.tab{{flex:1;padding:11px 0;text-align:center;font-size:13px;font-weight:600;color:#9B9490;cursor:pointer;border-bottom:2px solid transparent;transition:all 0.2s;}}
.tab.active{{color:#2A9D8F;border-bottom-color:#2A9D8F;}}
.tab:hover:not(.active){{color:#0F1F3D;}}
.tab-content{{flex:1;overflow:hidden;display:none;flex-direction:column;}}
.tab-content.active{{display:flex;}}
.guide-scroll{{flex:1;overflow-y:auto;padding:16px 18px;background:#F7F4EF;}}
.guide-scroll::-webkit-scrollbar{{width:3px;}}
.guide-scroll::-webkit-scrollbar-thumb{{background:#E5E0D8;border-radius:2px;}}
.guide-mag-header{{display:flex;align-items:center;gap:7px;margin-bottom:14px;}}
.guide-mag-dot{{width:7px;height:7px;border-radius:50%;background:#2A9D8F;animation:pulse 2s infinite;flex-shrink:0;}}
@keyframes pulse{{0%,100%{{opacity:1;}}50%{{opacity:0.4;}}}}
.guide-mag-label{{font-size:11px;color:#2A9D8F;font-family:"DM Mono",monospace;font-weight:600;letter-spacing:0.04em;}}
.ai-bubble{{background:#fff;border:1px solid #E5E0D8;border-radius:10px;border-top-left-radius:3px;padding:13px 15px;margin-bottom:12px;box-shadow:0 1px 4px rgba(15,31,61,0.05);}}
.ai-bubble-header{{display:flex;align-items:center;gap:7px;margin-bottom:8px;}}
.ai-icon{{width:20px;height:20px;background:#2A9D8F;border-radius:5px;display:flex;align-items:center;justify-content:center;flex-shrink:0;}}
.ai-icon svg{{width:11px;height:11px;stroke:#fff;fill:none;stroke-width:2;}}
.ai-label{{font-size:10px;color:#2A9D8F;font-weight:700;letter-spacing:0.06em;font-family:"DM Mono",monospace;}}
.ai-text{{font-size:13px;color:#3D3530;line-height:1.7;word-break:keep-all;}}
.ai-text strong{{color:#0F1F3D;font-weight:700;}}
.structure-list{{margin-top:8px;display:flex;flex-direction:column;gap:6px;}}
.struct-item{{display:flex;align-items:flex-start;gap:8px;padding:9px 12px;background:#fff;border-radius:7px;border:1px solid #E5E0D8;}}
.struct-dot{{width:7px;height:7px;border-radius:50%;background:#2A9D8F;flex-shrink:0;margin-top:5px;}}
.struct-text{{font-size:12px;color:#4A4540;line-height:1.55;word-break:keep-all;}}
.struct-text strong{{color:#0F1F3D;font-weight:700;}}
.observe-box{{background:#EBF6F5;border:1px solid rgba(42,157,143,0.2);border-radius:8px;padding:12px 14px;margin-top:12px;}}
.observe-label{{font-size:10px;color:#2A9D8F;font-weight:700;letter-spacing:0.1em;font-family:"DM Mono",monospace;margin-bottom:6px;}}
.observe-text{{font-size:12px;color:#2D5A52;line-height:1.65;word-break:keep-all;}}
.chat-scroll{{flex:1;overflow-y:auto;padding:14px 18px;display:flex;flex-direction:column;gap:10px;background:#F7F4EF;}}
.chat-scroll::-webkit-scrollbar{{width:3px;}}
.chat-scroll::-webkit-scrollbar-thumb{{background:#E5E0D8;border-radius:2px;}}
.msg-ai{{display:flex;gap:8px;align-items:flex-start;}}
.msg-ai-icon{{width:24px;height:24px;background:#2A9D8F;border-radius:6px;display:flex;align-items:center;justify-content:center;flex-shrink:0;}}
.msg-ai-icon svg{{width:12px;height:12px;stroke:#fff;fill:none;stroke-width:2;}}
.msg-ai-bubble{{background:#fff;border:1px solid #E5E0D8;border-radius:10px;border-top-left-radius:3px;padding:10px 13px;font-size:13px;color:#3D3530;line-height:1.65;max-width:230px;word-break:keep-all;box-shadow:0 1px 3px rgba(15,31,61,0.05);}}
.msg-user{{display:flex;justify-content:flex-end;}}
.msg-user-bubble{{background:#0F1F3D;border-radius:10px;border-bottom-right-radius:3px;padding:10px 13px;font-size:13px;color:rgba(255,255,255,0.9);line-height:1.65;max-width:230px;word-break:keep-all;}}
.typing-indicator{{display:flex;gap:4px;align-items:center;padding:10px 12px;}}
.typing-dot{{width:6px;height:6px;border-radius:50%;background:#2A9D8F;animation:typing 1.2s infinite;}}
.typing-dot:nth-child(2){{animation-delay:0.2s;}}
.typing-dot:nth-child(3){{animation-delay:0.4s;}}
@keyframes typing{{0%,60%,100%{{opacity:0.3;transform:scale(0.8);}}30%{{opacity:1;transform:scale(1);}}}}
.chat-input-area{{padding:12px 16px;border-top:1px solid #E5E0D8;background:#fff;flex-shrink:0;}}
.ctx-tag{{display:flex;align-items:center;gap:5px;margin-bottom:8px;font-size:10px;color:#9B9490;font-family:"DM Mono",monospace;}}
.ctx-dot{{width:5px;height:5px;border-radius:50%;background:#2A9D8F;}}
.chat-input-row{{display:flex;gap:7px;}}
.chat-input{{flex:1;background:#F7F4EF;border:1px solid #E5E0D8;border-radius:8px;padding:9px 13px;font-size:13px;color:#0F1F3D;font-family:"SUIT Variable",sans-serif;outline:none;}}
.chat-input::placeholder{{color:#B8B4AE;}}
.chat-input:focus{{border-color:#2A9D8F;}}
.chat-send{{background:#2A9D8F;border:none;width:36px;height:36px;border-radius:8px;display:flex;align-items:center;justify-content:center;cursor:pointer;flex-shrink:0;}}
.chat-send:hover{{background:#238b7f;}}
.chat-send svg{{width:14px;height:14px;stroke:#fff;fill:none;stroke-width:2;}}
.quiz-scroll{{flex:1;overflow-y:auto;padding:16px 18px;background:#F7F4EF;}}
.quiz-scroll::-webkit-scrollbar{{width:3px;}}
.quiz-scroll::-webkit-scrollbar-thumb{{background:#E5E0D8;border-radius:2px;}}
.quiz-icon-wrap{{width:52px;height:52px;background:#FEF7E6;border:1px solid rgba(233,196,106,0.3);border-radius:14px;display:flex;align-items:center;justify-content:center;margin:0 auto 12px;}}
.quiz-icon-wrap svg{{width:24px;height:24px;stroke:#C9A227;fill:none;stroke-width:1.5;}}
.quiz-stats{{display:flex;gap:8px;margin:14px 0;}}
.quiz-stat{{flex:1;background:#fff;border:1px solid #E5E0D8;border-radius:8px;padding:10px;text-align:center;}}
.quiz-stat-num{{font-size:18px;font-weight:800;}}
.quiz-stat-lbl{{font-size:10px;color:#9B9490;font-family:"DM Mono",monospace;margin-top:2px;}}
.quiz-start-btn{{background:#0F1F3D;color:#fff;border:none;padding:12px;border-radius:9px;font-size:14px;font-weight:700;font-family:"SUIT Variable",sans-serif;cursor:pointer;width:100%;}}
.quiz-start-btn:hover{{background:#1a2f52;}}
.quiz-progress{{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;}}
.qprog-label{{font-size:11px;color:#9B9490;font-family:"DM Mono",monospace;}}
.qprog-bar{{height:4px;background:#E5E0D8;border-radius:2px;flex:1;margin:0 10px;}}
.qprog-fill{{height:100%;background:#2A9D8F;border-radius:2px;transition:width 0.3s;}}
.quiz-q{{font-size:14px;font-weight:700;color:#0F1F3D;line-height:1.6;margin-bottom:14px;word-break:keep-all;}}
.quiz-options{{display:flex;flex-direction:column;gap:7px;}}
.quiz-opt{{background:#fff;border:1px solid #E5E0D8;border-radius:8px;padding:11px 14px;font-size:13px;color:#3D3530;cursor:pointer;transition:all 0.15s;display:flex;align-items:center;gap:10px;word-break:keep-all;}}
.quiz-opt:hover{{border-color:#2A9D8F;color:#0F1F3D;background:#F0FAF8;}}
.quiz-opt.correct{{border-color:#2A9D8F;background:#EBF6F5;color:#0F6E56;pointer-events:none;}}
.quiz-opt.wrong{{border-color:#F4A58A;background:#FEF0EB;color:#9B5040;pointer-events:none;}}
.opt-num{{width:22px;height:22px;border-radius:50%;border:1.5px solid #C8C4BC;display:flex;align-items:center;justify-content:center;font-size:11px;font-family:"DM Mono",monospace;flex-shrink:0;color:#6B6560;}}
.quiz-explanation{{background:#EBF6F5;border:1px solid rgba(42,157,143,0.2);border-radius:8px;padding:11px 13px;margin-top:10px;font-size:12px;color:#2D5A52;line-height:1.65;word-break:keep-all;display:none;}}
.quiz-next-btn{{background:#0F1F3D;color:#fff;border:none;padding:10px;border-radius:8px;font-size:13px;font-weight:600;font-family:"SUIT Variable",sans-serif;cursor:pointer;width:100%;margin-top:10px;display:none;}}
</style>
</head>
<body>
<div id="header">
  <div style="display:flex;align-items:center;gap:12px;">
    <a href="/slides" class="hdr-back">← 목록</a>
    <a href="/" style="display:flex;align-items:center;text-decoration:none;">
      <img src="/static/slideatlas_logo.png" alt="SlideAtlas" style="height:32px;width:auto;">
    </a>
  </div>
  <span id="hdr-center">{title_ko} &nbsp;/&nbsp; {stain} &nbsp;/&nbsp; <span id="hdr-mag">전체</span></span>
  <div id="hdr-right">
    <button class="hdr-btn" id="ai-toggle" onclick="togglePanel()">AI 패널 숨기기</button>
  </div>
</div>
<div id="main">
  <div id="viewer-wrap">
    <div id="viewer"></div>
    <div id="scale">— mm</div>
    <div id="toolbar">
      <button class="mb" onclick="zi()">−</button>
      <div id="md">전체</div>
      <button class="mb" onclick="zo()">+</button>
      <span style="color:rgba(255,255,255,0.15);font-size:18px;">|</span>
      <button class="mb" onclick="fit()">전체</button>
      <button class="mb" onclick="sm(1)">1×</button>
      <button class="mb" onclick="sm(4)">4×</button>
      <button class="mb" onclick="sm(10)">10×</button>
      <button class="mb" onclick="sm(20)">20×</button>
      <button class="mb" onclick="sm(40)">40×</button>
    </div>
  </div>
  <div id="ai-panel">
    <div class="slide-meta">
      <div class="meta-title">{title_ko}</div>
      <div class="meta-sub">{slide_id} · {system}</div>
      <div class="meta-badges">
        <span class="mbadge mbadge-he">{stain}</span>
        <span class="mbadge mbadge-sys">{system}</span>
        <span class="mbadge mbadge-mag" id="mag-badge">전체</span>
      </div>
    </div>
    <div class="tabs">
      <div class="tab active" onclick="switchTab(0)">구조 가이드</div>
      <div class="tab" onclick="switchTab(1)">질문하기</div>
      <div class="tab" onclick="switchTab(2)">퀴즈</div>
    </div>
    <div class="tab-content active" id="tab0">
      <div class="guide-scroll">
        <div class="guide-mag-header">
          <div class="guide-mag-dot"></div>
          <span class="guide-mag-label" id="guide-mag-label">전체 배율 · 슬라이드 개요</span>
        </div>
        <div class="ai-bubble">
          <div class="ai-bubble-header">
            <div class="ai-icon"><svg viewBox="0 0 24 24"><path d="M12 2a10 10 0 1 0 10 10"/><path d="M12 6v6l4 2"/></svg></div>
            <span class="ai-label">ATLAS AI</span>
          </div>
          <p class="ai-text" id="guide-main-text">슬라이드를 로드하는 중입니다. 배율을 조정하면 구조 가이드가 업데이트됩니다.</p>
        </div>
        <div class="structure-list" id="structure-list"></div>
        <div class="observe-box">
          <div class="observe-label">OBSERVE</div>
          <p class="observe-text" id="observe-text">H&amp;E 염색에서 핵은 <strong style="color:#6B4FA0;">진한 보라색</strong>, 세포질과 기저막은 <strong style="color:#C2607A;">분홍색</strong>으로 관찰됩니다.</p>
        </div>
      </div>
    </div>
    <div class="tab-content" id="tab1">
      <div class="chat-scroll" id="chat-messages">
        <div class="msg-ai">
          <div class="msg-ai-icon"><svg viewBox="0 0 24 24"><path d="M12 2a10 10 0 1 0 10 10"/><path d="M12 6v6l4 2"/></svg></div>
          <div class="msg-ai-bubble">{title_ko} 슬라이드에 대해 무엇이든 질문하세요.</div>
        </div>
      </div>
      <div class="chat-input-area">
        <div class="ctx-tag">
          <div class="ctx-dot"></div>
          <span id="ctx-label">{title_ko} · 전체 배율 컨텍스트 포함</span>
        </div>
        <div class="chat-input-row">
          <input class="chat-input" id="chat-input" placeholder="이 구조에 대해 질문하세요..." onkeydown="if(event.key==='Enter')sendChat()"/>
          <button class="chat-send" onclick="sendChat()"><svg viewBox="0 0 24 24"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg></button>
        </div>
      </div>
    </div>
    <div class="tab-content" id="tab2">
      <div class="quiz-scroll">
        <div id="quiz-start-view">
          <div style="text-align:center;padding-top:16px;">
            <div class="quiz-icon-wrap"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg></div>
            <div style="font-size:14px;font-weight:700;color:#0F1F3D;margin-bottom:6px;">{title_ko} 퀴즈</div>
            <div style="font-size:12px;color:#6B6560;line-height:1.6;word-break:keep-all;">이 슬라이드를 기반으로 조직학 수준 퀴즈를 생성합니다.</div>
          </div>
          <div class="quiz-stats">
            <div class="quiz-stat"><div class="quiz-stat-num" style="color:#E9C46A;">3</div><div class="quiz-stat-lbl">문제</div></div>
            <div class="quiz-stat"><div class="quiz-stat-num" style="color:#2A9D8F;">{stain}</div><div class="quiz-stat-lbl">유형</div></div>
            <div class="quiz-stat"><div class="quiz-stat-num" style="color:#9B9490;">★★</div><div class="quiz-stat-lbl">난이도</div></div>
          </div>
          <button class="quiz-start-btn" onclick="startQuiz()">퀴즈 시작 →</button>
        </div>
        <div id="quiz-play-view" style="display:none;">
          <div class="quiz-progress">
            <span class="qprog-label" id="q-num">1 / 3</span>
            <div class="qprog-bar"><div class="qprog-fill" id="q-prog" style="width:33%;"></div></div>
            <span class="qprog-label">{system}</span>
          </div>
          <div class="quiz-q" id="q-text"></div>
          <div class="quiz-options" id="q-opts"></div>
          <div class="quiz-explanation" id="q-exp"></div>
          <button class="quiz-next-btn" id="q-next" onclick="nextQuestion()">다음 문제 →</button>
        </div>
        <div id="quiz-result-view" style="display:none;text-align:center;padding-top:24px;">
          <div style="font-size:32px;font-weight:800;color:#E9C46A;margin-bottom:8px;" id="result-score"></div>
          <div style="font-size:14px;color:#6B6560;margin-bottom:20px;">문제를 맞혔습니다</div>
          <button class="quiz-start-btn" onclick="resetQuiz()">다시 풀기</button>
        </div>
      </div>
    </div>
  </div>
</div>
<script>
var SLIDE_ID = "{slide_id}";
var SLIDE_TITLE = "{title_ko}";
var SLIDE_STAIN = "{stain}";
var SLIDE_W = {W};
var SLIDE_H = {H};
var SLIDE_MPP = {mpp};
var QUIZ = [];
var qIdx = 0, score = 0;

var osd = OpenSeadragon({{
  id: "viewer",
  prefixUrl: "https://cdnjs.cloudflare.com/ajax/libs/openseadragon/4.1.0/images/",
  tileSources: "{tile_source_url}",
  showNavigationControl: false,
  animationTime: 0.3,
  blendTime: 0.1,
  constrainDuringPan: false,
  maxZoomPixelRatio: 2,
  minZoomLevel: 0.001,
  visibilityRatio: 0.05,
  showNavigator: true,
  navigatorPosition: "BOTTOM_RIGHT",
  navigatorHeight: 100,
  navigatorWidth: 140,
  defaultZoomLevel: 0,
}});

osd.addHandler('zoom', updViewer);
osd.addHandler('open', function() {{ osd.viewport.goHome(true); setTimeout(updViewer, 400); }});

function updViewer() {{
  try {{
    var z = osd.viewport.getZoom(true);
    // 정확한 배율: 화면픽셀 기준 계산
    // zoom=1이면 슬라이드 전체폭=뷰포트폭
    // 실제 배율 = (화면에서 1mm당 슬라이드픽셀수) / (기준 10x에서 1mm당 픽셀수)
    var tiledImageW = osd.world.getItemAt(0) ? osd.world.getItemAt(0).getContentSize().x : SLIDE_W;
    var viewportW = osd.viewport.getBounds().width;
    // viewportW는 0~1 정규화 기준, 1=슬라이드폭
    // 화면에 보이는 슬라이드 폭(픽셀) = SLIDE_W / viewportW * (containerW/SLIDE_W)
    // 더 단순하게: 1픽셀당 실제 크기(um) = viewportW * SLIDE_W * SLIDE_MPP / containerW
    var containerW = osd.container ? osd.container.clientWidth : 1000;
    var umPerScreenPx = viewportW * SLIDE_W * SLIDE_MPP / containerW;
    // 10x 기준: 1μm = 1화면픽셀 (표준 현미경 기준)
    var mag = 10 / umPerScreenPx / 10;
    // 실제 현미경 배율 = 1/umPerScreenPx * SCALE_FACTOR
    // 40x objective에서 1px = 0.25μm이므로
    mag = 1 / umPerScreenPx * 0.25 * 40;
    var magText = mag >= 1 ? (Math.round(mag*10)/10)+'×' : mag.toFixed(3)+'×';
    document.getElementById('md').textContent = magText;
    document.getElementById('hdr-mag').textContent = magText;
    document.getElementById('mag-badge').textContent = magText;
    document.getElementById('ctx-label').textContent = '{title_ko} · ' + magText + ' 배율';
    var vw = osd.viewport.getBounds().width;
    var umW = vw * SLIDE_W * SLIDE_MPP;
    var sc = Math.round(umW / 5);
    document.getElementById('scale').textContent =
      sc >= 1000000 ? (sc/1000000).toFixed(1)+' m' :
      sc >= 1000 ? (sc/1000).toFixed(2)+' mm' : sc+' μm';
  }} catch(e) {{}}
}}

function fit() {{ osd.viewport.goHome(false); setTimeout(updViewer,200); }}
function zi() {{ osd.viewport.zoomBy(1/1.8); setTimeout(updViewer,100); }}
function zo() {{ osd.viewport.zoomBy(1.8); setTimeout(updViewer,100); }}
function sm(m) {{
  // 원하는 배율(m)에서의 umPerScreenPx = 0.25*40/m
  // viewportW = umPerScreenPx * containerW / (SLIDE_W * SLIDE_MPP)
  var containerW = osd.container ? osd.container.clientWidth : 1000;
  var umPerPx = (0.25 * 40 / m);
  var targetViewportW = umPerPx * containerW / (SLIDE_W * SLIDE_MPP);
  osd.viewport.zoomTo(1 / targetViewportW);
  setTimeout(updViewer,100);
}}

function switchTab(idx) {{
  document.querySelectorAll('.tab').forEach(function(t,i){{ t.classList.toggle('active', i===idx); }});
  document.querySelectorAll('.tab-content').forEach(function(c,i){{ c.classList.toggle('active', i===idx); }});
}}

function togglePanel() {{
  var panel = document.getElementById('ai-panel');
  var main = document.getElementById('main');
  var btn = document.getElementById('ai-toggle');
  if(panel.style.display === 'none') {{
    panel.style.display = 'flex';
    main.style.gridTemplateColumns = '1fr 310px';
    btn.textContent = 'AI 패널 숨기기';
  }} else {{
    panel.style.display = 'none';
    main.style.gridTemplateColumns = '1fr';
    btn.textContent = 'AI 패널 열기';
  }}
}}

function sendChat() {{
  var input = document.getElementById('chat-input');
  var msg = input.value.trim();
  if(!msg) return;
  input.value = '';
  var containerW2 = osd.container ? osd.container.clientWidth : 1000;
  var vw2 = osd.viewport.getBounds().width;
  var umPerPx2 = vw2 * SLIDE_W * SLIDE_MPP / containerW2;
  var mag = 1 / umPerPx2 * 0.25 * 40;
  var magText = mag >= 1 ? Math.round(mag*10)/10 + '×' : mag.toFixed(3) + '×';
  var msgs = document.getElementById('chat-messages');
  msgs.innerHTML += '<div class="msg-user"><div class="msg-user-bubble">'+escHtml(msg)+'</div></div>';
  var typingId = 'typing-' + Date.now();
  msgs.innerHTML += '<div class="msg-ai" id="'+typingId+'"><div class="msg-ai-icon"><svg viewBox="0 0 24 24"><path d="M12 2a10 10 0 1 0 10 10"/><path d="M12 6v6l4 2"/></svg></div><div class="msg-ai-bubble"><div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div></div></div>';
  msgs.scrollTop = msgs.scrollHeight;
  var SYSTEM = "You are SlideAtlas AI tutor. Current slide: {title_ko} ({title_en}), {stain} stain, {system}. Current magnification: " + magText + ". Answer in Korean, as a histology/pathology education expert. Keep answers to 3-5 sentences.";
  var bubble = null;
  var fullText = '';
  fetch("/api/chat", {{
    method: "POST",
    headers: {{"Content-Type": "application/json"}},
    body: JSON.stringify({{ message: msg, system: SYSTEM }})
  }})
  .then(function(r) {{
    var reader = r.body.getReader();
    var decoder = new TextDecoder();
    var buffer = '';
    function read() {{
      reader.read().then(function(result) {{
        if(result.done) return;
        buffer += decoder.decode(result.value, {{stream: true}});
        var lines = buffer.split('\\n');
        buffer = lines.pop();
        for(var i=0; i<lines.length; i++) {{
          var line = lines[i].trim();
          if(line.indexOf('data: ') === 0) {{
            try {{
              var obj = JSON.parse(line.slice(6));
              if(obj.text) {{
                fullText += obj.text;
                var el = document.getElementById(typingId);
                if(el) {{
                  if(!bubble) {{ bubble = el.querySelector('.msg-ai-bubble'); }}
                  bubble.innerHTML = renderMd(fullText);
                  msgs.scrollTop = msgs.scrollHeight;
                }}
              }}
              if(obj.error) {{
                var el = document.getElementById(typingId);
                if(el) el.querySelector('.msg-ai-bubble').textContent = 'API 오류: ' + obj.error;
              }}
            }} catch(e) {{}}
          }}
        }}
        read();
      }});
    }}
    read();
  }})
  .catch(function() {{
    var el = document.getElementById(typingId);
    if(el) el.querySelector('.msg-ai-bubble').textContent = "연결 오류가 발생했습니다.";
  }});
}}

function escHtml(s) {{ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }}

function renderMd(s) {{
  var h = escHtml(s);
  var lines = h.split('\\n');
  for(var i=0; i<lines.length; i++) {{
    if(lines[i].indexOf('# ') === 0) {{ lines[i] = '<strong style="font-size:13px;color:#0F1F3D;display:block;margin-bottom:4px;">' + lines[i].slice(2) + '</strong>'; }}
    else if(lines[i].indexOf('## ') === 0) {{ lines[i] = '<strong style="font-size:13px;color:#0F1F3D;display:block;margin-bottom:4px;">' + lines[i].slice(3) + '</strong>'; }}
  }}
  h = lines.join('<br>');
  var parts = h.split('**');
  var result = '';
  for(var i=0; i<parts.length; i++) {{ result += i%2===1 ? '<strong>'+parts[i]+'</strong>' : parts[i]; }}
  return result;
}}

function startQuiz() {{
  if(QUIZ.length === 0) {{
    fetch("/api/chat", {{
      method: "POST",
      headers: {{"Content-Type": "application/json"}},
      body: JSON.stringify({{
        message: "{title_ko} ({title_en}) {stain} 슬라이드에 대한 조직학/병리학 퀴즈 3문제를 JSON 형식으로만 생성해주세요. 형식: [{{\\"q\\":\\"질문\\",\\"opts\\":[\\"A\\",\\"B\\",\\"C\\",\\"D\\"],\\"ans\\":0,\\"exp\\":\\"해설\\"}}]",
        system: "당신은 의과대학 조직학/병리학 교수입니다. 요청한 JSON 형식으로만 응답하세요. 다른 텍스트는 절대 포함하지 마세요."
      }})
    }})
    .then(function(r){{ return r.json(); }})
    .then(function(data) {{
      try {{
        var txt = data.reply.replace(/```json|```/g,'').trim();
        QUIZ = JSON.parse(txt);
      }} catch(e) {{
        QUIZ = [{{q:"{title_ko}의 주요 특징은?",opts:["세포 구조 변화","염색 반응","조직 배열","모두 해당"],ans:3,exp:"H&E 염색에서 다양한 특징을 관찰할 수 있습니다."}}];
      }}
      qIdx=0; score=0;
      document.getElementById('quiz-start-view').style.display='none';
      document.getElementById('quiz-play-view').style.display='block';
      renderQuestion();
    }});
    return;
  }}
  qIdx=0; score=0;
  document.getElementById('quiz-start-view').style.display='none';
  document.getElementById('quiz-play-view').style.display='block';
  renderQuestion();
}}

function renderQuestion() {{
  var q = QUIZ[qIdx];
  document.getElementById('q-num').textContent = (qIdx+1) + ' / ' + QUIZ.length;
  document.getElementById('q-prog').style.width = ((qIdx+1)/QUIZ.length*100) + '%';
  document.getElementById('q-text').textContent = q.q;
  document.getElementById('q-exp').style.display='none';
  document.getElementById('q-exp').textContent=q.exp;
  document.getElementById('q-next').style.display='none';
  var opts = document.getElementById('q-opts');
  var letters = ['A','B','C','D'];
  opts.innerHTML = q.opts.map(function(o,i) {{
    return '<div class="quiz-opt" onclick="answerQ(this,'+i+')"><span class="opt-num">'+letters[i]+'</span>'+escHtml(o)+'</div>';
  }}).join('');
}}

function answerQ(el, idx) {{
  var q = QUIZ[qIdx];
  document.querySelectorAll('.quiz-opt').forEach(function(o){{ o.onclick=null; }});
  if(idx===q.ans){{ el.classList.add('correct'); score++; }}
  else {{ el.classList.add('wrong'); document.querySelectorAll('.quiz-opt')[q.ans].classList.add('correct'); }}
  document.getElementById('q-exp').style.display='block';
  document.getElementById('q-next').style.display='block';
  document.getElementById('q-next').textContent = qIdx<QUIZ.length-1 ? '다음 문제 →' : '결과 보기 →';
}}

function nextQuestion() {{
  qIdx++;
  if(qIdx>=QUIZ.length) {{
    document.getElementById('quiz-play-view').style.display='none';
    document.getElementById('quiz-result-view').style.display='block';
    document.getElementById('result-score').textContent = score+' / '+QUIZ.length;
  }} else {{ renderQuestion(); }}
}}

function resetQuiz() {{
  QUIZ=[];
  document.getElementById('quiz-result-view').style.display='none';
  document.getElementById('quiz-start-view').style.display='block';
}}
</script>
</body>
</html>'''

@app.route('/slides')
def slides():
    data = load_slides()
    all_slides = [s for s in data.get('slides', []) if s.get('active')]
    systems = {}
    stains = {}
    for s in all_slides:
        sys = s.get('system', '기타')
        stain = s.get('stain', '기타')
        systems[sys] = systems.get(sys, 0) + 1
        stains[stain] = stains.get(stain, 0) + 1
    stain_class = {'H&E': 'he', 'PAS': 'pas', 'Masson Trichrome': 'masson', 'Silver': 'silver'}
    cards_html = ''
    for s in all_slides:
        sid = s['id']
        sc = stain_class.get(s.get('stain',''), 'he')
        stain_badge = s.get('stain', 'H&E')
        cards_html += f'''
      <a class="slide-card" href="/viewer/{sid}">
        <div class="card-thumb thumb-{sc}">
          <span class="card-thumb-badge badge-{sc}">{stain_badge}</span>
          <span class="card-sample-badge">AVAILABLE</span>
          <span class="card-scale">WSI · 40×</span>
        </div>
        <div class="card-body">
          <div class="card-system">{s.get('system','')}</div>
          <div class="card-name-ko">{s.get('title_ko', sid)}</div>
          <div class="card-name-en">{s.get('title_en','')}</div>
          <div class="card-meta">
            <span class="card-stain">{stain_badge} · {s.get('institution','SA')}</span>
            <span class="card-link">열기 →</span>
          </div>
        </div>
      </a>'''
    system_filters = ''.join([f'<div class="filter-item"><div class="filter-item-left"><div class="filter-cb"></div><span class="filter-label">{sys}</span></div><span class="filter-count">{cnt}</span></div>' for sys, cnt in systems.items()])
    stain_filters = ''.join([f'<div class="filter-item"><div class="filter-item-left"><div class="filter-cb"></div><span class="filter-label">{st}</span></div><span class="filter-count">{cnt}</span></div>' for st, cnt in stains.items()])
    total = len(all_slides)
    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SlideAtlas — 슬라이드 목록</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
@import url('https://cdn.jsdelivr.net/gh/sunn-us/SUIT/fonts/variable/woff2/SUIT-Variable.css');
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{font-family:"SUIT Variable","SUIT",sans-serif;background:#F7F4EF;color:#0F1F3D;min-height:100vh;}}
nav{{background:#0F1F3D;padding:0 40px;height:58px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100;}}
.logo{{display:flex;flex-direction:column;line-height:1;gap:1px;text-decoration:none;}}
.logo-slide{{font-size:8px;font-weight:500;letter-spacing:0.22em;color:#2A9D8F;text-transform:uppercase;font-family:"DM Mono",monospace;}}
.logo-atlas{{font-size:20px;font-weight:800;color:#fff;letter-spacing:0.04em;}}
.nav-right{{display:flex;gap:10px;align-items:center;}}
.nav-badge{{font-size:11px;color:#2A9D8F;border:1px solid rgba(42,157,143,0.3);padding:4px 12px;border-radius:20px;font-weight:500;}}
.btn-nav{{background:#2A9D8F;color:#fff;border:none;padding:7px 18px;border-radius:6px;font-size:13px;font-family:"SUIT Variable",sans-serif;font-weight:600;cursor:pointer;text-decoration:none;display:inline-block;}}
.page-header{{padding:28px 40px 20px;background:#fff;border-bottom:1px solid #E5E0D8;}}
.page-title{{font-size:26px;font-weight:800;letter-spacing:-0.03em;margin-bottom:4px;}}
.page-desc{{font-size:14px;color:#6B6560;font-weight:300;}}
.layout{{display:grid;grid-template-columns:220px 1fr;align-items:start;}}
.sidebar{{padding:24px 20px;border-right:1px solid #E5E0D8;background:#fff;position:sticky;top:58px;min-height:calc(100vh - 58px);}}
.filter-group{{margin-bottom:22px;}}
.filter-group-title{{font-size:10px;font-weight:700;letter-spacing:0.1em;color:#9B9490;text-transform:uppercase;margin-bottom:10px;font-family:"DM Mono",monospace;}}
.filter-item{{display:flex;align-items:center;justify-content:space-between;padding:5px 0;}}
.filter-item-left{{display:flex;align-items:center;gap:8px;}}
.filter-cb{{width:14px;height:14px;border:1.5px solid #C8C4BC;border-radius:3px;}}
.filter-label{{font-size:13px;color:#0F1F3D;}}
.filter-count{{font-size:11px;color:#9B9490;font-family:"DM Mono",monospace;}}
.filter-divider{{height:1px;background:#E5E0D8;margin:14px 0;}}
.main{{padding:24px 32px;}}
.main-top{{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;}}
.result-count{{font-size:13px;color:#6B6560;}}
.result-count strong{{color:#0F1F3D;font-weight:700;}}
.slides-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;}}
.slide-card{{background:#fff;border:1px solid #E5E0D8;border-radius:12px;overflow:hidden;cursor:pointer;transition:all 0.2s;text-decoration:none;display:block;color:inherit;}}
.slide-card:hover{{border-color:#2A9D8F;transform:translateY(-2px);box-shadow:0 8px 24px rgba(15,31,61,0.08);}}
.card-thumb{{height:140px;position:relative;overflow:hidden;}}
.thumb-he{{background:radial-gradient(ellipse 80px 60px at 40% 45%,rgba(220,150,170,0.7) 0%,transparent 65%),linear-gradient(135deg,#f5e8ee,#f0dce6,#e8d0dc);}}
.thumb-pas{{background:radial-gradient(ellipse 70px 50px at 35% 50%,rgba(150,200,220,0.6) 0%,transparent 60%),linear-gradient(135deg,#e8f4f8,#d4eaf4);}}
.thumb-masson{{background:radial-gradient(ellipse 60px 50px at 42% 48%,rgba(100,160,220,0.6) 0%,transparent 60%),linear-gradient(135deg,#e8eef8,#d8e4f4);}}
.thumb-silver{{background:radial-gradient(ellipse 60px 45px at 40% 50%,rgba(180,180,160,0.7) 0%,transparent 60%),linear-gradient(135deg,#f2f0ea,#e8e6de);}}
.card-thumb-badge{{position:absolute;top:10px;left:10px;font-size:9px;font-weight:600;padding:3px 8px;border-radius:4px;font-family:"DM Mono",monospace;}}
.badge-he{{background:rgba(42,157,143,0.9);color:#fff;}}
.badge-pas{{background:rgba(52,120,180,0.9);color:#fff;}}
.badge-masson{{background:rgba(100,70,160,0.9);color:#fff;}}
.badge-silver{{background:rgba(100,100,90,0.9);color:#fff;}}
.card-sample-badge{{position:absolute;top:10px;right:10px;background:rgba(233,196,106,0.95);color:#633806;font-size:9px;font-weight:700;padding:3px 8px;border-radius:4px;font-family:"DM Mono",monospace;}}
.card-scale{{position:absolute;bottom:10px;left:10px;font-size:9px;font-family:"DM Mono",monospace;color:rgba(255,255,255,0.85);background:rgba(0,0,0,0.45);padding:2px 8px;border-radius:3px;}}
.card-body{{padding:14px 16px;}}
.card-system{{font-size:10px;color:#2A9D8F;font-weight:600;letter-spacing:0.05em;margin-bottom:4px;font-family:"DM Mono",monospace;}}
.card-name-ko{{font-size:15px;font-weight:700;letter-spacing:-0.02em;margin-bottom:2px;}}
.card-name-en{{font-size:11px;color:#9B9490;font-family:"DM Mono",monospace;margin-bottom:10px;}}
.card-meta{{display:flex;align-items:center;justify-content:space-between;}}
.card-stain{{font-size:11px;color:#6B6560;}}
.card-link{{font-size:11px;color:#2A9D8F;font-weight:600;}}
footer{{background:#0F1F3D;padding:28px 52px;display:flex;align-items:center;justify-content:space-between;margin-top:40px;}}
.footer-logo{{font-weight:800;font-size:16px;color:#fff;}}
.footer-copy{{font-size:12px;color:rgba(255,255,255,0.28);}}
.footer-links{{display:flex;gap:24px;}}
.footer-links a{{font-size:12px;color:rgba(255,255,255,0.38);text-decoration:none;}}
</style>
</head>
<body>
<nav>
  <a href="/" style="display:flex;align-items:center;text-decoration:none;">
    <img src="/static/slideatlas_logo.png" alt="SlideAtlas" style="height:32px;width:auto;">
  </a>
  <div class="nav-right">
    <span class="nav-badge">Beta</span>
    <a class="btn-nav" href="/">홈으로</a>
  </div>
</nav>
<div class="page-header">
  <h1 class="page-title">슬라이드 라이브러리</h1>
  <p class="page-desc">고해상도 디지털 WSI 슬라이드 아카이브&nbsp;|&nbsp;{total}개 슬라이드 열람 가능</p>
</div>
<div class="layout">
  <div class="sidebar">
    <div class="filter-group">
      <div class="filter-group-title">계통별 · System</div>
      {system_filters}
    </div>
    <div class="filter-divider"></div>
    <div class="filter-group">
      <div class="filter-group-title">염색법 · Stain</div>
      {stain_filters}
    </div>
  </div>
  <div class="main">
    <div class="main-top">
      <span class="result-count"><strong>{total}개</strong> 슬라이드</span>
    </div>
    <div class="slides-grid">{cards_html}</div>
  </div>
</div>
<footer>
  <span class="footer-logo">SlideAtlas</span>
  <span class="footer-copy">© 2026 Lami International Co., Ltd.</span>
  <div class="footer-links">
    <a href="mailto:mcmajo@naver.com">문의</a>
    <a href="#">기관 구독</a>
  </div>
</footer>
</body>
</html>'''

@app.route('/api/chat', methods=['POST'])
def api_chat():
    import urllib.request
    import json as json_mod
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        return jsonify({'reply': '서버에 API 키가 설정되지 않았습니다.'}), 500
    data = request.get_json()
    user_msg = data.get('message', '')
    system_prompt = data.get('system', '당신은 병리학 교육 AI 튜터입니다. 한국어로 답변하세요.')
    if not user_msg:
        return jsonify({'reply': '메시지가 없습니다.'}), 400

    # 퀴즈 요청은 JSON 파싱이 필요하므로 스트리밍 없이 처리
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

    # 일반 채팅은 스트리밍 응답
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
def dzi_descriptor(slide_id):
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
    return Response(xml, mimetype='application/xml')

@app.route('/dzi/<slide_id>_files/<int:level>/<int:col>_<int:row>.jpeg')
@app.route('/dzi/<slide_id>_files/<int:level>/<int:col>_<int:row>.jpg')
def dzi_tile(slide_id, level, col, row):
    if slide_id not in SLIDE_CACHE:
        img = Image.new('RGB', (TILE_SIZE, TILE_SIZE), (245, 240, 235))
        buf = io.BytesIO()
        img.save(buf, 'JPEG')
        buf.seek(0)
        return send_file(buf, mimetype='image/jpeg')
    try:
        dz = SLIDE_CACHE[slide_id]["dz"]
        tile = dz.get_tile(level, (col, row))
        buf = io.BytesIO()
        tile.save(buf, format='JPEG', quality=88)
        buf.seek(0)
        return send_file(buf, mimetype='image/jpeg')
    except Exception as e:
        img = Image.new('RGB', (TILE_SIZE, TILE_SIZE), (255, 255, 255))
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
            session['admin_logged_in'] = True
            return redirect('/admin')
        else:
            error = '비밀번호가 올바르지 않습니다.'
    return f'''<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><title>SlideAtlas Admin</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{font-family:sans-serif;background:#0F1F3D;display:flex;align-items:center;justify-content:center;min-height:100vh;}}
.box{{background:#fff;border-radius:12px;padding:48px 40px;width:360px;}}
.logo{{text-align:center;margin-bottom:32px;}}
.ls{{font-size:9px;letter-spacing:0.22em;color:#2A9D8F;}}
.la{{font-size:24px;font-weight:800;color:#0F1F3D;}}
.lad{{font-size:11px;color:#9B9490;letter-spacing:0.08em;margin-top:4px;}}
label{{font-size:13px;font-weight:600;color:#0F1F3D;display:block;margin-bottom:8px;}}
input[type=password]{{width:100%;padding:11px 14px;border:1.5px solid #E5E0D8;border-radius:7px;font-size:14px;outline:none;}}
input[type=password]:focus{{border-color:#2A9D8F;}}
.btn{{width:100%;padding:12px;background:#2A9D8F;color:#fff;border:none;border-radius:7px;font-size:14px;font-weight:600;cursor:pointer;margin-top:16px;}}
.err{{color:#e76f51;font-size:13px;margin-top:12px;text-align:center;}}
</style></head>
<body><div class="box">
<div class="logo"><div class="ls">SLIDE</div><div class="la">ATLAS</div><div class="lad">ADMIN CONSOLE</div></div>
<form method="POST">
<label>관리자 비밀번호</label>
<input type="password" name="password" autofocus>
<button class="btn" type="submit">로그인</button>
{f'<div class="err">{error}</div>' if error else ''}
</form></div></body></html>'''

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
    inst_options = ''.join([f'<option value="{i["code"]}">{i["code"]} · {i["name_ko"]}</option>' for i in institutions])
    subj_options = ''.join([f'<option value="{s["code"]}">{s["code"]} · {s["name_ko"]}</option>' for s in subjects])
    slide_rows = ''
    for s in slides:
        status_badge = '<span class="badge-active">활성</span>' if s.get('active') else '<span class="badge-inactive">비활성</span>'
        slide_rows += f'<tr><td><code>{s["id"]}</code></td><td>{s["title_ko"]}</td><td>{s.get("system","")}</td><td><span class="stain-badge">{s.get("stain","")}</span></td><td>{s.get("institution","")}</td><td>{status_badge}</td><td><button class="btn-edit" onclick="openEdit({json.dumps(s)})">수정</button><button class="btn-del" onclick="deleteSlide(\'{s["id"]}\')">삭제</button></td></tr>'
    return f'''<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><title>SlideAtlas Admin</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{font-family:sans-serif;background:#F7F4EF;color:#0F1F3D;}}
nav{{background:#0F1F3D;padding:0 32px;height:54px;display:flex;align-items:center;justify-content:space-between;}}
.logo-atlas{{font-size:18px;font-weight:800;color:#fff;}}
.nav-logout{{color:rgba(255,255,255,0.45);font-size:12px;text-decoration:none;}}
.container{{max-width:1100px;margin:0 auto;padding:32px 24px;}}
.page-header{{display:flex;align-items:center;justify-content:space-between;margin-bottom:28px;}}
.page-title{{font-size:22px;font-weight:800;}}
.btn-add{{background:#2A9D8F;color:#fff;border:none;padding:10px 20px;border-radius:7px;font-size:13px;font-weight:600;cursor:pointer;}}
.card{{background:#fff;border:1px solid #E5E0D8;border-radius:12px;overflow:hidden;}}
.card-header{{padding:18px 24px;border-bottom:1px solid #E5E0D8;display:flex;align-items:center;justify-content:space-between;}}
.card-title{{font-size:14px;font-weight:700;}}
table{{width:100%;border-collapse:collapse;}}
th{{text-align:left;padding:11px 16px;font-size:11px;color:#9B9490;font-weight:600;border-bottom:1px solid #E5E0D8;}}
td{{padding:13px 16px;font-size:13px;border-bottom:1px solid #F0EDE8;vertical-align:middle;}}
tr:last-child td{{border-bottom:none;}}
code{{background:#F0EDE8;padding:2px 7px;border-radius:4px;font-size:12px;}}
.stain-badge{{background:#EBF6F5;color:#0F6E56;font-size:11px;padding:2px 8px;border-radius:12px;font-weight:600;}}
.badge-active{{background:#EBF6F5;color:#0F6E56;font-size:11px;padding:2px 8px;border-radius:12px;font-weight:600;}}
.badge-inactive{{background:#F5F0E8;color:#9B9490;font-size:11px;padding:2px 8px;border-radius:12px;font-weight:600;}}
.btn-edit{{background:#F0EDE8;color:#0F1F3D;border:none;padding:5px 12px;border-radius:5px;font-size:12px;cursor:pointer;font-weight:600;margin-right:4px;}}
.btn-del{{background:#fde8e4;color:#c0392b;border:none;padding:5px 12px;border-radius:5px;font-size:12px;cursor:pointer;font-weight:600;}}
.modal-overlay{{display:none;position:fixed;inset:0;background:rgba(15,31,61,0.6);z-index:1000;align-items:center;justify-content:center;}}
.modal-overlay.open{{display:flex;}}
.modal{{background:#fff;border-radius:12px;width:540px;max-height:85vh;overflow-y:auto;padding:32px;}}
.modal-title{{font-size:18px;font-weight:800;margin-bottom:24px;}}
.form-row{{margin-bottom:16px;}}
.form-row label{{font-size:12px;font-weight:600;display:block;margin-bottom:6px;}}
.form-row input,.form-row select,.form-row textarea{{width:100%;padding:9px 12px;border:1.5px solid #E5E0D8;border-radius:7px;font-size:13px;font-family:sans-serif;outline:none;}}
.form-row input:focus,.form-row select:focus{{border-color:#2A9D8F;}}
.form-grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px;}}
.modal-footer{{display:flex;gap:10px;justify-content:flex-end;margin-top:24px;}}
.btn-cancel{{background:#F0EDE8;color:#0F1F3D;border:none;padding:10px 20px;border-radius:7px;font-size:13px;font-weight:600;cursor:pointer;}}
.btn-save{{background:#2A9D8F;color:#fff;border:none;padding:10px 20px;border-radius:7px;font-size:13px;font-weight:600;cursor:pointer;}}
</style></head>
<body>
<nav><span class="logo-atlas">ATLAS ADMIN</span><a class="nav-logout" href="/admin/logout">로그아웃</a></nav>
<div class="container">
  <div class="page-header">
    <div><div class="page-title">슬라이드 관리</div></div>
    <button class="btn-add" onclick="openAdd()">+ 슬라이드 추가</button>
  </div>
  <div class="card">
    <div class="card-header"><span class="card-title">전체 슬라이드</span><span>{len(slides)} TOTAL</span></div>
    <table>
      <thead><tr><th>ID</th><th>슬라이드명</th><th>계통</th><th>염색</th><th>기관</th><th>상태</th><th>작업</th></tr></thead>
      <tbody>{slide_rows if slide_rows else '<tr><td colspan="7" style="text-align:center;color:#9B9490;padding:32px;">등록된 슬라이드가 없습니다.</td></tr>'}</tbody>
    </table>
  </div>
</div>
<div class="modal-overlay" id="modal">
  <div class="modal">
    <div class="modal-title" id="modal-title">슬라이드 추가</div>
    <input type="hidden" id="edit-id">
    <div class="form-grid">
      <div class="form-row"><label>기관 코드</label><select id="f-institution">{inst_options}</select></div>
      <div class="form-row"><label>과목 코드</label><select id="f-subject">{subj_options}</select></div>
    </div>
    <div class="form-row"><label>슬라이드 ID</label><input type="text" id="f-id" placeholder="예: SA-HST-0002"></div>
    <div class="form-grid">
      <div class="form-row"><label>슬라이드명 (한글)</label><input type="text" id="f-title-ko"></div>
      <div class="form-row"><label>슬라이드명 (영문)</label><input type="text" id="f-title-en"></div>
    </div>
    <div class="form-grid">
      <div class="form-row"><label>계통</label><input type="text" id="f-system"></div>
      <div class="form-row"><label>염색법</label><input type="text" id="f-stain"></div>
    </div>
    <div class="form-row"><label>포맷</label><select id="f-format"><option value="dcm">DCM</option><option value="svs">SVS</option></select></div>
    <div class="form-row"><label>S3 키 (s3_key)</label><input type="text" id="f-s3key" placeholder="예: SA-PATH-0002/SA-PATH-0002.svs"></div>
    <div class="form-row"><label>타일서버</label><select id="f-tileserver"><option value="">Render (기본)</option><option value="ec2">EC2</option></select></div>
    <div class="form-row"><label>DCM 진입 파일</label><input type="text" id="f-entry" placeholder="예: 000001.dcm"></div>
    <div class="form-row"><label>DCM 파일 목록 (쉼표 구분)</label><textarea id="f-files"></textarea></div>
    <div class="form-row"><label>설명</label><textarea id="f-desc"></textarea></div>
    <div class="form-row"><label>상태</label><select id="f-active"><option value="true">활성</option><option value="false">비활성</option></select></div>
    <div class="modal-footer">
      <button class="btn-cancel" onclick="closeModal()">취소</button>
      <button class="btn-save" onclick="saveSlide()">저장</button>
    </div>
  </div>
</div>
<script>
function openAdd() {{
  document.getElementById('modal-title').textContent = '슬라이드 추가';
  document.getElementById('edit-id').value = '';
  ['f-id','f-title-ko','f-title-en','f-system','f-stain','f-s3key','f-entry','f-files','f-desc'].forEach(id => document.getElementById(id).value = '');
  document.getElementById('f-active').value = 'true';
  document.getElementById('f-format').value = 'dcm';
  document.getElementById('f-tileserver').value = '';
  document.getElementById('modal').classList.add('open');
}}
function openEdit(slide) {{
  document.getElementById('modal-title').textContent = '슬라이드 수정';
  document.getElementById('edit-id').value = slide.id;
  document.getElementById('f-id').value = slide.id;
  document.getElementById('f-title-ko').value = slide.title_ko || '';
  document.getElementById('f-title-en').value = slide.title_en || '';
  document.getElementById('f-system').value = slide.system || '';
  document.getElementById('f-stain').value = slide.stain || '';
  document.getElementById('f-format').value = slide.format || 'dcm';
  document.getElementById('f-s3key').value = slide.s3_key || '';
  document.getElementById('f-tileserver').value = slide.tileserver || '';
  document.getElementById('f-entry').value = slide.dcm_entry || '';
  document.getElementById('f-files').value = (slide.dcm_files || []).join(', ');
  document.getElementById('f-desc').value = slide.description || '';
  document.getElementById('f-active').value = slide.active ? 'true' : 'false';
  if(slide.institution) document.getElementById('f-institution').value = slide.institution;
  document.getElementById('modal').classList.add('open');
}}
function closeModal() {{ document.getElementById('modal').classList.remove('open'); }}
async function saveSlide() {{
  const payload = {{
    id: document.getElementById('f-id').value.trim(),
    title_ko: document.getElementById('f-title-ko').value.trim(),
    title_en: document.getElementById('f-title-en').value.trim(),
    system: document.getElementById('f-system').value.trim(),
    stain: document.getElementById('f-stain').value.trim(),
    institution: document.getElementById('f-institution').value,
    category: document.getElementById('f-subject').value.toLowerCase(),
    format: document.getElementById('f-format').value,
    s3_key: document.getElementById('f-s3key').value.trim(),
    tileserver: document.getElementById('f-tileserver').value,
    dcm_entry: document.getElementById('f-entry').value.trim(),
    dcm_files: document.getElementById('f-files').value.split(',').map(s=>s.trim()).filter(Boolean),
    description: document.getElementById('f-desc').value.trim(),
    active: document.getElementById('f-active').value === 'true',
    edit_id: document.getElementById('edit-id').value
  }};
  if(!payload.tileserver) delete payload.tileserver;
  const res = await fetch('/admin/api/slide', {{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(payload)}});
  const result = await res.json();
  if(result.ok) {{ location.reload(); }} else {{ alert('오류: ' + result.error); }}
}}
async function deleteSlide(id) {{
  if(!confirm(id+' 슬라이드를 삭제하시겠습니까?')) return;
  const res = await fetch('/admin/api/slide/'+id, {{method:'DELETE'}});
  const result = await res.json();
  if(result.ok) {{ location.reload(); }} else {{ alert('오류: '+result.error); }}
}}
document.getElementById('modal').addEventListener('click', function(e) {{ if(e.target===this) closeModal(); }});
</script>
</body></html>'''

@app.route('/admin/api/slide', methods=['POST'])
@admin_required
def admin_save_slide():
    try:
        payload = request.get_json()
        data = load_slides()
        slides = data.get('slides', [])
        edit_id = payload.pop('edit_id', None)
        if edit_id:
            for i, s in enumerate(slides):
                if s['id'] == edit_id:
                    slides[i] = payload
                    break
        else:
            if any(s['id'] == payload['id'] for s in slides):
                return jsonify({'ok': False, 'error': '이미 존재하는 ID입니다.'})
            slides.append(payload)
        data['slides'] = slides
        save_slides(data)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/admin/api/slide/<slide_id>', methods=['DELETE'])
@admin_required
def admin_delete_slide(slide_id):
    try:
        data = load_slides()
        data['slides'] = [s for s in data.get('slides', []) if s['id'] != slide_id]
        save_slides(data)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

if __name__ == '__main__':
    print(f"\n✅ SlideAtlas 서버 시작!")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, threaded=True)
