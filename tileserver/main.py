from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
import openslide_bin
import openslide
from openslide import deepzoom
import boto3, io, os, re, time, hmac, hashlib
from PIL import Image

app = FastAPI(title="SlideAtlas TileServer")
BUCKET = "slideatlas-slides"
SLIDES_DIR = "/tmp/slides"
SLIDES_DIR2 = "/home/ubuntu/slides"
CACHE = {}
os.makedirs(SLIDES_DIR, exist_ok=True)
os.makedirs(SLIDES_DIR2, exist_ok=True)

# ── [블로커1] 타일서버 자체 인가 (HMAC 타일토큰 직접 검증) ──
# Flask 의 generate_tile_token 과 동일 시크릿(JWT_SECRET_KEY)·동일 페이로드
#   (user_id:institution_id:slide_id:exp) 로 HMAC-SHA256 서명을 검증한다.
# 포트 8000 에 직접 GET 하더라도 유효 토큰 없이는 타일을 내주지 않는다(Flask 게이트 우회 차단).
# 시크릿은 환경변수에서만 읽고, 미설정 시 fail-closed(모든 요청 거부).
_SLIDE_RE = re.compile(r'^SA-[A-Z]+-\d+$')


def _tile_secret():
    s = os.environ.get("JWT_SECRET_KEY")
    if not s:
        # fail-closed: 시크릿 미설정이면 어떤 토큰도 검증 불가 → 전면 거부.
        raise HTTPException(status_code=503, detail="tileserver secret not configured")
    return s


def _verify_tile_token(token: str, user_id: str, institution_id: str, slide_id: str) -> bool:
    try:
        exp_str, sig = token.split(":", 1)
        exp = int(exp_str)
        if exp < int(time.time()):
            return False
        msg = f"{user_id}:{institution_id}:{slide_id}:{exp}"
        expected = hmac.new(_tile_secret().encode(), msg.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)
    except HTTPException:
        raise
    except Exception:
        return False


def require_token(slide_id: str, t, u, i):
    """slide_id 형식 + HMAC 타일토큰 검증. 토큰에 바인딩된 slide_id 와 경로 slide_id 가
    일치할 때만(서명이 경로 slide_id 로 재계산되므로 불일치 시 서명 실패) 통과."""
    if not slide_id or not _SLIDE_RE.match(slide_id):
        raise HTTPException(status_code=400, detail="invalid slide_id")
    if not t or not _verify_tile_token(t, u or "", i or "", slide_id):
        raise HTTPException(status_code=401, detail="tile token invalid")


def get_slide(slide_id):
    # 방어적 입력 검증(트래버설·이상 slide_id 차단) — 모든 진입점이 거치는 단일 지점.
    if not slide_id or not _SLIDE_RE.match(slide_id):
        raise HTTPException(status_code=400, detail="invalid slide_id")
    if slide_id in CACHE:
        return CACHE[slide_id]

    # 로컬 경로 순서대로 확인
    candidates = [
        f"{SLIDES_DIR}/{slide_id}.svs",
        f"{SLIDES_DIR2}/{slide_id}.svs",
        f"{SLIDES_DIR}/{slide_id}/{slide_id}",
        f"{SLIDES_DIR2}/{slide_id}/{slide_id}",
    ]

    local_path = None
    for c in candidates:
        if os.path.exists(c) and not os.path.isdir(c):
            local_path = c
            break
        elif os.path.isdir(c):
            dcm_files = sorted([f for f in os.listdir(c) if f.endswith('.dcm')])
            if dcm_files:
                local_path = os.path.join(c, dcm_files[0])
                break

    if not local_path:
        s3 = boto3.client('s3', region_name='ap-northeast-2')
        svs_key = f"{slide_id}.svs"
        try:
            s3.head_object(Bucket=BUCKET, Key=svs_key)
            dst = f"{SLIDES_DIR}/{slide_id}.svs"
            print(f"S3 다운로드(SVS): {svs_key}")
            s3.download_file(BUCKET, svs_key, dst)
            local_path = dst
        except:
            resp = s3.list_objects_v2(Bucket=BUCKET, Prefix=f"{slide_id}/")
            objects = resp.get('Contents', [])
            svs_keys = [o['Key'] for o in objects if o['Key'].lower().endswith('.svs')]
            dcm_keys = [o['Key'] for o in objects if o['Key'].lower().endswith('.dcm')]

            if svs_keys:
                local_path = f"{SLIDES_DIR}/{slide_id}.svs"
                s3.download_file(BUCKET, svs_keys[0], local_path)
            elif dcm_keys:
                slide_dir = f"{SLIDES_DIR}/{slide_id}/{slide_id}"
                os.makedirs(slide_dir, exist_ok=True)
                for key in dcm_keys:
                    fname = os.path.basename(key)
                    lf = os.path.join(slide_dir, fname)
                    if not os.path.exists(lf):
                        s3.download_file(BUCKET, key, lf)
                dcm_files = sorted([f for f in os.listdir(slide_dir) if f.endswith('.dcm')])
                local_path = os.path.join(slide_dir, dcm_files[0])
            else:
                raise HTTPException(status_code=404, detail=f"No slide files for {slide_id}")

    slide = openslide.OpenSlide(local_path)
    dz = deepzoom.DeepZoomGenerator(slide, tile_size=254, overlap=1, limit_bounds=True)
    CACHE[slide_id] = {"slide": slide, "dz": dz}
    print(f"로드 완료: {slide_id} {slide.dimensions}")
    return CACHE[slide_id]

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/info/{slide_id}")
def info(slide_id: str, t: str = "", u: str = "", i: str = ""):
    require_token(slide_id, t, u, i)
    c = get_slide(slide_id)
    slide = c["slide"]
    dz = c["dz"]
    return {
        "width": slide.dimensions[0],
        "height": slide.dimensions[1],
        "levels": dz.level_count,
        "mpp_x": slide.properties.get("openslide.mpp-x"),
        "mpp_y": slide.properties.get("openslide.mpp-y"),
        "objective": slide.properties.get("openslide.objective-power"),
        "level_dimensions": dz.level_dimensions
    }

@app.get("/dzi/{slide_id}.dzi")
def dzi(slide_id: str, t: str = "", u: str = "", i: str = ""):
    require_token(slide_id, t, u, i)
    c = get_slide(slide_id)
    dz = c["dz"]
    w, h = dz.level_dimensions[-1]
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<Image xmlns="http://schemas.microsoft.com/deepzoom/2008"
  Format="jpeg" Overlap="1" TileSize="254">
  <Size Width="{w}" Height="{h}"/>
</Image>'''
    return Response(xml, media_type="application/xml")

@app.api_route("/dzi/{path:path}", methods=["GET"])
def tile_catch_all(path: str, t: str = "", u: str = "", i: str = ""):
    # slide_id 그룹을 SA-형식으로 한정 → '..' 등 트래버설이 group(1)에 섞이지 못한다.
    m = re.match(r'^(SA-[A-Z]+-\d+)_files/(\d+)/(\d+)_(\d+)\.(jpeg|jpg)$', path)
    if not m:
        raise HTTPException(status_code=404, detail="Invalid path")
    slide_id, level, col, row = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))
    require_token(slide_id, t, u, i)
    try:
        c = get_slide(slide_id)
        t = c["dz"].get_tile(level, (col, row))
        buf = io.BytesIO()
        t.save(buf, format="JPEG", quality=85)
        buf.seek(0)
        return Response(buf.getvalue(), media_type="image/jpeg")
    except HTTPException:
        raise
    except Exception as e:
        print(f"타일 오류 {path}: {e}")
        img = Image.new("RGB", (256, 256), (255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        buf.seek(0)
        return Response(buf.getvalue(), media_type="image/jpeg")
