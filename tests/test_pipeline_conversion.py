"""
tests/test_pipeline_conversion.py — COG 변환 파이프라인 2단계 단위 테스트

이 환경엔 pyvips/openslide/tifffile/boto3 가 없어도 돌아야 한다. 따라서:
- 순수 파서(_mpp_from_* / _valid_mpp / _to_micrometers)는 라이브러리 무의존이라 직접 검증.
- run() 오케스트레이션은 이미지 단계 함수를 monkeypatch 로 대체(스텁)해 상태흐름만 검증.
- persist_result 는 가짜 conn/cursor 로 SQL 화이트리스트·전이검증·검수본 보존을 검증.
"""

import pytest

from pipeline import (
    ConversionJob, ConversionResult, ConversionStatus, InputFormat,
    resolve_terminal_status, assert_transition, IllegalTransition,
)
from pipeline import conversion_engine as ce
from pipeline import storage_adapter as sa
from pipeline.trigger_adapter import HttpTriggerAdapter


# ─────────────────────────────────────────────────────────────
# MPP 폴백 체인 — 순수 파서
# ─────────────────────────────────────────────────────────────
class TestMppParsers:
    def test_valid_mpp_range(self):
        assert ce._valid_mpp(0.25) == 0.25
        assert ce._valid_mpp(0.05) == 0.05      # 경계 하한 채택
        assert ce._valid_mpp(2.0) == 2.0        # 경계 상한 채택
        assert ce._valid_mpp(0.0) is None       # 비양수
        assert ce._valid_mpp(-1) is None
        assert ce._valid_mpp(0.04) is None      # 범위 밖(쓰레기) 거부
        assert ce._valid_mpp(2.5) is None
        assert ce._valid_mpp(None) is None
        assert ce._valid_mpp("abc") is None

    def test_openslide_props(self):
        assert ce._mpp_from_openslide_props({"openslide.mpp-x": "0.2456"}) == pytest.approx(0.2456)
        # mpp-x None, mpp-y 유효 → mpp-y 채택
        assert ce._mpp_from_openslide_props(
            {"openslide.mpp-x": None, "openslide.mpp-y": "0.5"}) == 0.5
        # 둘 다 없음/None → None (Motic generic-tiff 실측 케이스)
        assert ce._mpp_from_openslide_props({"openslide.mpp-x": None}) is None
        assert ce._mpp_from_openslide_props({}) is None

    def test_image_description_verified_motic(self):
        # ★ 2026-06-12 Motic 실측 값
        assert ce._mpp_from_image_description("Foo|MPP = 0.261438|Bar") == pytest.approx(0.261438)
        # Aperio 스타일
        assert ce._mpp_from_image_description("Aperio Image|AppMag=20|MPP=0.4965") == pytest.approx(0.4965)
        assert ce._mpp_from_image_description("no mpp here") is None
        assert ce._mpp_from_image_description(None) is None
        # 범위 밖 값은 거부
        assert ce._mpp_from_image_description("MPP=10.0") is None

    def test_ome_xml(self):
        xml = '<Pixels PhysicalSizeX="0.32" PhysicalSizeXUnit="µm"/>'
        assert ce._mpp_from_ome_xml(xml) == pytest.approx(0.32)
        # nm 단위 환산
        xml_nm = '<Pixels PhysicalSizeX="320" PhysicalSizeXUnit="nm"/>'
        assert ce._mpp_from_ome_xml(xml_nm) == pytest.approx(0.32)
        # 단위 미지정 → µm 가정
        assert ce._mpp_from_ome_xml('<Pixels PhysicalSizeX="0.5"/>') == 0.5
        assert ce._mpp_from_ome_xml(None) is None
        assert ce._mpp_from_ome_xml("<Pixels/>") is None

    def test_tiff_resolution(self):
        # inch: 25400µm / 100000 px-per-inch = 0.254 µm/px
        assert ce._mpp_from_tiff_resolution(100000.0, 100000.0, 2) == pytest.approx(0.254)
        # cm: 10000µm / 40000 px-per-cm = 0.25 µm/px
        assert ce._mpp_from_tiff_resolution(40000.0, 40000.0, 3) == pytest.approx(0.25)
        # 무단위(1) → 환산 불가 → None
        assert ce._mpp_from_tiff_resolution(40000.0, None, 1) is None
        # 해상도 0/None → None
        assert ce._mpp_from_tiff_resolution(0, 0, 3) is None
        assert ce._mpp_from_tiff_resolution(None, None, 2) is None
        # 범위 밖(너무 큰 mpp) → None: 10000µm/cm / 100 = 100 µm/px
        assert ce._mpp_from_tiff_resolution(100.0, 100.0, 3) is None

    def test_dicom_pixel_spacing(self):
        # 0.00025 mm → 0.25 µm
        assert ce._mpp_from_dicom_pixel_spacing([0.00025, 0.00025]) == pytest.approx(0.25)
        assert ce._mpp_from_dicom_pixel_spacing(0.0003) == pytest.approx(0.3)
        assert ce._mpp_from_dicom_pixel_spacing(None) is None
        assert ce._mpp_from_dicom_pixel_spacing([]) is None

    def test_to_micrometers(self):
        assert ce._to_micrometers(1.0, "µm") == 1.0
        assert ce._to_micrometers(1000.0, "nm") == 1.0
        assert ce._to_micrometers(0.001, "mm") == 1.0
        assert ce._to_micrometers(0.0001, "cm") == 1.0


# ─────────────────────────────────────────────────────────────
# 상태머신 / 종착 결정
# ─────────────────────────────────────────────────────────────
class TestStateMachine:
    def test_resolve_terminal(self):
        assert resolve_terminal_status(0.25) == ConversionStatus.READY
        assert resolve_terminal_status(None) == ConversionStatus.READY_NO_MPP
        assert resolve_terminal_status(0.0) == ConversionStatus.READY_NO_MPP
        assert resolve_terminal_status(-1.0) == ConversionStatus.READY_NO_MPP

    def test_legal_transitions(self):
        assert_transition(ConversionStatus.PENDING, ConversionStatus.CONVERTING)
        assert_transition(ConversionStatus.CONVERTING, ConversionStatus.QC_CHECK)
        assert_transition(ConversionStatus.QC_CHECK, ConversionStatus.READY)
        assert_transition(ConversionStatus.QC_CHECK, ConversionStatus.READY_NO_MPP)

    def test_illegal_transitions(self):
        with pytest.raises(IllegalTransition):
            assert_transition(ConversionStatus.FAILED, ConversionStatus.READY)
        with pytest.raises(IllegalTransition):
            assert_transition(ConversionStatus.READY, ConversionStatus.CONVERTING)


# ─────────────────────────────────────────────────────────────
# run() 오케스트레이션 (이미지 단계 monkeypatch)
# ─────────────────────────────────────────────────────────────
class _FakeReader:
    def fetch_to_local(self, bucket, key):
        return "/tmp/fake_source.svs"


class _FakeWriter:
    def __init__(self):
        self.puts = []

    def put_cog(self, slide_id, p):
        self.puts.append(("cog", p)); return f"cog/{slide_id}.tif"

    def put_minimap(self, slide_id, p):
        self.puts.append(("minimap", p)); return f"minimap/{slide_id}.png"

    def put_thumbnail(self, slide_id, p):
        self.puts.append(("thumb", p)); return f"thumbnail/{slide_id}.jpg"


def _job(fmt="SVS"):
    return ConversionJob(slide_id="SA-HST-001", source_s3_key="uploads/x.svs",
                         input_format=InputFormat.coerce(fmt), subject_code="HST")


def _patch_stages(monkeypatch, mpp, qc_pass=True, qc_failures=(), overviews=8, raise_on=None):
    meta = ce.SlideMeta(width=60000, height=40000, overview_levels=9,
                        mpp=mpp, original_format="SVS")

    def fake_extract_meta(path, fmt):
        if raise_on == "meta":
            raise RuntimeError("boom-meta")
        return meta

    def fake_convert(src, out):
        return overviews

    monkeypatch.setattr(ce, "extract_meta", fake_extract_meta)
    monkeypatch.setattr(ce, "convert_cog", fake_convert)
    monkeypatch.setattr(ce, "extract_minimap", lambda c, o: None)
    monkeypatch.setattr(ce, "extract_thumbnail", lambda c, o: None)
    monkeypatch.setattr(ce, "run_qc", lambda c, m, ov: ce.QcReport(
        passed=qc_pass, failures=tuple(qc_failures),
        mpp_out_of_range=(m.mpp is not None and not (0.1 <= m.mpp <= 1.0))))
    return meta


class TestRun:
    def test_success_ready(self, monkeypatch, tmp_path):
        _patch_stages(monkeypatch, mpp=0.25)
        w = _FakeWriter()
        res = ce.run(_job(), _FakeReader(), w, workdir=str(tmp_path))
        assert res.status == ConversionStatus.READY
        assert res.mpp == 0.25
        assert res.cog_s3_key == "cog/SA-HST-001.tif"
        assert res.minimap_s3_key and res.thumbnail_s3_key
        assert res.overview_levels == 8
        assert res.qc_passed_at is not None
        assert res.width == 60000 and res.height == 40000
        assert len(w.puts) == 3   # 산출물 3종 업로드

    def test_no_mpp_goes_ready_no_mpp(self, monkeypatch, tmp_path):
        _patch_stages(monkeypatch, mpp=None)
        res = ce.run(_job(), _FakeReader(), _FakeWriter(), workdir=str(tmp_path))
        assert res.status == ConversionStatus.READY_NO_MPP
        assert res.mpp is None            # 임의 기본값 절대 없음(§4-1)
        assert res.cog_s3_key             # 타일은 정상 서빙(키 채워짐)
        assert res.qc_passed_at is not None

    def test_qc_failure_returns_failed_and_no_upload(self, monkeypatch, tmp_path):
        _patch_stages(monkeypatch, mpp=0.25, qc_pass=False, qc_failures=("white_ratio>=0.95",))
        w = _FakeWriter()
        res = ce.run(_job(), _FakeReader(), w, workdir=str(tmp_path))
        assert res.status == ConversionStatus.FAILED
        assert "white_ratio" in res.failure_reason
        assert res.cog_s3_key is None
        assert w.puts == []               # QC 실패 시 업로드 안 함

    def test_exception_returns_failed(self, monkeypatch, tmp_path):
        _patch_stages(monkeypatch, mpp=0.25, raise_on="meta")
        res = ce.run(_job(), _FakeReader(), _FakeWriter(), workdir=str(tmp_path))
        assert res.status == ConversionStatus.FAILED
        assert "boom-meta" in res.failure_reason

    def test_kb_generator_injected(self, monkeypatch, tmp_path):
        _patch_stages(monkeypatch, mpp=0.25)
        kb = {"key_structures": ["villus"]}
        res = ce.run(_job(), _FakeReader(), _FakeWriter(),
                     kb_generator=lambda m, j: kb, workdir=str(tmp_path))
        assert res.knowledge_base == kb

    def test_kb_none_without_generator(self, monkeypatch, tmp_path):
        _patch_stages(monkeypatch, mpp=0.25)
        res = ce.run(_job(), _FakeReader(), _FakeWriter(), workdir=str(tmp_path))
        assert res.knowledge_base is None   # 검수본 보존: persist 가 기존 kb 안 덮음


# ─────────────────────────────────────────────────────────────
# persist_result (가짜 conn/cursor)
# ─────────────────────────────────────────────────────────────
class _FakeCursor:
    def __init__(self, fetch_row):
        self._fetch_row = fetch_row
        self.executed = []     # (sql, params)
        self.closed = False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return self._fetch_row

    def close(self):
        self.closed = True


class _FakeConn:
    def __init__(self, fetch_row):
        self._cur = _FakeCursor(fetch_row)
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self._cur

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def _result(status=ConversionStatus.READY, kb=None):
    return ConversionResult(
        slide_id="SA-HST-001", status=status, mpp=0.25, width=60000, height=40000,
        cog_s3_key="cog/SA-HST-001.tif", minimap_s3_key="minimap/SA-HST-001.png",
        thumbnail_s3_key="thumbnail/SA-HST-001.jpg", overview_levels=8,
        knowledge_base=kb, qc_passed_at="2026-06-12T00:00:00+00:00", log="ok")


class TestPersistResult:
    def test_missing_row_raises(self):
        conn = _FakeConn(fetch_row=None)
        with pytest.raises(sa.PersistTargetMissing):
            sa.persist_result(_result(), conn)
        assert conn.rolled_back is True

    def test_update_only_whitelist(self):
        # 기존 행: converting → ready (합법 전이), 기존 kb 없음
        conn = _FakeConn(fetch_row=("converting", None))
        sa.persist_result(_result(), conn)
        update_sql = [s for s, p in conn._cur.executed if s.strip().upper().startswith("UPDATE")][0]
        # 교육용 메타 컬럼은 절대 SET 에 없어야 함
        for forbidden in ("title_ko", "title_en", "organ_code", "stain", "license_source",
                          "subject_code", "institution_id", "deploy_status"):
            assert forbidden not in update_sql
        # 화이트리스트 컬럼은 있어야 함
        for col in ("conversion_status", "mpp", "width", "height", "s3_key",
                    "s3_minimap_key", "s3_thumbnail_key", "overview_levels",
                    "conversion_log", "qc_passed_at"):
            assert col in update_sql
        assert conn.committed is True

    def test_illegal_transition_blocked(self):
        # 기존 failed → ready 시도(오전이) → IllegalTransition, 롤백
        conn = _FakeConn(fetch_row=("failed", None))
        with pytest.raises(IllegalTransition):
            sa.persist_result(_result(status=ConversionStatus.READY), conn)
        assert conn.rolled_back is True

    def test_qc_passed_at_only_on_terminal(self):
        # failed 결과(qc_passed_at None 가정) → qc_passed_at SET 안 됨
        conn = _FakeConn(fetch_row=("converting", None))
        failed = ConversionResult.failed("SA-HST-001", reason="bad", log="x")
        sa.persist_result(failed, conn)
        update_sql = [s for s, p in conn._cur.executed if s.strip().upper().startswith("UPDATE")][0]
        assert "qc_passed_at" not in update_sql

    def test_reviewed_kb_preserved(self):
        # 기존 kb 가 검수 완료본(reviewed=true) → 초안으로 덮지 않음
        conn = _FakeConn(fetch_row=("converting", {"reviewed": True, "key_structures": ["x"]}))
        sa.persist_result(_result(kb={"key_structures": ["draft"]}), conn)
        update_sql = [s for s, p in conn._cur.executed if s.strip().upper().startswith("UPDATE")][0]
        assert "knowledge_base" not in update_sql   # 검수본 보존

    def test_draft_kb_written_when_not_reviewed(self):
        conn = _FakeConn(fetch_row=("converting", None))
        sa.persist_result(_result(kb={"key_structures": ["draft"]}), conn)
        update_sql = [s for s, p in conn._cur.executed if s.strip().upper().startswith("UPDATE")][0]
        assert "knowledge_base" in update_sql

    def test_kb_is_reviewed_helper(self):
        assert sa._kb_is_reviewed({"reviewed": True}) is True
        assert sa._kb_is_reviewed({"reviewed_at": "2026-06-01"}) is True
        assert sa._kb_is_reviewed('{"is_reviewed": true}') is True   # JSON 문자열
        assert sa._kb_is_reviewed({"key_structures": ["x"]}) is False
        assert sa._kb_is_reviewed(None) is False


# ─────────────────────────────────────────────────────────────
# HttpTriggerAdapter.parse
# ─────────────────────────────────────────────────────────────
class TestHttpTrigger:
    def test_valid(self):
        jobs = HttpTriggerAdapter().parse({
            "slide_id": "SA-HST-001", "source_s3_key": "uploads/x.svs",
            "input_format": "svs", "subject_code": "hst"})
        assert len(jobs) == 1
        j = jobs[0]
        assert j.slide_id == "SA-HST-001"
        assert j.input_format == InputFormat.SVS
        assert j.subject_code == "HST"     # 대문자 정규화

    def test_missing_field(self):
        with pytest.raises(ValueError):
            HttpTriggerAdapter().parse({"slide_id": "x", "source_s3_key": "y",
                                        "input_format": "svs"})  # subject_code 누락

    def test_unsupported_format(self):
        with pytest.raises(ValueError):
            HttpTriggerAdapter().parse({"slide_id": "x", "source_s3_key": "y",
                                        "input_format": "jpeg", "subject_code": "HST"})

    def test_non_dict(self):
        with pytest.raises(ValueError):
            HttpTriggerAdapter().parse("not a dict")
