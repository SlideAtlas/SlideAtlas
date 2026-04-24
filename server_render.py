import os
import sys
import threading

from flask import Flask, send_file, Response
from PIL import Image
import io

app = Flask(__name__)

DCM_PATH = "/opt/render/project/src/000001.dcm"
download_status = {"done": False, "error": None, "progress": 0}
slide = None
dz = None
W, H = 57344, 60416
DZ_LEVELS = 17
TILE_SIZE = 256
OVERLAP = 1

def download_and_init():
    global slide, dz, W, H, DZ_LEVELS, download_status
    try:
        import openslide
        from openslide import deepzoom
        print("OpenSlide 초기화 중...")
        slide = openslide.OpenSlide(DCM_PATH)
        W, H = slide.dimensions
        dz = deepzoom.DeepZoomGenerator(slide, tile_size=TILE_SIZE, overlap=OVERLAP, limit_bounds=True)
        DZ_LEVELS = dz.level_count
        download_status["done"] = True
        print(f"✅ 준비 완료! {W}x{H}, {DZ_LEVELS}레벨")
    except Exception as e:
        download_status["error"] = str(e)
        print(f"❌ 오류: {e}")

thread = threading.Thread(target=download_and_init)
thread.daemon = True
thread.start()

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
.nav-badge { font-size: 11px; color: #2A9D8F; border: 1px solid rgba(42,157,143,0.3); padding: 4px 12px; border-radius: 20px; letter-spacing: 0.03em; font-weight: 500; }
.btn-nav { background: #2A9D8F; color: #fff; border: none; padding: 7px 18px; border-radius: 6px; font-size: 13px; font-family: "SUIT Variable", sans-serif; font-weight: 600; cursor: pointer; text-decoration: none; display: inline-block; }
.hero { display: grid; grid-template-columns: 1fr 1fr; min-height: 480px; }
.hero-left { background: #0F1F3D; padding: 64px 48px 64px 52px; display: flex; flex-direction: column; justify-content: center; }
.hero-tag { display: inline-flex; align-items: center; gap: 7px; margin-bottom: 28px; }
.hero-dot { width: 7px; height: 7px; border-radius: 50%; background: #2A9D8F; animation: pulse 2s infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
.hero-tag-text { font-size: 10px; letter-spacing: 0.15em; color: rgba(255,255,255,0.45); text-transform: uppercase; font-family: "DM Mono", monospace; }
.hero-title { font-weight: 800; font-size: 46px; line-height: 1.15; color: #fff; margin-bottom: 18px; letter-spacing: -0.03em; word-break: keep-all; }
.hero-title .accent { color: #2A9D8F; }
.hero-desc { font-size: 15px; line-height: 1.7; color: rgba(255,255,255,0.55); margin-bottom: 36px; max-width: 380px; font-weight: 300; word-break: keep-all; }
.hero-cta { display: flex; gap: 12px; align-items: center; }
.btn-primary { background: #2A9D8F; color: #fff; border: none; padding: 13px 26px; border-radius: 7px; font-size: 14px; font-family: "SUIT Variable", sans-serif; font-weight: 600; cursor: pointer; letter-spacing: -0.01em; text-decoration: none; display: inline-block; }
.btn-primary:hover { background: #238b7f; }
.btn-secondary { background: transparent; color: rgba(255,255,255,0.65); border: 1px solid rgba(255,255,255,0.2); padding: 13px 24px; border-radius: 7px; font-size: 14px; font-family: "SUIT Variable", sans-serif; font-weight: 400; cursor: pointer; }
.hero-stats { display: flex; gap: 36px; margin-top: 48px; padding-top: 36px; border-top: 1px solid rgba(255,255,255,0.08); }
.stat-num { font-weight: 700; font-size: 28px; color: #fff; line-height: 1; letter-spacing: -0.02em; }
.stat-label { font-size: 11px; color: rgba(255,255,255,0.38); margin-top: 5px; font-weight: 400; }
.hero-right { background: #111c32; display: flex; flex-direction: column; }
.slide-viewer-mock { flex: 1; position: relative; background: radial-gradient(ellipse at 50% 50%, #1e2f4a 0%, #0d1626 100%); min-height: 320px; overflow: hidden; }
.tissue-bg { position: absolute; inset: 0; background: radial-gradient(ellipse 140px 100px at 38% 42%, rgba(220,150,170,0.55) 0%, transparent 70%), radial-gradient(ellipse 80px 80px at 62% 38%, rgba(200,120,145,0.6) 0%, transparent 65%), radial-gradient(ellipse 60px 70px at 45% 65%, rgba(210,135,160,0.5) 0%, transparent 60%), radial-gradient(ellipse 100px 85px at 72% 60%, rgba(190,110,135,0.5) 0%, transparent 65%), radial-gradient(ellipse 120px 90px at 25% 70%, rgba(215,140,165,0.45) 0%, transparent 60%), linear-gradient(135deg, #f5e8ee 0%, #f0dce6 30%, #e8d0dc 60%, #f2e4ea 100%); opacity: 0.9; }
.viewer-overlay { position: absolute; inset: 0; display: flex; flex-direction: column; justify-content: space-between; padding: 14px; }
.viewer-top { display: flex; align-items: center; justify-content: space-between; }
.viewer-badge { background: rgba(42,157,143,0.9); color: #fff; font-size: 10px; padding: 4px 10px; border-radius: 4px; letter-spacing: 0.08em; font-weight: 600; font-family: "DM Mono", monospace; }
.viewer-info-badge { background: rgba(15,31,61,0.85); color: rgba(255,255,255,0.75); font-size: 9px; padding: 4px 10px; border-radius: 4px; font-family: "DM Mono", monospace; }
.viewer-bottom { display: flex; align-items: flex-end; justify-content: space-between; }
.viewer-meta { background: rgba(15,31,61,0.88); border-radius: 7px; padding: 10px 14px; }
.viewer-meta-title { font-size: 12px; font-weight: 700; color: #fff; margin-bottom: 3px; letter-spacing: -0.01em; }
.viewer-meta-sub { font-size: 10px; color: rgba(255,255,255,0.45); font-family: "DM Mono", monospace; }
.viewer-magnify { display: flex; gap: 4px; }
.mag-btn { background: rgba(15,31,61,0.85); color: rgba(255,255,255,0.65); border: none; width: 32px; height: 26px; border-radius: 4px; font-size: 11px; cursor: pointer; font-family: "DM Mono", monospace; }
.mag-btn.active { background: #2A9D8F; color: #fff; }
.hero-right-info { background: #0a1628; padding: 18px 24px; display: flex; align-items: center; justify-content: space-between; }
.hri-label { font-size: 10px; color: rgba(255,255,255,0.3); letter-spacing: 0.08em; font-family: "DM Mono", monospace; margin-bottom: 3px; }
.hri-value { font-size: 13px; color: rgba(255,255,255,0.8); font-weight: 500; }
.hri-divider { width: 1px; height: 32px; background: rgba(255,255,255,0.08); }
.mvp-notice { margin: 40px 52px 0; background: #fff; border: 1px solid #E5E0D8; border-left: 3px solid #E9C46A; border-radius: 8px; padding: 14px 20px; display: flex; align-items: center; gap: 12px; }
.mvp-dot { width: 7px; height: 7px; border-radius: 50%; background: #E9C46A; flex-shrink: 0; }
.mvp-text { font-size: 13px; color: #6B6560; line-height: 1.5; word-break: keep-all; }
.mvp-text strong { color: #0F1F3D; font-weight: 600; }
.section-discipline { padding: 64px 52px 80px; background: #F7F4EF; }
.section-label { font-size: 10px; letter-spacing: 0.18em; color: #2A9D8F; text-transform: uppercase; margin-bottom: 10px; font-family: "DM Mono", monospace; }
.section-title { font-weight: 800; font-size: 30px; color: #0F1F3D; margin-bottom: 36px; letter-spacing: -0.03em; }
.discipline-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; }
.discipline-card { background: #fff; border: 1px solid #E5E0D8; border-radius: 12px; padding: 28px; cursor: pointer; transition: all 0.2s; position: relative; overflow: hidden; text-decoration: none; display: block; color: inherit; }
.discipline-card:hover { border-color: #2A9D8F; transform: translateY(-2px); box-shadow: 0 8px 24px rgba(15,31,61,0.08); }
.discipline-card:hover .card-arrow { color: #2A9D8F; }
.card-icon { width: 40px; height: 40px; border-radius: 8px; background: #EBF6F5; display: flex; align-items: center; justify-content: center; margin-bottom: 16px; }
.card-icon svg { width: 20px; height: 20px; stroke: #2A9D8F; fill: none; stroke-width: 1.5; }
.card-count { font-size: 11px; color: #2A9D8F; font-weight: 600; letter-spacing: 0.04em; margin-bottom: 5px; font-family: "DM Mono", monospace; }
.card-title-ko { font-size: 20px; font-weight: 700; color: #0F1F3D; margin-bottom: 2px; letter-spacing: -0.02em; }
.card-title-en { font-size: 12px; color: #9B9490; margin-bottom: 14px; font-family: "DM Mono", monospace; }
.card-desc { font-size: 13px; color: #6B6560; line-height: 1.65; word-break: keep-all; }
.card-arrow { position: absolute; bottom: 24px; right: 24px; font-size: 16px; color: #C8C4BC; transition: color 0.2s; }
.card-core-badge { position: absolute; top: 16px; right: 16px; background: #EBF6F5; color: #0F6E56; font-size: 9px; font-weight: 600; padding: 3px 8px; border-radius: 20px; letter-spacing: 0.08em; font-family: "DM Mono", monospace; }
footer { background: #0F1F3D; padding: 28px 52px; display: flex; align-items: center; justify-content: space-between; }
.footer-logo { font-weight: 800; font-size: 16px; color: #fff; letter-spacing: -0.01em; }
.footer-copy { font-size: 12px; color: rgba(255,255,255,0.28); }
.footer-links { display: flex; gap: 24px; }
.footer-links a { font-size: 12px; color: rgba(255,255,255,0.38); text-decoration: none; }
.footer-links a:hover { color: rgba(255,255,255,0.7); }
</style>
</head>
<body>
<nav>
  <div class="logo">
    <span class="logo-slide">SLIDE</span>
    <span class="logo-atlas">ATLAS</span>
  </div>
  <div class="nav-right">
    <span class="nav-badge">Beta · 무료 체험 중</span>
    <a class="btn-nav" href="/viewer">슬라이드 둘러보기</a>
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
      <a class="btn-primary" href="/viewer">슬라이드 체험하기 →</a>
      <button class="btn-secondary">기관 구독 문의</button>
    </div>
    <div class="hero-stats">
      <div><div class="stat-num">1+</div><div class="stat-label">샘플 슬라이드</div></div>
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
    <a class="discipline-card" href="/viewer">
      <div class="card-core-badge">CORE</div>
      <div class="card-icon"><svg viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg></div>
      <div class="card-count">1 SLIDE · SAMPLE</div>
      <div class="card-title-ko">조직학</div>
      <div class="card-title-en">Histology</div>
      <p class="card-desc">정상 조직의 미시적 구조를 고해상도 디지털 슬라이드로 관찰합니다.</p>
      <span class="card-arrow">→</span>
    </a>
    <div class="discipline-card" style="opacity:0.55; cursor:default;">
      <div class="card-icon"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M4.22 4.22l2.12 2.12M17.66 17.66l2.12 2.12M2 12h3M19 12h3M4.22 19.78l2.12-2.12M17.66 6.34l2.12-2.12"/></svg></div>
      <div class="card-count">준비 중</div>
      <div class="card-title-ko">병리학</div>
      <div class="card-title-en">Pathology</div>
      <p class="card-desc">질병에 의한 조직 변화를 관찰하고 진단적 사고를 훈련합니다.</p>
      <span class="card-arrow">→</span>
    </div>
    <div class="discipline-card" style="opacity:0.55; cursor:default;">
      <div class="card-icon"><svg viewBox="0 0 24 24"><path d="M8 3c0 0 1 2 1 5s-2 5-2 8c0 2.21 1.79 4 4 4s4-1.79 4-4c0-3-2-5-2-8s1-5 1-5"/><path d="M5 8c-1 0-2 1-2 2s1 2 2 2M19 8c1 0 2 1 2 2s-1 2-2 2"/></svg></div>
      <div class="card-count">준비 중</div>
      <div class="card-title-ko">기생충학</div>
      <div class="card-title-en">Parasitology</div>
      <p class="card-desc">기생충의 조직학적 특징과 숙주 반응을 고해상도로 학습합니다.</p>
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
    <a href="/viewer">슬라이드 체험</a>
  </div>
</footer>
</body>
</html>'''

# ── 뷰어 (기존 / 라우트에서 /viewer로 이동) ──
@app.route('/viewer')
def viewer():
    if not download_status["done"]:
        if download_status["error"]:
            return f'''<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>SlideAtlas</title>
<style>body{{background:#0d1219;color:white;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}}</style>
</head><body><div style="text-align:center">
<h2 style="color:#e76f51">오류 발생</h2>
<p style="color:rgba(255,255,255,0.5)">{download_status["error"]}</p>
<a href="/" style="color:#2A9D8F;margin-top:16px;display:block;">← 홈으로</a>
</div></body></html>'''

        return '''<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>SlideAtlas — 로딩 중</title>
<meta http-equiv="refresh" content="5">
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { background:#0d1219; color:white; font-family:"Segoe UI",sans-serif;
  display:flex; align-items:center; justify-content:center; height:100vh; }
.logo-slide { font-size:9px; letter-spacing:0.25em; color:#2A9D8F; }
.logo-atlas { font-size:28px; font-weight:700; margin-bottom:32px; }
.spinner { width:40px; height:40px; border:3px solid rgba(255,255,255,0.1);
  border-top-color:#2A9D8F; border-radius:50%;
  animation:spin 1s linear infinite; margin:0 auto 20px; }
@keyframes spin { to { transform:rotate(360deg); } }
p { color:rgba(255,255,255,0.45); font-size:14px; }
small { color:rgba(255,255,255,0.25); font-size:12px; margin-top:8px; display:block; }
</style>
</head>
<body>
<div style="text-align:center">
  <div class="logo-slide">slide</div>
  <div class="logo-atlas">ATLAS</div>
  <div class="spinner"></div>
  <p>슬라이드 데이터 로딩 중...</p>
  <small>처음 접속 시 1~2분 소요됩니다. 페이지가 자동으로 새로고침됩니다.</small>
</div>
</body></html>'''

    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>SlideAtlas — 소장 H&E</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/openseadragon/4.1.0/openseadragon.min.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#0d1219; font-family:"Segoe UI",sans-serif; overflow:hidden; }}
#header {{
  position:fixed; top:0; left:0; right:0; z-index:100;
  background:rgba(15,31,61,0.97); border-bottom:1px solid rgba(255,255,255,0.08);
  padding:0 24px; height:52px;
  display:flex; align-items:center; justify-content:space-between;
}}
.logo {{ display:flex; flex-direction:column; line-height:1; }}
.logo-slide {{ font-size:8px; letter-spacing:0.25em; color:#2A9D8F; }}
.logo-atlas {{ font-size:18px; font-weight:700; color:white; }}
#info {{ font-size:12px; color:rgba(255,255,255,0.45); font-family:monospace; }}
#back {{ color:#2A9D8F; font-size:12px; text-decoration:none; margin-right:16px; }}
#viewer {{ position:fixed; top:52px; left:0; right:0; bottom:0; }}
#meta {{
  position:fixed; top:68px; right:16px;
  background:rgba(15,31,61,0.92); border:1px solid rgba(255,255,255,0.08);
  border-radius:10px; padding:14px 16px; font-size:11px;
  color:rgba(255,255,255,0.6); line-height:1.9; min-width:190px; z-index:50;
}}
.ml {{ color:rgba(255,255,255,0.3); font-size:9px; text-transform:uppercase; letter-spacing:0.1em; }}
.mv {{ color:rgba(255,255,255,0.8); }}
#toolbar {{
  position:fixed; bottom:20px; left:50%; transform:translateX(-50%);
  background:rgba(15,31,61,0.95); border:1px solid rgba(255,255,255,0.12);
  border-radius:12px; padding:10px 20px;
  display:flex; align-items:center; gap:8px; z-index:50;
  box-shadow: 0 8px 32px rgba(0,0,0,0.4);
}}
.mb {{
  background:rgba(255,255,255,0.08); border:1px solid rgba(255,255,255,0.15);
  color:rgba(255,255,255,0.8); padding:6px 14px; border-radius:7px;
  cursor:pointer; font-size:12px; font-family:monospace; transition:all 0.15s;
}}
.mb:hover {{ background:rgba(42,157,143,0.3); border-color:#2A9D8F; color:white; }}
#md {{ font-family:monospace; font-size:15px; color:white; min-width:55px; text-align:center; font-weight:600; }}
#scale {{
  position:fixed; bottom:20px; left:20px;
  background:rgba(0,0,0,0.7); color:white; padding:6px 14px;
  border-radius:8px; font-family:monospace; font-size:12px;
  border:1px solid rgba(255,255,255,0.1); z-index:50;
}}
</style>
</head>
<body>
<div id="header">
  <div style="display:flex;align-items:center;">
    <a href="/" id="back">← 홈</a>
    <div class="logo">
      <span class="logo-slide">slide</span>
      <span class="logo-atlas">ATLAS</span>
    </div>
  </div>
  <div id="info">소장 · Small Intestine, c.s. &nbsp;·&nbsp; H&amp;E &nbsp;·&nbsp; {W:,}×{H:,}px &nbsp;·&nbsp; WSI DICOM · 3DHISTECH</div>
</div>
<div id="viewer"></div>
<div id="meta">
  <div class="ml">조직명</div><div class="mv">소장 · Small Intestine</div>
  <div class="ml">염색법</div><div class="mv">H&amp;E</div>
  <div class="ml">해상도</div><div class="mv">0.121 μm/pixel (40×)</div>
  <div class="ml">전체 크기</div><div class="mv">{W:,} × {H:,} px</div>
  <div class="ml">장비</div><div class="mv">3DHISTECH Pannoramic 1000</div>
</div>
<div id="toolbar">
  <button class="mb" onclick="zi()">−</button>
  <div id="md">전체</div>
  <button class="mb" onclick="zo()">+</button>
  <span style="color:rgba(255,255,255,0.2);font-size:20px">|</span>
  <button class="mb" onclick="fit()">전체</button>
  <button class="mb" onclick="sm(1)">1×</button>
  <button class="mb" onclick="sm(4)">4×</button>
  <button class="mb" onclick="sm(10)">10×</button>
  <button class="mb" onclick="sm(20)">20×</button>
  <button class="mb" onclick="sm(40)">40×</button>
</div>
<div id="scale">— mm</div>
<script>
var viewer = OpenSeadragon({{
  id: "viewer",
  prefixUrl: "https://cdnjs.cloudflare.com/ajax/libs/openseadragon/4.1.0/images/",
  tileSources: "/dzi.dzi",
  showNavigationControl: false,
  animationTime: 0.3,
  blendTime: 0.1,
  constrainDuringPan: false,
  maxZoomPixelRatio: 2,
  minZoomLevel: 0.001,
  visibilityRatio: 0.05,
  showNavigator: true,
  navigatorPosition: "BOTTOM_RIGHT",
  navigatorHeight: 120,
  navigatorWidth: 160,
  defaultZoomLevel: 0,
}});
viewer.addHandler('zoom', upd);
viewer.addHandler('open', function() {{
  viewer.viewport.goHome(true);
  setTimeout(upd, 400);
}});
function upd() {{
  try {{
    var z = viewer.viewport.getZoom(true);
    var mag = z * 40;
    document.getElementById('md').textContent =
      mag >= 1 ? (Math.round(mag*10)/10)+'×' : mag.toFixed(3)+'×';
    var vw = viewer.viewport.getBounds().width;
    var umW = vw * {W} * 0.121;
    var sc = Math.round(umW / 5);
    document.getElementById('scale').textContent =
      sc >= 1000000 ? (sc/1000000).toFixed(1)+' m' :
      sc >= 1000 ? (sc/1000).toFixed(2)+' mm' : sc+' μm';
  }} catch(e) {{}}
}}
function fit() {{ viewer.viewport.goHome(false); setTimeout(upd,200); }}
function zi() {{ viewer.viewport.zoomBy(1/1.8); setTimeout(upd,100); }}
function zo() {{ viewer.viewport.zoomBy(1.8); setTimeout(upd,100); }}
function sm(m) {{ viewer.viewport.zoomTo(m/40); setTimeout(upd,100); }}
</script>
</body>
</html>'''

@app.route('/dzi.dzi')
def dzi_descriptor():
    if not download_status["done"]:
        return Response("Loading...", status=503)
    w, h = dz.level_dimensions[-1]
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<Image xmlns="http://schemas.microsoft.com/deepzoom/2008"
  Format="jpeg" Overlap="{OVERLAP}" TileSize="{TILE_SIZE}">
  <Size Width="{w}" Height="{h}"/>
</Image>'''
    return Response(xml, mimetype='application/xml')

@app.route('/dzi_files/<int:level>/<int:col>_<int:row>.jpeg')
@app.route('/dzi_files/<int:level>/<int:col>_<int:row>.jpg')
def dzi_tile(level, col, row):
    if not download_status["done"]:
        img = Image.new('RGB', (TILE_SIZE, TILE_SIZE), (245, 240, 235))
        buf = io.BytesIO()
        img.save(buf, 'JPEG')
        buf.seek(0)
        return send_file(buf, mimetype='image/jpeg')
    try:
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

if __name__ == '__main__':
    print(f"\n✅ SlideAtlas 서버 시작!")
    print(f"   http://localhost:5000\n")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, threaded=True)
