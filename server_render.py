import os
import sys
import threading

from flask import Flask, send_file, Response
from PIL import Image
import io

app = Flask(__name__)

# Google Drive 파일 ID (000005.dcm - 메인 WSI)
DCM_FILE_ID = "1pjtScg1nRuOz2eVUnjYlqD1TE2kna9gT"
DCM_PATH = "/tmp/000005.dcm"

# 다운로드 상태
download_status = {"done": False, "error": None, "progress": 0}
slide = None
dz = None
W, H = 57344, 60416  # 기본값
DZ_LEVELS = 17
TILE_SIZE = 256
OVERLAP = 1

def download_and_init():
    global slide, dz, W, H, DZ_LEVELS, download_status

    try:
        # gdown으로 다운로드
        print("Google Drive에서 DCM 파일 다운로드 중...")
        import gdown
        gdown.download(f"https://drive.google.com/uc?id={DCM_FILE_ID}", DCM_PATH, quiet=False)
        print("다운로드 완료!")

        # OpenSlide 초기화
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

# 백그라운드에서 다운로드 시작
thread = threading.Thread(target=download_and_init)
thread.daemon = True
thread.start()

@app.route('/')
def index():
    if not download_status["done"]:
        if download_status["error"]:
            return f'''<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>SlideAtlas</title>
<style>body{{background:#0d1219;color:white;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}}</style>
</head><body><div style="text-align:center">
<h2 style="color:#e76f51">오류 발생</h2>
<p style="color:rgba(255,255,255,0.5)">{download_status["error"]}</p>
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
.spinner {
  width:40px; height:40px; border:3px solid rgba(255,255,255,0.1);
  border-top-color:#2A9D8F; border-radius:50%;
  animation:spin 1s linear infinite; margin:0 auto 20px;
}
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
  <div class="logo">
    <span class="logo-slide">slide</span>
    <span class="logo-atlas">ATLAS</span>
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
    app.run(debug=False, port=5000, threaded=True)
