"""
pipeline/conversion_engine.py — ConversionJob → ConversionResult 변환 엔진 (2단계 본체)

★ 이식성 계약(§4-3): 엔진은 **트리거·환경변수·HTTP 컨텍스트·전역 DB 커넥션을 직접 참조하지 않는다.**
  필요한 외부 I/O(원본 다운로드·산출물 업로드)는 storage_adapter 의 추상 인터페이스를 '인자로 주입'받아
  쓴다(의존성 주입). 그래야 HTTP/SQS/Lambda 어디서 호출돼도 동일하게 동작한다.

★ 변환 라이브러리 = libvips(pyvips). 2026-06-12 SVS/Motic 실측으로 확정:
  - 같은 입력에서 libvips 9레벨 완벽 단조감소 피라미드(26초) vs GDAL 3레벨 부실(37초).
  - 입력 피라미드가 깨져 있어도(Motic 레벨 순서 엉킴·openslide level_count=1) libvips 가 표준
    피라미드로 복구함(확인됨).
  - 검증된 변환 명령:
      vips tiffsave IN OUT.tif --tile --tile-width 256 --tile-height 256
           --pyramid --compression jpeg --Q 85 --bigtiff

★ pyvips/openslide 는 **지연 임포트**(함수 안)한다. 이 개발 환경엔 라이브러리가 없어도 모듈 임포트·
  순수 파서(_mpp_from_* / _valid_mpp)·상태머신 단위테스트가 돌아야 하기 때문이다. 실제 이미지 연산은
  EC2(libvips 설치됨)에서 리허설로 검증한다(§18 D35).

§4-2 단계 순서:
  ① extract_meta → ② convert_cog → ③ extract_minimap → ④ extract_thumbnail
  → ⑤ generate_kb_json → ⑥ run_qc → (⑦ update_db 는 storage_adapter 책임)
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from typing import Optional, Dict, Any, Callable, TYPE_CHECKING

from .models import (
    ConversionJob, ConversionResult, ConversionStatus,
    assert_transition, resolve_terminal_status,
)

if TYPE_CHECKING:  # 런타임 임포트 회피(이식성·순환참조 방지)
    from .storage_adapter import SourceReader, ArtifactWriter


# ── 고정 변환 스펙(§4-1) — 엔진 상수. COG 가 반드시 만족해야 하는 값 ──
TILE_SIZE = 256              # 256×256
JPEG_QUALITY = 85           # JPEG Q=85
# §4-1 문서는 '오버뷰 7레벨 고정(2..128)'을 적으나, 실측에서 libvips --pyramid 는 이미지 크기에 따라
# 가변 레벨(9레벨 관측)을 만든다. 따라서 '고정 7'을 강제하지 않고 **실제 생성 레벨 수를 기록**하고
# (overview_levels), QC 는 '피라미드 무결성(단조감소·다중 페이지)'을 검증한다(아래 run_qc 주석 참조).
MPP_MIN, MPP_MAX = 0.1, 1.0          # §4-4 MPP '경고' 범위(계속 진행, 실패 아님)
# MPP 유효성 '채택' 범위(폴백 체인) — 쓰레기 값 채택 방지(0.05~2.0 μm/px).
#   ※ §4-4 경고범위(0.1~1.0)보다 넓다: 경고는 "흔치 않다" 신호일 뿐 채택 자체는 막지 않음.
MPP_ACCEPT_MIN, MPP_ACCEPT_MAX = 0.05, 2.0
MIN_DIMENSION_PX = 5000      # §4-4 최소 해상도


@dataclass
class SlideMeta:
    """extract_meta 산출물. mpp 가 None 이면 종착이 ready_no_mpp 로 강제된다(§4-1)."""
    width: int
    height: int
    overview_levels: int        # 원본에서 읽은 레벨 수(진단용; COG 산출 레벨은 convert_cog 가 별도 셈)
    mpp: Optional[float]        # ★ 추출 실패 시 None — 임의 기본값 금지
    original_format: str


# ─────────────────────────────────────────────────────────────
# 진입점: 순수 변환 (Job → Result)
# ─────────────────────────────────────────────────────────────
def run(job: ConversionJob,
        reader: "SourceReader",
        writer: "ArtifactWriter",
        kb_generator: Optional[Callable[["SlideMeta", ConversionJob], Optional[Dict[str, Any]]]] = None,
        workdir: Optional[str] = None) -> ConversionResult:
    """ConversionJob 하나를 변환해 ConversionResult 를 반환하는 순수 함수.

    reader/writer 는 storage_adapter 가 구현하는 추상 I/O(주입). 엔진은 boto3/DB 를 직접 모른다.
    kb_generator(선택 주입): SlideMeta·Job → kb dict. **주입 안 하면 kb=None**(검수본 보존: persist 가
      None 일 때 기존 kb 를 덮지 않는다 §5-4). Claude API 키를 엔진에 끌어들이지 않으려는 분리(이식성).
    workdir(선택): 임시 산출물 디렉터리. 미지정 시 tempfile.

    단계 중 복구 불가 오류 → ConversionResult.failed(...). MPP 추출 실패 → ready_no_mpp(§4-1).
    상태 전이는 models.assert_transition 으로 검증하며 진행한다(pending→converting→qc_check→종착).
    """
    log: list[str] = []

    def _log(msg: str) -> None:
        log.append(msg)

    # 상태 진행: pending → converting (오전이 시 IllegalTransition)
    status = ConversionStatus.PENDING
    tmp_root = workdir or tempfile.mkdtemp(prefix=f"cog_{job.slide_id}_")

    try:
        assert_transition(status, ConversionStatus.CONVERTING)
        status = ConversionStatus.CONVERTING
        _log(f"converting 시작 slide={job.slide_id} fmt={job.input_format.value}")

        # 원본 가져오기(주입 I/O)
        src_path = reader.fetch_to_local(job.source_bucket, job.source_s3_key)
        _log(f"원본 로컬 확보: {src_path}")

        # ① extract_meta
        meta = extract_meta(src_path, job.input_format.value)
        _log(f"meta: {meta.width}x{meta.height} levels={meta.overview_levels} "
             f"mpp={'(none)' if meta.mpp is None else meta.mpp}")

        # ② convert_cog
        cog_path = os.path.join(tmp_root, f"{job.slide_id}.tif")
        produced_overviews = convert_cog(src_path, cog_path)
        _log(f"COG 생성: overview_levels={produced_overviews}")

        # ③ minimap ④ thumbnail
        minimap_path = os.path.join(tmp_root, f"{job.slide_id}_minimap.png")
        thumb_path = os.path.join(tmp_root, f"{job.slide_id}_thumb.jpg")
        extract_minimap(cog_path, minimap_path)
        extract_thumbnail(cog_path, thumb_path)
        _log("minimap/thumbnail 생성")

        # ⑤ kb 초안(선택 주입; 실패해도 변환은 진행)
        kb = None
        try:
            kb = generate_kb_json(meta, job, kb_generator)
        except Exception as e:  # kb 실패는 치명 아님(§5-4 검수 단계 보완)
            _log(f"kb 생성 실패(무시): {e}")

        # qc_check 단계로 전이 후 ⑥ run_qc
        assert_transition(status, ConversionStatus.QC_CHECK)
        status = ConversionStatus.QC_CHECK
        qc = run_qc(cog_path, meta, produced_overviews)
        if not qc.passed:
            _log(f"QC 실패: {qc.failures}")
            assert_transition(status, ConversionStatus.FAILED)
            return ConversionResult.failed(
                job.slide_id, reason=f"QC 실패: {', '.join(qc.failures)}",
                log="\n".join(log))
        if qc.mpp_out_of_range:
            _log(f"경고: MPP 범위 밖({meta.mpp}) — 계속(§4-4)")

        # 산출물 업로드(주입 I/O) — QC 통과분만 S3 로
        cog_key = writer.put_cog(job.slide_id, cog_path)
        minimap_key = writer.put_minimap(job.slide_id, minimap_path)
        thumb_key = writer.put_thumbnail(job.slide_id, thumb_path)
        _log(f"업로드 완료 cog={cog_key} minimap={minimap_key} thumb={thumb_key}")

        # 종착: mpp 유무로 ready / ready_no_mpp (임의 기본값 절대 없음 §4-1)
        terminal = resolve_terminal_status(meta.mpp)
        assert_transition(status, terminal)
        _log(f"종착 상태: {terminal.value}")

        from datetime import datetime, timezone
        return ConversionResult(
            slide_id=job.slide_id,
            status=terminal,
            mpp=meta.mpp,
            width=meta.width,
            height=meta.height,
            cog_s3_key=cog_key,
            minimap_s3_key=minimap_key,
            thumbnail_s3_key=thumb_key,
            knowledge_base=kb,
            overview_levels=produced_overviews,
            qc_passed_at=datetime.now(timezone.utc).isoformat(),
            log="\n".join(log),
        )

    except Exception as e:
        # 복구 불가 오류 → failed (임의 MPP·치수로 채우지 않음 §4-1)
        _log(f"변환 중단(예외): {type(e).__name__}: {e}")
        return ConversionResult.failed(
            job.slide_id, reason=f"{type(e).__name__}: {e}", log="\n".join(log))


# ─────────────────────────────────────────────────────────────
# ① extract_meta + MPP 폴백 체인
# ─────────────────────────────────────────────────────────────
def extract_meta(local_source_path: str, input_format: str) -> SlideMeta:
    """① 원본에서 MPP·해상도·원본 레벨 수·포맷 추출(§4-2 ①).

    width/height/레벨 수는 openslide(있으면)로, 없으면 pyvips 로 읽는다. MPP 는 _extract_mpp 폴백 체인.
    어느 경로든 MPP 추출 실패 시 None → run() 이 resolve_terminal_status 로 ready_no_mpp(§4-1).
    """
    width, height, levels = _read_dimensions(local_source_path)
    mpp = _extract_mpp(local_source_path, input_format)
    return SlideMeta(width=width, height=height, overview_levels=levels,
                     mpp=mpp, original_format=input_format)


def _read_dimensions(local_source_path: str) -> tuple[int, int, int]:
    """원본 (width, height, level_count). openslide 우선, 실패 시 pyvips. (지연 임포트)"""
    # openslide 우선(WSI 메타에 강함)
    try:
        import openslide  # type: ignore
        sl = openslide.OpenSlide(local_source_path)
        try:
            w, h = sl.dimensions
            lv = int(getattr(sl, "level_count", 1) or 1)
            return int(w), int(h), lv
        finally:
            sl.close()
    except Exception:
        pass
    # pyvips 폴백
    import pyvips  # type: ignore
    img = pyvips.Image.new_from_file(local_source_path, access="sequential")
    n_pages = 1
    try:
        n_pages = int(img.get("n-pages"))
    except Exception:
        n_pages = 1
    return int(img.width), int(img.height), n_pages


# ── MPP 폴백 체인 ──────────────────────────────────────────────
# 설계 원칙(메모리 확정): "여러 예상 위치를 순서대로 열어보고 처음 찾은 유효값을 채택, 다 실패하면 None".
# 보편성을 지향하되 **검증 안 된 갈래를 검증된 척하지 않는다**(각 파서 docstring 에 검증/미검증 명시).
# 각 갈래는 '순수 파서'(이미 읽어온 원시값 → Optional[float])로 분리해 단위테스트 가능하게 한다.
# 파일에서 원시값을 긁어오는 부분만 라이브러리 의존(지연 임포트, 실패 시 다음 갈래).

_MPP_RE = re.compile(r"MPP\s*=\s*([0-9]*\.?[0-9]+)", re.IGNORECASE)


def _valid_mpp(value: Optional[float]) -> Optional[float]:
    """양수 + 합리적 범위(0.05~2.0 μm/px) 검사. 범위 밖/비양수/파싱불가 → None(쓰레기 값 채택 방지)."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v <= 0 or not (MPP_ACCEPT_MIN <= v <= MPP_ACCEPT_MAX):
        return None
    return v


def _mpp_from_openslide_props(props: Dict[str, Any]) -> Optional[float]:
    """[검증됨] openslide.properties 의 'openslide.mpp-x'/'mpp-y'. 둘 중 유효한 첫 값.

    ※ openslide 가 형식을 인식할 때만 채워진다. Motic generic-tiff 처럼 vendor 미인식이면 None
      (실측: openslide 가 mpp-x=None 반환) → 다음 갈래로.
    """
    for key in ("openslide.mpp-x", "openslide.mpp-y"):
        v = _valid_mpp(props.get(key))
        if v is not None:
            return v
    return None


def _mpp_from_image_description(desc: Optional[str]) -> Optional[float]:
    """[검증됨 — 2026-06-12 Motic 실측] ImageDescription 의 'MPP=' 패턴(Aperio/Motic 공통).

    실측: Motic 파일 ImageDescription 에 'MPP = 0.261438' 존재(openslide 는 못 읽음).
    정규식 r'MPP\\s*=\\s*([\\d.]+)'. Aperio SVS 도 ImageDescription 에 'MPP=' 표기 → 둘 다 커버.
    """
    if not desc:
        return None
    m = _MPP_RE.search(desc)
    if not m:
        return None
    return _valid_mpp(m.group(1))


def _mpp_from_ome_xml(xml: Optional[str]) -> Optional[float]:
    """[이론상 동작, 실파일 검증 전] OME-TIFF 의 OME-XML PhysicalSizeX(+PhysicalSizeXUnit 단위 환산).

    표준 위치라 로직은 짜되 실파일 미검증. PhysicalSizeX 는 보통 µm; Unit 이 nm/mm 면 환산.
    """
    if not xml:
        return None
    mx = re.search(r'PhysicalSizeX\s*=\s*"([0-9]*\.?[0-9]+)"', xml)
    if not mx:
        return None
    value = float(mx.group(1))
    munit = re.search(r'PhysicalSizeXUnit\s*=\s*"([^"]+)"', xml)
    unit = (munit.group(1) if munit else "µm").strip()
    return _valid_mpp(_to_micrometers(value, unit))


def _mpp_from_tiff_resolution(xres: Optional[float], yres: Optional[float],
                              resolution_unit: Optional[int]) -> Optional[float]:
    """[이론상 동작, 실파일 검증 전 — ★ 뷰웍스 TIFF 유력 후보, 회신 후 확정] generic TIFF
    XResolution/YResolution + ResolutionUnit → μm/px 환산.

    ★ 단위 주의: XResolution 은 'ResolutionUnit 당 픽셀 수'(pixels per unit).
      ResolutionUnit: 2=inch(1 inch=25400 µm), 3=cm(1 cm=10000 µm). 1=무단위(환산 불가→None).
      μm/px = (단위당 µm) / (단위당 픽셀 수).
    """
    res = xres if xres else yres
    if not res or res <= 0:
        return None
    if resolution_unit == 2:      # inch
        unit_in_um = 25400.0
    elif resolution_unit == 3:    # centimeter
        unit_in_um = 10000.0
    else:                         # 1=무단위 또는 미상 → 환산 불가
        return None
    return _valid_mpp(unit_in_um / float(res))


def _mpp_from_dicom_pixel_spacing(pixel_spacing: Optional[Any]) -> Optional[float]:
    """[미검증 — v1.0 입력 아님, 미래 대비] DICOM PixelSpacing(mm/px) → μm/px(×1000).

    PixelSpacing 은 [row, col] mm. SharedFunctionalGroupsSequence→PixelMeasuresSequence 위치.
    여기선 이미 추출된 값(시퀀스 또는 단일)을 받아 환산만 한다.
    """
    if pixel_spacing is None:
        return None
    try:
        first = pixel_spacing[0] if isinstance(pixel_spacing, (list, tuple)) else pixel_spacing
        return _valid_mpp(float(first) * 1000.0)   # mm → µm
    except (TypeError, ValueError, IndexError):
        return None


def _to_micrometers(value: float, unit: str) -> float:
    """OME PhysicalSize 단위 → µm 환산."""
    u = (unit or "").strip().lower()
    if u in ("µm", "um", "micron", "micrometer", "micrometre", "µm"):
        return value
    if u in ("nm", "nanometer", "nanometre"):
        return value / 1000.0
    if u in ("mm", "millimeter", "millimetre"):
        return value * 1000.0
    if u in ("cm", "centimeter", "centimetre"):
        return value * 10000.0
    # 미상 단위 → µm 로 가정(보수적). _valid_mpp 가 범위로 걸러냄.
    return value


def _extract_mpp(local_source_path: str, input_format: str) -> Optional[float]:
    """포맷별 MPP(μm/px) 추출 폴백 체인. 실패 시 None(임의 기본값 금지, §4-1).

    순서: ① openslide props → ② ImageDescription 'MPP=' → ③ OME-XML → ④ TIFF XResolution
          → ⑤ DICOM PixelSpacing → ⑥ None(→ ready_no_mpp).
    각 갈래는 원시값을 긁어와(라이브러리 지연 임포트, 실패 시 다음) 순수 파서에 넘긴다.
    """
    fmt = (input_format or "").strip().lower()

    # ① openslide props (+ openslide 가 ImageDescription 도 노출하면 ②도 같이 시도)
    props = _read_openslide_props(local_source_path)
    if props is not None:
        v = _mpp_from_openslide_props(props)
        if v is not None:
            return v
        # openslide.comment / tiff.ImageDescription 에 MPP= 가 있을 수 있음(②)
        desc = props.get("openslide.comment") or props.get("tiff.ImageDescription")
        v = _mpp_from_image_description(desc)
        if v is not None:
            return v

    # ② tifffile 로 ImageDescription 직접 읽기(openslide 미인식 형식 — Motic 실측 경로)
    desc, ome_xml, xres, yres, runit = _read_tiff_tags(local_source_path)
    v = _mpp_from_image_description(desc)
    if v is not None:
        return v
    # ③ OME-TIFF
    v = _mpp_from_ome_xml(ome_xml)
    if v is not None:
        return v
    # ④ generic TIFF resolution 태그(★ 뷰웍스 후보)
    v = _mpp_from_tiff_resolution(xres, yres, runit)
    if v is not None:
        return v

    # ⑤ DICOM
    if fmt in ("dcm", "dicom"):
        v = _mpp_from_dicom_pixel_spacing(_read_dicom_pixel_spacing(local_source_path))
        if v is not None:
            return v

    # ⑥ 다 실패 → None (ready_no_mpp 종착)
    return None


# ── 파일에서 원시값 긁어오기(라이브러리 의존, 지연 임포트·실패 시 graceful) ──
def _read_openslide_props(path: str) -> Optional[Dict[str, Any]]:
    try:
        import openslide  # type: ignore
        sl = openslide.OpenSlide(path)
        try:
            return dict(sl.properties)
        finally:
            sl.close()
    except Exception:
        return None


def _read_tiff_tags(path: str):
    """(ImageDescription, ome_xml, XResolution, YResolution, ResolutionUnit). 실패 항목은 None."""
    desc = ome_xml = None
    xres = yres = None
    runit = None
    try:
        import tifffile  # type: ignore
        with tifffile.TiffFile(path) as tf:
            page = tf.pages[0]
            desc = getattr(page, "description", None)
            if desc and desc.lstrip().startswith("<?xml"):
                ome_xml = desc
            if getattr(tf, "ome_metadata", None):
                ome_xml = tf.ome_metadata
            tags = page.tags
            if "XResolution" in tags:
                xres = _rational_to_float(tags["XResolution"].value)
            if "YResolution" in tags:
                yres = _rational_to_float(tags["YResolution"].value)
            if "ResolutionUnit" in tags:
                ru = tags["ResolutionUnit"].value
                runit = int(ru) if not hasattr(ru, "value") else int(ru.value)
    except Exception:
        pass
    return desc, ome_xml, xres, yres, runit


def _rational_to_float(val: Any) -> Optional[float]:
    """TIFF RATIONAL((num, den) 또는 스칼라) → float."""
    try:
        if isinstance(val, (tuple, list)) and len(val) == 2:
            num, den = val
            return float(num) / float(den) if den else None
        return float(val)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _read_dicom_pixel_spacing(path: str) -> Optional[Any]:
    try:
        import pydicom  # type: ignore
        ds = pydicom.dcmread(path, stop_before_pixels=True)
        if hasattr(ds, "PixelSpacing"):
            return ds.PixelSpacing
        sfg = getattr(ds, "SharedFunctionalGroupsSequence", None)
        if sfg:
            pm = getattr(sfg[0], "PixelMeasuresSequence", None)
            if pm:
                return getattr(pm[0], "PixelSpacing", None)
    except Exception:
        return None
    return None


# ─────────────────────────────────────────────────────────────
# ② convert_cog — libvips 검증 명령
# ─────────────────────────────────────────────────────────────
def convert_cog(local_source_path: str, out_path: str) -> int:
    """② 표준 스펙 고정 COG TIFF 변환(§4-1·§4-2 ②). 반환: 생성된 '오버뷰' 레벨 수(전체 페이지-1).

    ★ 메모리 안전(§12 QA-2): pyvips 는 demand-driven 스트리밍. new_from_file(access='sequential')
      로 열어 tiffsave 하면 수 GB 입력도 전체를 메모리에 올리지 않는다(타일 단위 스트림).
    ★ 검증 명령과 동일 옵션: tile 256, pyramid, compression jpeg, Q 85, bigtiff.
    """
    import pyvips  # type: ignore
    img = pyvips.Image.new_from_file(local_source_path, access="sequential")
    img.tiffsave(
        out_path,
        tile=True,
        tile_width=TILE_SIZE,
        tile_height=TILE_SIZE,
        pyramid=True,
        compression="jpeg",
        Q=JPEG_QUALITY,
        bigtiff=True,
    )
    total_pages = _count_tiff_pages(out_path)
    # overview_levels = 전체 페이지 수 - 1(레벨 0=풀해상도 제외). 최소 0.
    return max(total_pages - 1, 0)


def _count_tiff_pages(path: str) -> int:
    """COG 의 해상도 페이지(피라미드 레벨) 수. pyvips n-pages 우선, tifffile 폴백."""
    try:
        import pyvips  # type: ignore
        img = pyvips.Image.new_from_file(path, access="sequential")
        return int(img.get("n-pages"))
    except Exception:
        pass
    import tifffile  # type: ignore
    with tifffile.TiffFile(path) as tf:
        return len(tf.pages)


def _page_dimensions(path: str) -> list[tuple[int, int]]:
    """각 피라미드 페이지의 (width, height) 목록(레벨0→최저). 단조감소 검증용."""
    dims: list[tuple[int, int]] = []
    try:
        import pyvips  # type: ignore
        n = _count_tiff_pages(path)
        for i in range(n):
            p = pyvips.Image.new_from_file(path, page=i)
            dims.append((int(p.width), int(p.height)))
        return dims
    except Exception:
        pass
    import tifffile  # type: ignore
    with tifffile.TiffFile(path) as tf:
        for pg in tf.pages:
            dims.append((int(pg.imagewidth), int(pg.imagelength)))
    return dims


# ─────────────────────────────────────────────────────────────
# ③ minimap ④ thumbnail (S3 사전 생성 — D7 해결 목표)
# ─────────────────────────────────────────────────────────────
def extract_minimap(cog_path: str, out_path: str) -> None:
    """③ 최저 오버뷰 → minimap.png(§4-2 ③). 가장 작은 피라미드 페이지를 그대로 PNG 로 저장(경량)."""
    import pyvips  # type: ignore
    last = _count_tiff_pages(cog_path) - 1
    page = max(last, 0)
    img = pyvips.Image.new_from_file(cog_path, page=page)
    img = _flatten_to_srgb(img)
    img.write_to_file(out_path)  # 확장자(.png)로 포맷 결정


def extract_thumbnail(cog_path: str, out_path: str) -> None:
    """④ 적정 오버뷰 → thumbnail.jpg(400×300, §4-2 ④). 종횡비 유지 축소 후 캔버스 정합.

    ★ S3 사전 생성 원칙(§4-2) — openslide 동적 생성(D7)을 이 단계로 대체.
    작은 오버뷰 페이지에서 thumbnail 연산(스트리밍·저메모리)으로 폭 400 기준 축소.
    """
    import pyvips  # type: ignore
    # thumbnail_image 는 저해상도 페이지를 골라 빠르게 축소(메모리 안전).
    img = pyvips.Image.thumbnail(cog_path, 400, height=300, size="down")
    img = _flatten_to_srgb(img)
    img.jpegsave(out_path, Q=JPEG_QUALITY)


def _flatten_to_srgb(img):
    """알파/CMYK 등을 흰 배경 sRGB 로 평탄화(PNG/JPEG 안전)."""
    try:
        if img.hasalpha():
            img = img.flatten(background=[255, 255, 255])
        if img.interpretation not in ("srgb", "rgb"):
            img = img.colourspace("srgb")
    except Exception:
        pass
    return img


# ─────────────────────────────────────────────────────────────
# ⑤ generate_kb_json — kb 초안(선택 주입)
# ─────────────────────────────────────────────────────────────
def generate_kb_json(meta: SlideMeta, job: ConversionJob,
                     kb_generator: Optional[Callable[["SlideMeta", ConversionJob],
                                                     Optional[Dict[str, Any]]]] = None
                     ) -> Optional[Dict[str, Any]]:
    """⑤ knowledge_base JSON 초안(§4-2 ⑤·§5-3). **엔진은 Claude API 를 직접 모른다.**

    kb_generator 가 주입되면 그걸로 초안을 만들고, 없으면 None 을 반환한다(검수본 보존: persist 가
    None 이면 기존 kb 를 덮지 않음 §5-4). Claude API 키/엔드포인트는 호출 계층(trigger/caller)이
    kb_generator 클로저로 싸서 주입한다(이식성 §4-3).
    """
    if kb_generator is None:
        return None
    return kb_generator(meta, job)


# ─────────────────────────────────────────────────────────────
# ⑥ run_qc — §4-4 자동 검증
# ─────────────────────────────────────────────────────────────
@dataclass
class QcReport:
    """run_qc 산출물. passed=False → failed. mpp_out_of_range 는 경고(종착 결정과 무관)."""
    passed: bool
    failures: tuple = ()          # 치명 실패 항목 목록(로그용)
    mpp_out_of_range: bool = False


def run_qc(cog_path: str, meta: SlideMeta, produced_overviews: int) -> QcReport:
    """⑥ §4-4 자동 QC.

    치명(실패) 항목:
      - 피라미드 존재: 페이지 ≥ 2 (단일 페이지면 오버뷰 없음 → failed)
      - 피라미드 무결성: 페이지 치수가 단조감소(레벨0이 가장 큼). ★실측에서 libvips 의 핵심 강점
        (GDAL '부실 피라미드' 대비). 단조감소 위반 → failed.
      - 타일 가독성: 저·중·고 3레벨에서 타일 읽기 성공(로컬 디코드 성공 = HTTP 200 대응 §4-4)
      - 흰 타일 비율: 중앙 샘플 타일 흰색 < 95%
      - 최소 해상도: max(width,height) ≥ 5000 px
    경고(계속) 항목:
      - MPP 범위(0.1~1.0): 밖이면 mpp_out_of_range=True 지만 passed 에 영향 없음(§4-4).

    ※ §4-4 의 'DZI 레벨 수 예상값 일치'는 libvips 가변 레벨(실측 9레벨)이라 '고정 7 일치'로
      강제하지 않고 '피라미드 무결성(단조감소·다중 페이지)' 검증으로 대체한다(report.md 에 명시,
      외부검증·EC2 리허설 D35 대상).
    """
    failures: list[str] = []

    # 최소 해상도
    if max(meta.width, meta.height) < MIN_DIMENSION_PX:
        failures.append(f"min_dimension<{MIN_DIMENSION_PX}({meta.width}x{meta.height})")

    # 피라미드 페이지/단조감소
    dims = _page_dimensions(cog_path)
    if len(dims) < 2:
        failures.append(f"no_pyramid(pages={len(dims)})")
    else:
        for a, b in zip(dims, dims[1:]):
            if not (b[0] <= a[0] and b[1] <= a[1] and (b[0] < a[0] or b[1] < a[1])):
                failures.append(f"pyramid_not_monotonic({dims})")
                break

    # 타일 가독성(저/중/고 3레벨) + 흰 타일 비율(최저해상도 페이지 중앙)
    try:
        readable, white_ratio = _sample_tiles(cog_path, dims)
        if not readable:
            failures.append("tiles_unreadable")
        if white_ratio is not None and white_ratio >= 0.95:
            failures.append(f"white_ratio>=0.95({white_ratio:.3f})")
    except Exception as e:
        failures.append(f"tile_sample_error:{e}")

    # MPP 경고(실패 아님)
    mpp_warn = meta.mpp is not None and not (MPP_MIN <= meta.mpp <= MPP_MAX)

    return QcReport(passed=(len(failures) == 0),
                    failures=tuple(failures),
                    mpp_out_of_range=mpp_warn)


def _sample_tiles(cog_path: str, dims: list[tuple[int, int]]):
    """3레벨에서 타일 디코드 성공 여부 + 최저해상도 페이지 중앙의 흰 픽셀 비율.

    반환 (readable: bool, white_ratio: Optional[float]). pyvips 로 작은 영역만 fetch(저메모리).
    """
    import pyvips  # type: ignore
    import numpy as np  # type: ignore

    if not dims:
        return False, None
    n = len(dims)
    sample_pages = sorted({0, n // 2, n - 1})  # 저·중·고

    readable = True
    for p in sample_pages:
        try:
            img = pyvips.Image.new_from_file(cog_path, page=p)
            w, h = img.width, img.height
            cw = min(TILE_SIZE, w)
            ch = min(TILE_SIZE, h)
            left = max((w - cw) // 2, 0)
            top = max((h - ch) // 2, 0)
            region = img.crop(left, top, cw, ch)
            _ = region.avg()  # 강제 디코드
        except Exception:
            readable = False

    # 흰 비율: 최저해상도 페이지 중앙 타일
    white_ratio = None
    try:
        img = pyvips.Image.new_from_file(cog_path, page=n - 1)
        img = _flatten_to_srgb(img)
        w, h = img.width, img.height
        cw = min(TILE_SIZE, w)
        ch = min(TILE_SIZE, h)
        region = img.crop(max((w - cw) // 2, 0), max((h - ch) // 2, 0), cw, ch)
        arr = np.ndarray(buffer=region.write_to_memory(),
                         dtype=np.uint8,
                         shape=[region.height, region.width, region.bands])
        # RGB 모두 ≥ 245 면 흰색으로 간주
        rgb = arr[:, :, :3]
        white_mask = (rgb >= 245).all(axis=2)
        white_ratio = float(white_mask.mean())
    except Exception:
        white_ratio = None

    return readable, white_ratio
