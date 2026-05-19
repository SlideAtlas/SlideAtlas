from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
import openslide_bin
import openslide
from openslide import deepzoom
import boto3, io, os, re
from PIL import Image

app = FastAPI(title="SlideAtlas TileServer")
BUCKET = "slideatlas-slides"
SLIDES_DIR = "/tmp/slides"
SLIDES_DIR2 = "/home/ubuntu/slides"
CACHE = {}
os.makedirs(SLIDES_DIR, exist_ok=True)
os.makedirs(SLIDES_DIR2, exist_ok=True)

def get_slide(slide_id):
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
def info(slide_id: str):
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
def dzi(slide_id: str):
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
def tile_catch_all(path: str):
    m = re.match(r'^(.+)_files/(\d+)/(\d+)_(\d+)\.(jpeg|jpg)$', path)
    if not m:
        raise HTTPException(status_code=404, detail=f"Invalid path: {path}")
    slide_id, level, col, row = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))
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
