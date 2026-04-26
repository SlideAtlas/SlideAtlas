import os
import sys
import threading

from flask import Flask, send_file, Response, request, jsonify
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
    <a class="btn-nav" href="/slides">슬라이드 둘러보기</a>
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
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/openseadragon/4.1.0/openseadragon.min.js"></script>
<style>
@import url('https://cdn.jsdelivr.net/gh/sunn-us/SUIT/fonts/variable/woff2/SUIT-Variable.css');
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{background:#0d1219;font-family:"SUIT Variable","SUIT",sans-serif;overflow:hidden;height:100vh;display:flex;flex-direction:column;}}

/* HEADER */
#header{{background:rgba(15,31,61,0.97);border-bottom:1px solid rgba(255,255,255,0.08);padding:0 20px;height:50px;display:flex;align-items:center;justify-content:space-between;flex-shrink:0;z-index:100;}}
.logo{{display:flex;flex-direction:column;line-height:1;gap:1px;text-decoration:none;}}
.logo-slide{{font-size:7px;letter-spacing:0.22em;color:#2A9D8F;font-family:"DM Mono",monospace;font-weight:500;}}
.logo-atlas{{font-size:18px;font-weight:800;color:#fff;}}
#hdr-center{{font-size:11px;color:rgba(255,255,255,0.4);font-family:"DM Mono",monospace;}}
#hdr-right{{display:flex;align-items:center;gap:8px;}}
.hdr-back{{color:#2A9D8F;font-size:12px;text-decoration:none;border:1px solid rgba(42,157,143,0.3);padding:4px 10px;border-radius:5px;}}
.hdr-btn{{background:transparent;color:rgba(255,255,255,0.45);border:1px solid rgba(255,255,255,0.12);padding:4px 10px;border-radius:5px;font-size:12px;cursor:pointer;font-family:"SUIT Variable",sans-serif;}}

/* MAIN SPLIT */
#main{{display:grid;grid-template-columns:1fr 310px;flex:1;overflow:hidden;}}

/* VIEWER */
#viewer-wrap{{position:relative;overflow:hidden;background:#111824;}}
#viewer{{position:absolute;inset:0;}}

/* toolbar */
#toolbar{{position:absolute;bottom:16px;left:50%;transform:translateX(-50%);background:rgba(15,31,61,0.95);border:1px solid rgba(255,255,255,0.12);border-radius:10px;padding:8px 16px;display:flex;align-items:center;gap:6px;z-index:50;box-shadow:0 8px 32px rgba(0,0,0,0.4);}}
.mb{{background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.15);color:rgba(255,255,255,0.8);padding:5px 12px;border-radius:6px;cursor:pointer;font-size:11px;font-family:"DM Mono",monospace;transition:all 0.15s;}}
.mb:hover{{background:rgba(42,157,143,0.3);border-color:#2A9D8F;color:white;}}
.mb.active{{background:#2A9D8F;border-color:#2A9D8F;color:#fff;}}
#md{{font-family:"DM Mono",monospace;font-size:14px;color:white;min-width:48px;text-align:center;font-weight:500;}}
#scale{{position:absolute;bottom:16px;left:16px;background:rgba(0,0,0,0.6);color:rgba(255,255,255,0.7);padding:5px 12px;border-radius:6px;font-family:"DM Mono",monospace;font-size:11px;border:1px solid rgba(255,255,255,0.08);z-index:50;}}

/* AI PANEL - 밝은 베이지/흰색 테마 */
#ai-panel{{background:#F7F4EF;border-left:1px solid #E5E0D8;display:flex;flex-direction:column;overflow:hidden;}}

.slide-meta{{padding:14px 18px;border-bottom:1px solid #E5E0D8;background:#fff;flex-shrink:0;}}
.meta-title{{font-size:15px;font-weight:800;letter-spacing:-0.02em;color:#0F1F3D;margin-bottom:3px;}}
.meta-sub{{font-size:11px;color:#9B9490;font-family:"DM Mono",monospace;}}
.meta-badges{{display:flex;gap:5px;margin-top:8px;}}
.mbadge{{font-size:10px;font-weight:600;padding:3px 9px;border-radius:4px;font-family:"DM Mono",monospace;}}
.mbadge-he{{background:#EBF6F5;color:#0F6E56;border:1px solid rgba(42,157,143,0.2);}}
.mbadge-sys{{background:#F0EDE8;color:#6B6560;border:1px solid #E5E0D8;}}
.mbadge-mag{{background:#FEF7E6;color:#8B6010;border:1px solid rgba(233,196,106,0.3);}}

/* TABS */
.tabs{{display:flex;border-bottom:1px solid #E5E0D8;background:#fff;flex-shrink:0;}}
.tab{{flex:1;padding:11px 0;text-align:center;font-size:13px;font-weight:600;color:#9B9490;cursor:pointer;border-bottom:2px solid transparent;transition:all 0.2s;}}
.tab.active{{color:#2A9D8F;border-bottom-color:#2A9D8F;}}
.tab:hover:not(.active){{color:#0F1F3D;}}

.tab-content{{flex:1;overflow:hidden;display:none;flex-direction:column;}}
.tab-content.active{{display:flex;}}

/* 탭1: 구조 가이드 */
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

/* 탭2: 질문하기 */
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

/* 탭3: 퀴즈 */
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
    <a href="/" class="logo">
      <span class="logo-slide">SLIDE</span>
      <span class="logo-atlas">ATLAS</span>
    </a>
  </div>
  <span id="hdr-center">소장 · Small Intestine &nbsp;/&nbsp; H&amp;E &nbsp;/&nbsp; <span id="hdr-mag">전체</span></span>
  <div id="hdr-right">
    <button class="hdr-btn" id="ai-toggle" onclick="togglePanel()">AI 패널 숨기기</button>
  </div>
</div>

<div id="main">
  <!-- 뷰어 -->
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

  <!-- AI 패널 -->
  <div id="ai-panel">
    <div class="slide-meta">
      <div class="meta-title">소장 · Small Intestine</div>
      <div class="meta-sub">SA-HST-0001 · 소화기계 · 3DHISTECH</div>
      <div class="meta-badges">
        <span class="mbadge mbadge-he">H&amp;E</span>
        <span class="mbadge mbadge-sys">소화기계</span>
        <span class="mbadge mbadge-mag" id="mag-badge">전체</span>
      </div>
    </div>

    <div class="tabs">
      <div class="tab active" onclick="switchTab(0)">구조 가이드</div>
      <div class="tab" onclick="switchTab(1)">질문하기</div>
      <div class="tab" onclick="switchTab(2)">퀴즈</div>
    </div>

    <!-- 탭1: 구조 가이드 -->
    <div class="tab-content active" id="tab0">
      <div class="guide-scroll" id="guide-content">
        <div class="guide-mag-header">
          <div class="guide-mag-dot"></div>
          <span class="guide-mag-label" id="guide-mag-label">전체 배율 · 슬라이드 개요</span>
        </div>
        <div class="ai-bubble">
          <div class="ai-bubble-header">
            <div class="ai-icon"><svg viewBox="0 0 24 24"><path d="M12 2a10 10 0 1 0 10 10"/><path d="M12 6v6l4 2"/></svg></div>
            <span class="ai-label">ATLAS AI</span>
          </div>
          <p class="ai-text" id="guide-main-text">전체 슬라이드를 보고 있습니다. 소장(small intestine)의 단면으로, 중앙의 내강(lumen)을 향해 <strong>융모(villus)</strong>가 돌출된 구조가 특징적입니다. 배율을 높여보세요.</p>
        </div>
        <div class="structure-list" id="structure-list">
          <div class="struct-item">
            <div class="struct-dot"></div>
            <div class="struct-text"><strong>점막층 (Mucosa)</strong> — 융모와 장샘이 위치하는 최내층.</div>
          </div>
          <div class="struct-item">
            <div class="struct-dot" style="background:#E9C46A;"></div>
            <div class="struct-text"><strong>점막하층 (Submucosa)</strong> — 결합조직, 혈관, 신경총.</div>
          </div>
          <div class="struct-item">
            <div class="struct-dot" style="background:rgba(255,255,255,0.3);"></div>
            <div class="struct-text"><strong>근육층 (Muscularis)</strong> — 내윤상근 + 외종주근.</div>
          </div>
        </div>
        <div class="observe-box">
          <div class="observe-label">OBSERVE</div>
          <p class="observe-text" id="observe-text">H&amp;E 염색에서 핵은 <strong style="color:#6B4FA0;">진한 보라색</strong>, 세포질과 기저막은 <strong style="color:#C2607A;">분홍색</strong>으로 관찰됩니다. 10× 이상으로 확대하면 융모 구조가 선명하게 보입니다.</p>
        </div>
      </div>
    </div>

    <!-- 탭2: 질문하기 -->
    <div class="tab-content" id="tab1">
      <div class="chat-scroll" id="chat-messages">
        <div class="msg-ai">
          <div class="msg-ai-icon"><svg viewBox="0 0 24 24"><path d="M12 2a10 10 0 1 0 10 10"/><path d="M12 6v6l4 2"/></svg></div>
          <div class="msg-ai-bubble">소장 H&amp;E 슬라이드에 대해 무엇이든 질문하세요. 현재 배율 기준으로 답변드립니다.</div>
        </div>
      </div>
      <div class="chat-input-area">
        <div class="ctx-tag">
          <div class="ctx-dot"></div>
          <span id="ctx-label">소장 H&amp;E · 전체 배율 컨텍스트 포함</span>
        </div>
        <div class="chat-input-row">
          <input class="chat-input" id="chat-input" placeholder="이 구조에 대해 질문하세요..." onkeydown="if(event.key==='Enter')sendChat()"/>
          <button class="chat-send" onclick="sendChat()"><svg viewBox="0 0 24 24"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg></button>
        </div>
      </div>
    </div>

    <!-- 탭3: 퀴즈 -->
    <div class="tab-content" id="tab2">
      <div class="quiz-scroll">
        <div id="quiz-start-view">
          <div style="text-align:center;padding-top:16px;">
            <div class="quiz-icon-wrap"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg></div>
            <div style="font-size:14px;font-weight:700;color:#fff;margin-bottom:6px;">소장 H&amp;E 퀴즈</div>
            <div style="font-size:12px;color:rgba(255,255,255,0.38);line-height:1.6;word-break:keep-all;">이 슬라이드를 기반으로 조직학 수준 퀴즈 3문제를 생성합니다.</div>
          </div>
          <div class="quiz-stats">
            <div class="quiz-stat"><div class="quiz-stat-num" style="color:#E9C46A;">3</div><div class="quiz-stat-lbl">문제</div></div>
            <div class="quiz-stat"><div class="quiz-stat-num" style="color:#2A9D8F;">H&E</div><div class="quiz-stat-lbl">유형</div></div>
            <div class="quiz-stat"><div class="quiz-stat-num" style="color:rgba(255,255,255,0.6);">★★</div><div class="quiz-stat-lbl">난이도</div></div>
          </div>
          <button class="quiz-start-btn" onclick="startQuiz()">퀴즈 시작 →</button>
        </div>
        <div id="quiz-play-view" style="display:none;">
          <div class="quiz-progress">
            <span class="qprog-label" id="q-num">1 / 3</span>
            <div class="qprog-bar"><div class="qprog-fill" id="q-prog" style="width:33%;"></div></div>
            <span class="qprog-label">소화기계</span>
          </div>
          <div class="quiz-q" id="q-text"></div>
          <div class="quiz-options" id="q-opts"></div>
          <div class="quiz-explanation" id="q-exp"></div>
          <button class="quiz-next-btn" id="q-next" onclick="nextQuestion()">다음 문제 →</button>
        </div>
        <div id="quiz-result-view" style="display:none;text-align:center;padding-top:24px;">
          <div style="font-size:32px;font-weight:800;color:#E9C46A;margin-bottom:8px;" id="result-score"></div>
          <div style="font-size:14px;color:rgba(255,255,255,0.6);margin-bottom:20px;">문제를 맞혔습니다</div>
          <button class="quiz-start-btn" onclick="resetQuiz()">다시 풀기</button>
        </div>
      </div>
    </div>
  </div>
</div>

<script>
// ── 퀴즈 데이터 ──
var QUIZ = [
  {{
    q: "소장 H&E 슬라이드에서 배상세포(Goblet cell)를 구별하는 가장 중요한 특징은?",
    opts: ["진한 보라색 핵을 가진다", "밝고 투명한 세포질 (점액 미염색)", "세포 크기가 현저히 크다", "기저막에 붙어있지 않다"],
    ans: 1,
    exp: "배상세포는 점액을 분비하며 H&E에서 점액이 염색되지 않아 세포질이 밝고 투명하게 보입니다."
  }},
  {{
    q: "소장 융모(Villus)의 주요 기능은?",
    opts: ["소화효소 분비", "흡수 면적 증가", "점액층 형성", "연동운동 조절"],
    ans: 1,
    exp: "융모는 소장 점막이 손가락 모양으로 돌출된 구조로, 표면적을 크게 늘려 영양소 흡수 효율을 높입니다."
  }},
  {{
    q: "H&E 염색에서 핵이 진한 보라색으로 보이는 이유는?",
    opts: ["헤마톡실린이 DNA와 결합하기 때문", "에오신이 핵에 침착하기 때문", "핵의 지질 성분 때문", "산성 단백질 때문"],
    ans: 0,
    exp: "헤마톡실린은 염기성 색소로 음전하를 띤 핵산(DNA, RNA)과 결합하여 핵을 청자색으로 염색합니다."
  }}
];
var qIdx = 0, score = 0;

// ── 구조 가이드 데이터 ──
var GUIDE = {{
  low: {{
    label: "전체 배율 · 슬라이드 개요",
    main: "전체 슬라이드를 보고 있습니다. 소장(small intestine)의 단면으로, 중앙의 내강(lumen)을 향해 <strong>융모(villus)</strong>가 돌출된 구조가 특징적입니다. 배율을 높여보세요.",
    structs: [
      {{dot:"#2A9D8F", name:"점막층 (Mucosa)", desc:"융모와 장샘이 위치하는 최내층."}},
      {{dot:"#E9C46A", name:"점막하층 (Submucosa)", desc:"결합조직, 혈관, 신경총."}},
      {{dot:"rgba(255,255,255,0.3)", name:"근육층 (Muscularis)", desc:"내윤상근 + 외종주근."}}
    ],
    observe: "H&E 염색에서 핵은 <strong style='color:#b4a0e8;'>진한 보라색</strong>, 세포질과 기저막은 <strong style='color:#f0b8c8;'>분홍색</strong>으로 관찰됩니다. 10× 이상으로 확대하면 융모 구조가 선명하게 보입니다."
  }},
  mid: {{
    label: "10× 배율 · 융모 구조 분석",
    main: "10× 배율에서 소장의 <strong>융모(Villus) 구조</strong>가 선명하게 보입니다. 손가락 모양으로 돌출된 구조물이 소장의 표면적을 극대화합니다.",
    structs: [
      {{dot:"#2A9D8F", name:"융모 (Villus)", desc:"점막 상피가 돌출된 구조. 흡수 면적 약 10배 증가."}},
      {{dot:"#E9C46A", name:"배상세포 (Goblet cell)", desc:"점액 분비세포. H&E에서 밝은 투명한 세포질."}},
      {{dot:"rgba(255,255,255,0.3)", name:"장샘 (Crypt of Lieberkühn)", desc:"융모 사이 오목한 부분. 세포 재생 담당."}}
    ],
    observe: "융모 표면의 단층 원주상피세포가 규칙적으로 배열되어 있습니다. 세포 사이 <strong style='color:#E9C46A;'>배상세포</strong>가 밝게 보입니다."
  }},
  high: {{
    label: "40× 배율 · 세포 수준 관찰",
    main: "40× 고배율에서 <strong>단층 원주상피세포</strong>의 핵과 미세융모(brush border)를 확인할 수 있습니다.",
    structs: [
      {{dot:"#2A9D8F", name:"미세융모 (Microvilli)", desc:"세포 정단면의 솔경계. 흡수 면적 추가 증가."}},
      {{dot:"#E9C46A", name:"상피세포 핵", desc:"기저부에 위치. H&E에서 진한 보라색 타원형."}},
      {{dot:"rgba(255,255,255,0.3)", name:"고유층 (Lamina propria)", desc:"융모 중심부. 모세혈관과 유미관 포함."}}
    ],
    observe: "세포 정단면의 <strong style='color:#2A9D8F;'>솔경계(brush border)</strong>가 희미한 분홍색 선으로 보입니다. 핵은 기저부에 규칙적으로 배열됩니다."
  }}
}};

// ── OpenSeadragon ──
var osd = OpenSeadragon({{
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
  navigatorHeight: 100,
  navigatorWidth: 140,
  defaultZoomLevel: 0,
}});

var lastMagLevel = '';
osd.addHandler('zoom', updViewer);
osd.addHandler('open', function() {{ osd.viewport.goHome(true); setTimeout(updViewer, 400); }});

function updViewer() {{
  try {{
    var z = osd.viewport.getZoom(true);
    var mag = z * 40;
    var magText = mag >= 1 ? (Math.round(mag*10)/10)+'×' : mag.toFixed(3)+'×';
    document.getElementById('md').textContent = magText;
    document.getElementById('hdr-mag').textContent = magText;
    document.getElementById('mag-badge').textContent = magText;
    document.getElementById('ctx-label').textContent = '소장 H&E · ' + magText + ' 배율 컨텍스트 포함';

    var vw = osd.viewport.getBounds().width;
    var umW = vw * {W} * 0.121;
    var sc = Math.round(umW / 5);
    document.getElementById('scale').textContent =
      sc >= 1000000 ? (sc/1000000).toFixed(1)+' m' :
      sc >= 1000 ? (sc/1000).toFixed(2)+' mm' : sc+' μm';

    // 구조 가이드 자동 업데이트
    var level = mag < 2 ? 'low' : mag < 15 ? 'mid' : 'high';
    if(level !== lastMagLevel) {{ lastMagLevel = level; updateGuide(level); }}
  }} catch(e) {{}}
}}

function updateGuide(level) {{
  var g = GUIDE[level];
  document.getElementById('guide-mag-label').textContent = g.label;
  document.getElementById('guide-main-text').innerHTML = g.main;
  document.getElementById('observe-text').innerHTML = g.observe;
  var sl = document.getElementById('structure-list');
  sl.innerHTML = g.structs.map(function(s) {{
    return '<div class="struct-item"><div class="struct-dot" style="background:'+s.dot+';"></div><div class="struct-text"><strong>'+s.name+'</strong> — '+s.desc+'</div></div>';
  }}).join('');
}}

function fit() {{ osd.viewport.goHome(false); setTimeout(updViewer,200); }}
function zi() {{ osd.viewport.zoomBy(1/1.8); setTimeout(updViewer,100); }}
function zo() {{ osd.viewport.zoomBy(1.8); setTimeout(updViewer,100); }}
function sm(m) {{ osd.viewport.zoomTo(m/40); setTimeout(updViewer,100); }}

// ── 탭 전환 ──
function switchTab(idx) {{
  document.querySelectorAll('.tab').forEach(function(t,i){{ t.classList.toggle('active', i===idx); }});
  document.querySelectorAll('.tab-content').forEach(function(c,i){{ c.classList.toggle('active', i===idx); }});
}}

// ── AI 패널 토글 ──
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

// ── 채팅 ──
function sendChat() {{
  var input = document.getElementById('chat-input');
  var msg = input.value.trim();
  if(!msg) return;
  input.value = '';

  var z = osd.viewport.getZoom(true);
  var mag = (z * 40);
  var magText = mag >= 1 ? Math.round(mag*10)/10 + '×' : mag.toFixed(3) + '×';

  var msgs = document.getElementById('chat-messages');
  msgs.innerHTML += '<div class="msg-user"><div class="msg-user-bubble">'+escHtml(msg)+'</div></div>';

  var typingId = 'typing-' + Date.now();
  msgs.innerHTML += '<div class="msg-ai" id="'+typingId+'"><div class="msg-ai-icon"><svg viewBox="0 0 24 24"><path d="M12 2a10 10 0 1 0 10 10"/><path d="M12 6v6l4 2"/></svg></div><div class="msg-ai-bubble"><div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div></div></div>';
  msgs.scrollTop = msgs.scrollHeight;

  var SLIDE_INFO = "Small Intestine H&E slide, 3DHISTECH scanner, current magnification: " + magText;
  var SYSTEM = "You are SlideAtlas AI tutor. Current slide: " + SLIDE_INFO + ". Please answer in Korean, as a histology education expert. Keep answers to 3-5 sentences.";

  fetch("/api/chat", {{
    method: "POST",
    headers: {{"Content-Type": "application/json"}},
    body: JSON.stringify({{
      message: msg,
      system: SYSTEM
    }})
  }})
  .then(function(r){{ return r.json(); }})
  .then(function(data) {{
    var reply = data.reply || "응답을 받지 못했습니다.";
    var el = document.getElementById(typingId);
    if(el) el.querySelector('.msg-ai-bubble').textContent = reply;
    msgs.scrollTop = msgs.scrollHeight;
  }})
  .catch(function() {{
    var el = document.getElementById(typingId);
    if(el) el.querySelector('.msg-ai-bubble').textContent = "연결 오류가 발생했습니다. 잠시 후 다시 시도해주세요.";
  }});
}}

function escHtml(s) {{
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}}

// ── 퀴즈 ──
function startQuiz() {{
  qIdx = 0; score = 0;
  document.getElementById('quiz-start-view').style.display = 'none';
  document.getElementById('quiz-result-view').style.display = 'none';
  document.getElementById('quiz-play-view').style.display = 'block';
  renderQuestion();
}}

function renderQuestion() {{
  var q = QUIZ[qIdx];
  document.getElementById('q-num').textContent = (qIdx+1) + ' / ' + QUIZ.length;
  document.getElementById('q-prog').style.width = ((qIdx+1)/QUIZ.length*100) + '%';
  document.getElementById('q-text').textContent = q.q;
  document.getElementById('q-exp').style.display = 'none';
  document.getElementById('q-exp').textContent = q.exp;
  document.getElementById('q-next').style.display = 'none';
  var opts = document.getElementById('q-opts');
  var letters = ['A','B','C','D'];
  opts.innerHTML = q.opts.map(function(o,i) {{
    return '<div class="quiz-opt" onclick="answerQ(this,'+i+')"><span class="opt-num">'+letters[i]+'</span>'+escHtml(o)+'</div>';
  }}).join('');
}}

function answerQ(el, idx) {{
  var q = QUIZ[qIdx];
  document.querySelectorAll('.quiz-opt').forEach(function(o){{ o.onclick=null; }});
  if(idx === q.ans) {{
    el.classList.add('correct');
    score++;
  }} else {{
    el.classList.add('wrong');
    document.querySelectorAll('.quiz-opt')[q.ans].classList.add('correct');
  }}
  document.getElementById('q-exp').style.display = 'block';
  document.getElementById('q-next').style.display = 'block';
  document.getElementById('q-next').textContent = qIdx < QUIZ.length-1 ? '다음 문제 →' : '결과 보기 →';
}}

function nextQuestion() {{
  qIdx++;
  if(qIdx >= QUIZ.length) {{
    document.getElementById('quiz-play-view').style.display = 'none';
    document.getElementById('quiz-result-view').style.display = 'block';
    document.getElementById('result-score').textContent = score + ' / ' + QUIZ.length;
  }} else {{ renderQuestion(); }}
}}

function resetQuiz() {{
  document.getElementById('quiz-result-view').style.display = 'none';
  document.getElementById('quiz-start-view').style.display = 'block';
}}
</script>
</body>
</html>'''

@app.route('/slides')
def slides():
    return '''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SlideAtlas — 슬라이드 목록</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
@import url('https://cdn.jsdelivr.net/gh/sunn-us/SUIT/fonts/variable/woff2/SUIT-Variable.css');
*{margin:0;padding:0;box-sizing:border-box;}
body{font-family:"SUIT Variable","SUIT",sans-serif;background:#F7F4EF;color:#0F1F3D;min-height:100vh;}
nav{background:#0F1F3D;padding:0 40px;height:58px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100;}
.logo{display:flex;flex-direction:column;line-height:1;gap:1px;text-decoration:none;}
.logo-slide{font-size:8px;font-weight:500;letter-spacing:0.22em;color:#2A9D8F;text-transform:uppercase;font-family:"DM Mono",monospace;}
.logo-atlas{font-size:20px;font-weight:800;color:#fff;letter-spacing:0.04em;}
.nav-right{display:flex;gap:10px;align-items:center;}
.nav-badge{font-size:11px;color:#2A9D8F;border:1px solid rgba(42,157,143,0.3);padding:4px 12px;border-radius:20px;font-weight:500;}
.btn-nav{background:#2A9D8F;color:#fff;border:none;padding:7px 18px;border-radius:6px;font-size:13px;font-family:"SUIT Variable",sans-serif;font-weight:600;cursor:pointer;text-decoration:none;display:inline-block;}
.breadcrumb{padding:16px 40px;display:flex;align-items:center;gap:8px;border-bottom:1px solid #E5E0D8;background:#fff;}
.bc-item{font-size:13px;color:#9B9490;text-decoration:none;}
.bc-item:hover{color:#0F1F3D;}
.bc-sep{font-size:13px;color:#C8C4BC;}
.bc-current{font-size:13px;color:#0F1F3D;font-weight:600;}
.page-header{padding:28px 40px 20px;background:#fff;border-bottom:1px solid #E5E0D8;}
.page-header-top{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:16px;}
.page-title{font-size:26px;font-weight:800;letter-spacing:-0.03em;margin-bottom:4px;}
.page-desc{font-size:14px;color:#6B6560;font-weight:300;}
.search-bar{display:flex;align-items:center;gap:10px;background:#F7F4EF;border:1px solid #E5E0D8;border-radius:8px;padding:10px 16px;width:340px;}
.search-icon{width:16px;height:16px;stroke:#9B9490;fill:none;stroke-width:2;flex-shrink:0;}
.search-input{border:none;background:transparent;font-size:14px;color:#0F1F3D;font-family:"SUIT Variable",sans-serif;outline:none;width:100%;}
.search-input::placeholder{color:#9B9490;}
.search-kbd{font-size:10px;color:#C8C4BC;font-family:"DM Mono",monospace;border:1px solid #E5E0D8;padding:2px 6px;border-radius:4px;flex-shrink:0;}
.filter-tags{display:flex;gap:8px;flex-wrap:wrap;}
.ftag{display:inline-flex;align-items:center;gap:5px;background:#EBF6F5;color:#0F6E56;font-size:12px;font-weight:600;padding:5px 12px;border-radius:20px;cursor:pointer;}
.ftag-x{color:#2A9D8F;}
.ftag-clear{background:transparent;border:1px solid #E5E0D8;color:#9B9490;font-size:12px;padding:5px 12px;border-radius:20px;cursor:pointer;}
.layout{display:grid;grid-template-columns:220px 1fr;align-items:start;}
.sidebar{padding:24px 20px;border-right:1px solid #E5E0D8;background:#fff;position:sticky;top:58px;min-height:calc(100vh - 58px);}
.filter-group{margin-bottom:22px;}
.filter-group-title{font-size:10px;font-weight:700;letter-spacing:0.1em;color:#9B9490;text-transform:uppercase;margin-bottom:10px;font-family:"DM Mono",monospace;}
.filter-item{display:flex;align-items:center;justify-content:space-between;padding:5px 0;cursor:pointer;}
.filter-item-left{display:flex;align-items:center;gap:8px;}
.filter-cb{width:14px;height:14px;border:1.5px solid #C8C4BC;border-radius:3px;flex-shrink:0;}
.filter-cb.checked{background:#2A9D8F;border-color:#2A9D8F;}
.filter-label{font-size:13px;color:#0F1F3D;}
.filter-count{font-size:11px;color:#9B9490;font-family:"DM Mono",monospace;}
.filter-divider{height:1px;background:#E5E0D8;margin:14px 0;}
.main{padding:24px 32px;}
.main-top{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;}
.result-count{font-size:13px;color:#6B6560;}
.result-count strong{color:#0F1F3D;font-weight:700;}
.sort-select{background:#fff;border:1px solid #E5E0D8;border-radius:6px;padding:7px 12px;font-size:13px;font-family:"SUIT Variable",sans-serif;color:#0F1F3D;cursor:pointer;outline:none;}
.slides-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;}
.slide-card{background:#fff;border:1px solid #E5E0D8;border-radius:12px;overflow:hidden;cursor:pointer;transition:all 0.2s;text-decoration:none;display:block;color:inherit;position:relative;}
.slide-card:hover{border-color:#2A9D8F;transform:translateY(-2px);box-shadow:0 8px 24px rgba(15,31,61,0.08);}
.slide-card.locked{opacity:0.55;cursor:default;pointer-events:none;}
.card-thumb{height:140px;position:relative;overflow:hidden;}
.thumb-he{background:radial-gradient(ellipse 80px 60px at 40% 45%,rgba(220,150,170,0.7) 0%,transparent 65%),radial-gradient(ellipse 50px 50px at 65% 40%,rgba(200,120,145,0.65) 0%,transparent 60%),radial-gradient(ellipse 40px 45px at 48% 68%,rgba(210,135,160,0.55) 0%,transparent 55%),linear-gradient(135deg,#f5e8ee,#f0dce6,#e8d0dc);}
.thumb-pas{background:radial-gradient(ellipse 70px 50px at 35% 50%,rgba(150,200,220,0.6) 0%,transparent 60%),radial-gradient(ellipse 40px 40px at 68% 38%,rgba(130,180,210,0.55) 0%,transparent 55%),linear-gradient(135deg,#e8f4f8,#d4eaf4,#c8e0ee);}
.thumb-masson{background:radial-gradient(ellipse 60px 50px at 42% 48%,rgba(100,160,220,0.6) 0%,transparent 60%),radial-gradient(ellipse 50px 40px at 65% 42%,rgba(220,80,80,0.4) 0%,transparent 55%),linear-gradient(135deg,#e8eef8,#d8e4f4,#e8daea);}
.thumb-silver{background:radial-gradient(ellipse 60px 45px at 40% 50%,rgba(180,180,160,0.7) 0%,transparent 60%),linear-gradient(135deg,#f2f0ea,#e8e6de,#dedad0);}
.card-thumb-badge{position:absolute;top:10px;left:10px;font-size:9px;font-weight:600;padding:3px 8px;border-radius:4px;font-family:"DM Mono",monospace;letter-spacing:0.06em;}
.badge-he{background:rgba(42,157,143,0.9);color:#fff;}
.badge-pas{background:rgba(52,120,180,0.9);color:#fff;}
.badge-masson{background:rgba(100,70,160,0.9);color:#fff;}
.badge-silver{background:rgba(100,100,90,0.9);color:#fff;}
.card-sample-badge{position:absolute;top:10px;right:10px;background:rgba(233,196,106,0.95);color:#633806;font-size:9px;font-weight:700;padding:3px 8px;border-radius:4px;font-family:"DM Mono",monospace;}
.card-coming-badge{position:absolute;top:10px;right:10px;background:rgba(0,0,0,0.3);color:rgba(255,255,255,0.65);font-size:9px;font-weight:600;padding:3px 8px;border-radius:4px;font-family:"DM Mono",monospace;}
.card-scale{position:absolute;bottom:10px;left:10px;font-size:9px;font-family:"DM Mono",monospace;color:rgba(255,255,255,0.85);background:rgba(0,0,0,0.45);padding:2px 8px;border-radius:3px;}
.card-body{padding:14px 16px;}
.card-system{font-size:10px;color:#2A9D8F;font-weight:600;letter-spacing:0.05em;margin-bottom:4px;font-family:"DM Mono",monospace;}
.card-name-ko{font-size:15px;font-weight:700;letter-spacing:-0.02em;margin-bottom:2px;}
.card-name-en{font-size:11px;color:#9B9490;font-family:"DM Mono",monospace;margin-bottom:10px;}
.card-meta{display:flex;align-items:center;justify-content:space-between;}
.card-stain{font-size:11px;color:#6B6560;}
.card-link{font-size:11px;color:#2A9D8F;font-weight:600;}
.card-coming{font-size:11px;color:#9B9490;}
footer{background:#0F1F3D;padding:28px 52px;display:flex;align-items:center;justify-content:space-between;margin-top:40px;}
.footer-logo{font-weight:800;font-size:16px;color:#fff;}
.footer-copy{font-size:12px;color:rgba(255,255,255,0.28);}
.footer-links{display:flex;gap:24px;}
.footer-links a{font-size:12px;color:rgba(255,255,255,0.38);text-decoration:none;}
</style>
</head>
<body>

<nav>
  <a class="logo" href="/">
    <span class="logo-slide">SLIDE</span>
    <span class="logo-atlas">ATLAS</span>
  </a>
  <div class="nav-right">
    <span class="nav-badge">Beta</span>
    <a class="btn-nav" href="/">홈으로</a>
  </div>
</nav>

<div class="breadcrumb">
  <a class="bc-item" href="/">홈</a>
  <span class="bc-sep">/</span>
  <a class="bc-item" href="/slides">조직학</a>
  <span class="bc-sep">/</span>
  <span class="bc-current">슬라이드 목록</span>
</div>

<div class="page-header">
  <div class="page-header-top">
    <div>
      <h1 class="page-title">조직학 · Histology</h1>
      <p class="page-desc">정상 조직의 미시적 구조를 고해상도 디지털 슬라이드로 관찰합니다.&nbsp;|&nbsp;준비 중 포함 6개 슬라이드</p>
    </div>
    <div class="search-bar">
      <svg class="search-icon" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
      <input class="search-input" placeholder="조직명 · 염색법 · 장기 검색" />
      <span class="search-kbd">⌘K</span>
    </div>
  </div>
  <div class="filter-tags">
    <div class="ftag">소화기계 <span class="ftag-x">×</span></div>
    <div class="ftag">H&amp;E <span class="ftag-x">×</span></div>
    <span class="ftag-clear">필터 초기화</span>
  </div>
</div>

<div class="layout">
  <div class="sidebar">
    <div class="filter-group">
      <div class="filter-group-title">계통별 · System</div>
      <div class="filter-item">
        <div class="filter-item-left"><div class="filter-cb checked"></div><span class="filter-label">소화기계</span></div>
        <span class="filter-count">2</span>
      </div>
      <div class="filter-item">
        <div class="filter-item-left"><div class="filter-cb"></div><span class="filter-label">비뇨기계</span></div>
        <span class="filter-count">1</span>
      </div>
      <div class="filter-item">
        <div class="filter-item-left"><div class="filter-cb"></div><span class="filter-label">순환기계</span></div>
        <span class="filter-count">1</span>
      </div>
      <div class="filter-item">
        <div class="filter-item-left"><div class="filter-cb"></div><span class="filter-label">호흡기계</span></div>
        <span class="filter-count">1</span>
      </div>
      <div class="filter-item">
        <div class="filter-item-left"><div class="filter-cb"></div><span class="filter-label">신경계</span></div>
        <span class="filter-count">1</span>
      </div>
    </div>
    <div class="filter-divider"></div>
    <div class="filter-group">
      <div class="filter-group-title">염색법 · Stain</div>
      <div class="filter-item">
        <div class="filter-item-left"><div class="filter-cb checked"></div><span class="filter-label">H&amp;E</span></div>
        <span class="filter-count">3</span>
      </div>
      <div class="filter-item">
        <div class="filter-item-left"><div class="filter-cb"></div><span class="filter-label">PAS</span></div>
        <span class="filter-count">1</span>
      </div>
      <div class="filter-item">
        <div class="filter-item-left"><div class="filter-cb"></div><span class="filter-label">Masson Trichrome</span></div>
        <span class="filter-count">1</span>
      </div>
      <div class="filter-item">
        <div class="filter-item-left"><div class="filter-cb"></div><span class="filter-label">Silver</span></div>
        <span class="filter-count">1</span>
      </div>
    </div>
    <div class="filter-divider"></div>
    <div class="filter-group">
      <div class="filter-group-title">배율 · Magnification</div>
      <div class="filter-item">
        <div class="filter-item-left"><div class="filter-cb"></div><span class="filter-label">4×</span></div>
        <span class="filter-count">6</span>
      </div>
      <div class="filter-item">
        <div class="filter-item-left"><div class="filter-cb"></div><span class="filter-label">10×</span></div>
        <span class="filter-count">6</span>
      </div>
      <div class="filter-item">
        <div class="filter-item-left"><div class="filter-cb checked"></div><span class="filter-label">40×</span></div>
        <span class="filter-count">6</span>
      </div>
    </div>
  </div>

  <div class="main">
    <div class="main-top">
      <span class="result-count"><strong>6개</strong> 슬라이드 (1개 체험 가능)</span>
      <select class="sort-select">
        <option>최신 등록순</option>
        <option>이름순</option>
        <option>계통별</option>
      </select>
    </div>

    <div class="slides-grid">

      <a class="slide-card" href="/viewer">
        <div class="card-thumb thumb-he">
          <span class="card-thumb-badge badge-he">H&amp;E</span>
          <span class="card-sample-badge">SAMPLE</span>
          <span class="card-scale">100 μm · 40×</span>
        </div>
        <div class="card-body">
          <div class="card-system">소화기계</div>
          <div class="card-name-ko">소장 · 융모 구조</div>
          <div class="card-name-en">Small Intestine, Villi</div>
          <div class="card-meta">
            <span class="card-stain">H&amp;E · 3DHISTECH</span>
            <span class="card-link">체험하기 →</span>
          </div>
        </div>
      </a>

      <div class="slide-card locked">
        <div class="card-thumb thumb-he">
          <span class="card-thumb-badge badge-he">H&amp;E</span>
          <span class="card-coming-badge">COMING SOON</span>
          <span class="card-scale">100 μm</span>
        </div>
        <div class="card-body">
          <div class="card-system">소화기계</div>
          <div class="card-name-ko">간 · 소엽 구조</div>
          <div class="card-name-en">Liver, Lobule</div>
          <div class="card-meta">
            <span class="card-stain">H&amp;E</span>
            <span class="card-coming">준비 중</span>
          </div>
        </div>
      </div>

      <div class="slide-card locked">
        <div class="card-thumb thumb-pas">
          <span class="card-thumb-badge badge-pas">PAS</span>
          <span class="card-coming-badge">COMING SOON</span>
          <span class="card-scale">100 μm</span>
        </div>
        <div class="card-body">
          <div class="card-system">비뇨기계</div>
          <div class="card-name-ko">신장 · 사구체</div>
          <div class="card-name-en">Kidney, Glomerulus</div>
          <div class="card-meta">
            <span class="card-stain">PAS</span>
            <span class="card-coming">준비 중</span>
          </div>
        </div>
      </div>

      <div class="slide-card locked">
        <div class="card-thumb thumb-he">
          <span class="card-thumb-badge badge-he">H&amp;E</span>
          <span class="card-coming-badge">COMING SOON</span>
          <span class="card-scale">100 μm</span>
        </div>
        <div class="card-body">
          <div class="card-system">호흡기계</div>
          <div class="card-name-ko">폐 · 폐포 구조</div>
          <div class="card-name-en">Lung, Alveoli</div>
          <div class="card-meta">
            <span class="card-stain">H&amp;E</span>
            <span class="card-coming">준비 중</span>
          </div>
        </div>
      </div>

      <div class="slide-card locked">
        <div class="card-thumb thumb-masson">
          <span class="card-thumb-badge badge-masson">MASSON</span>
          <span class="card-coming-badge">COMING SOON</span>
          <span class="card-scale">100 μm</span>
        </div>
        <div class="card-body">
          <div class="card-system">순환기계</div>
          <div class="card-name-ko">심장 · 심근섬유</div>
          <div class="card-name-en">Heart, Cardiac Muscle</div>
          <div class="card-meta">
            <span class="card-stain">Masson Trichrome</span>
            <span class="card-coming">준비 중</span>
          </div>
        </div>
      </div>

      <div class="slide-card locked">
        <div class="card-thumb thumb-silver">
          <span class="card-thumb-badge badge-silver">SILVER</span>
          <span class="card-coming-badge">COMING SOON</span>
          <span class="card-scale">100 μm</span>
        </div>
        <div class="card-body">
          <div class="card-system">신경계</div>
          <div class="card-name-ko">대뇌 · 피질 구조</div>
          <div class="card-name-en">Cerebral Cortex</div>
          <div class="card-meta">
            <span class="card-stain">Silver</span>
            <span class="card-coming">준비 중</span>
          </div>
        </div>
      </div>

    </div>
  </div>
</div>

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

# ── Claude API 중계 엔드포인트 ──
@app.route('/api/chat', methods=['POST'])
def api_chat():
    import urllib.request
    import json as json_mod

    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        return jsonify({'reply': '서버에 API 키가 설정되지 않았습니다. 관리자에게 문의하세요.'}), 500

    data = request.get_json()
    user_msg = data.get('message', '')
    system_prompt = data.get('system', '당신은 병리학 교육 AI 튜터입니다. 한국어로 답변하세요.')

    if not user_msg:
        return jsonify({'reply': '메시지가 없습니다.'}), 400

    payload = json_mod.dumps({
        'model': 'claude-sonnet-4-5',
        'max_tokens': 600,
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
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json_mod.loads(resp.read().decode('utf-8'))
            reply = result['content'][0]['text'] if result.get('content') else '응답 없음'
            return jsonify({'reply': reply})
    except Exception as e:
        return jsonify({'reply': f'API 오류: {str(e)}'}), 500

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
