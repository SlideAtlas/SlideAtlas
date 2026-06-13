"""
pipeline/storage_adapter.py — S3 이동 · RDS 갱신 인터페이스 (골격, 1단계)

역할 분리(이식성):
- SourceReader / ArtifactWriter : 엔진이 주입받는 '추상 I/O'(원본 읽기·산출물 쓰기). 엔진은 boto3 를 모른다.
- persist_result               : ConversionResult → slides 컬럼 UPDATE(§4-2 ⑦ update_db).
                                 ★ models.py 매핑표와 글자단위로 일치해야 한다(어긋나면 변환돼도 DB 미반영).

★ 본체 미구현 — 시그니처 + docstring + TODO + 매핑(주석) 만. 실제 boto3/psycopg2 호출은 다음 단계.
  (인증·게이트·구독·세션·_slide_access_allowed·tile_token 과 무관 — 본 모듈은 변환 산출물 적재 전용.)
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Optional, Any

from .models import ConversionResult, ConversionStatus, assert_reachable


# ─────────────────────────────────────────────────────────────
# 엔진에 주입되는 추상 I/O (boto3 의존을 엔진 밖으로 격리)
# ─────────────────────────────────────────────────────────────
class SourceReader(ABC):
    """원본(SVS/TIFF/DCM)을 엔진이 읽을 수 있는 로컬 경로로 가져온다."""

    @abstractmethod
    def fetch_to_local(self, bucket: Optional[str], key: str) -> str:
        """원본 S3 객체 → 로컬 임시 경로 반환. TODO(2단계): boto3 download_file/streaming."""
        raise NotImplementedError


class ArtifactWriter(ABC):
    """변환 산출물(COG·minimap·thumbnail)을 S3 에 올리고 최종 S3 키를 돌려준다."""

    @abstractmethod
    def put_cog(self, slide_id: str, local_path: str) -> str:
        """COG TIFF 업로드 → s3_key 반환. TODO."""
        raise NotImplementedError

    @abstractmethod
    def put_minimap(self, slide_id: str, local_path: str) -> str:
        """minimap.png 업로드 → s3_minimap_key 반환. TODO."""
        raise NotImplementedError

    @abstractmethod
    def put_thumbnail(self, slide_id: str, local_path: str) -> str:
        """thumbnail.jpg 업로드 → s3_thumbnail_key 반환. TODO."""
        raise NotImplementedError


# ─────────────────────────────────────────────────────────────
# ⑦ update_db — ConversionResult → slides 컬럼 (매핑표 = 단일 진실)
# ─────────────────────────────────────────────────────────────
def persist_result(result: ConversionResult, db_conn: Any) -> None:
    """ConversionResult 를 기존 slides 행에 UPDATE(§4-2 ⑦). **확정 계약 — 본체만 TODO.**

    ★★ 책임 경계(코드로 못박음) ★★
    1) **UPDATE-only — INSERT 절대 안 함.** slides 행 생성 주체는 D30 배치 파서이고, 변환은 이미
       존재하는 pending 행을 갱신할 뿐이다.
    2) **변환 산출 컬럼만 명시적으로 UPDATE.** 교육용 메타 컬럼(title_ko·title_en·organ_code·stain·
       license_source·subject_code 등)은 **절대 건드리지 않는다**(D30 파서 소유 — 덮어쓰기 금지).
    3) **대상 slide_id 행이 없으면 에러 반환**(조용히 INSERT 금지 — 경계 위반 탐지 신호).

    ★ slides 컬럼 매핑(models.py ConversionResult 매핑표와 1:1 — 변경 시 양쪽 동기):
        result.status.value      → conversion_status   (전이 검증: 기존행 status → result.status 를
                                                         models.assert_transition 으로 확인 후 UPDATE)
        result.mpp               → mpp                  (None 그대로 — 임의 기본값 금지 §4-1)
        result.width             → width
        result.height            → height
        result.cog_s3_key        → s3_key
        result.minimap_s3_key    → s3_minimap_key
        result.thumbnail_s3_key  → s3_thumbnail_key
        result.overview_levels   → overview_levels      (전용 컬럼 — db/slides_overview_levels_migration.sql)
        result.knowledge_base    → knowledge_base       (JSONB — ★검수본 보존 규칙 아래)
        result.qc_passed_at      → qc_passed_at          (ready/ready_no_mpp 시각)
        _compose_log(result)     → conversion_log        (log + failure_reason 합본)
      WHERE id = result.slide_id

    위 목록이 **UPDATE 허용 컬럼 화이트리스트의 전부**다. 여기 없는 컬럼은 SET 절에 넣지 않는다.

    ★ knowledge_base 검수본 보존 불변식(§5-4):
        kb 는 변환이 만드는 '초안'이고, 검수자가 배포 단계에서 보완한 '최종본'이 있다.
        재처리(failed/ready_no_mpp → pending → 재변환) 시 **이미 검수된 kb 가 존재하면 초안으로 덮어쓰지
        않는다.** (검수 여부 판별 방식 — 별도 플래그 컬럼 필요 여부 — 은 본체 단계에서 결정. 지금은
        '재처리가 검수본을 날리지 않는다'는 불변식만 확정.)

    전용 컬럼 없는 필드(슬라이드 스키마 무변경):
        failure_reason → conversion_log 에 합본(_compose_log). 새 컬럼 신설 안 함.
        (overview_levels 는 더 이상 합본 대상 아님 — 전용 컬럼화됨.)

    TODO(2단계):
      1) SELECT conversion_status FROM slides WHERE id=%s FOR UPDATE  → 기존 상태(NULL=행 없음)
      2) 행 없으면 **에러 반환**(INSERT 금지, 경계 위반)
      3) models.assert_transition(기존, result.status) 로 오전이 차단(§4-5)
      4) 위 화이트리스트 컬럼만 SET 으로 UPDATE (트랜잭션, 부분 실패 롤백 §12 QA-4)
      5) knowledge_base 는 검수본 보존 규칙 적용 후에만 SET(검수본 있으면 제외)
      6) ready/ready_no_mpp 가 아니면 qc_passed_at 은 건드리지 않음
    """
    cur = db_conn.cursor()
    try:
        # 1) 기존 상태 + 검수 여부 판별용 kb 조회(FOR UPDATE 로 동시 재처리 직렬화)
        cur.execute(
            "SELECT conversion_status, knowledge_base FROM slides WHERE id=%s FOR UPDATE",
            (result.slide_id,),
        )
        row = cur.fetchone()
        # 2) 행 없으면 에러(조용히 INSERT 금지 — 경계 위반 탐지 신호)
        if row is None:
            raise PersistTargetMissing(
                f"slides 행 없음: id={result.slide_id} (변환은 UPDATE-only, INSERT 금지)")
        current_status_raw, existing_kb = row[0], row[1]

        # 3) 오전이 차단(§4-5). 현재 status 가 None/미지 값이면 전이검증 생략(레거시 행 방어).
        try:
            current_status = ConversionStatus(current_status_raw)
        except ValueError:
            current_status = None  # 알 수 없는 기존 상태 — 도달성검증 불가, 갱신은 허용
        if current_status is not None:
            # 경로 도달성(여러 홉) 검증: pending→ready 허용, failed→ready 등 회귀 차단.
            assert_reachable(current_status, result.status)

        # 4) 화이트리스트 컬럼만 SET (교육용 메타 절대 미접촉)
        set_cols = [
            "conversion_status = %s",
            "mpp = %s",
            "width = %s",
            "height = %s",
            "s3_key = %s",
            "s3_minimap_key = %s",
            "s3_thumbnail_key = %s",
            "overview_levels = %s",
            "conversion_log = %s",
        ]
        params: list[Any] = [
            result.status.value,
            result.mpp,
            result.width,
            result.height,
            result.cog_s3_key,
            result.minimap_s3_key,
            result.thumbnail_s3_key,
            result.overview_levels,
            _compose_log(result),
        ]

        # 5) knowledge_base — 검수본 보존(§5-4): 이미 검수된 kb 가 있으면 초안으로 덮지 않는다.
        #    판별: result.knowledge_base 가 None 이면 애초에 안 건드림. 기존 kb 가 검수 완료
        #    (_kb_is_reviewed)면 result 가 채워졌어도 SET 에서 제외.
        if result.knowledge_base is not None and not _kb_is_reviewed(existing_kb):
            set_cols.append("knowledge_base = %s")
            params.append(_as_jsonb(result.knowledge_base))

        # 6) qc_passed_at — ready/ready_no_mpp 도달 시에만 SET
        if result.status in (ConversionStatus.READY, ConversionStatus.READY_NO_MPP) \
                and result.qc_passed_at is not None:
            set_cols.append("qc_passed_at = %s")
            params.append(result.qc_passed_at)

        params.append(result.slide_id)
        cur.execute(
            f"UPDATE slides SET {', '.join(set_cols)} WHERE id = %s",
            params,
        )
        db_conn.commit()
    except Exception:
        db_conn.rollback()
        raise
    finally:
        cur.close()


class PersistTargetMissing(Exception):
    """persist_result 대상 slides 행이 없음(UPDATE-only 경계 위반 신호 — 조용한 INSERT 금지)."""


def _kb_is_reviewed(existing_kb: Any) -> bool:
    """기존 kb 가 '검수 완료본'인지 판별(검수본 보존 §5-4).

    판별 규칙(현행): kb dict 에 reviewed/reviewed_at/is_reviewed 중 truthy 가 있으면 검수본으로 본다.
    (전용 플래그 컬럼을 신설하지 않고 kb JSON 내 마커로 표현 — 검수 모달이 보완 시 마커를 남기는 전제.
     마커가 없으면 초안으로 간주해 재처리 시 갱신 허용.)
    """
    if not existing_kb:
        return False
    kb = existing_kb
    if isinstance(kb, str):
        import json
        try:
            kb = json.loads(kb)
        except (ValueError, TypeError):
            return False
    if not isinstance(kb, dict):
        return False
    return bool(kb.get("reviewed") or kb.get("reviewed_at") or kb.get("is_reviewed"))


def _as_jsonb(value: Any) -> Any:
    """dict → psycopg2 가 JSONB 로 적재할 수 있는 형태(json.dumps 문자열). None 은 그대로."""
    if value is None:
        return None
    import json
    return json.dumps(value, ensure_ascii=False)


def _compose_log(result: ConversionResult) -> str:
    """conversion_log 본문 합성: 단계 로그 + (실패 시) failure_reason.

    전용 컬럼이 없는 failure_reason 를 여기로 흡수한다(사람이 읽는 실패 사유라 로그가 맞음, 매핑표 참조).
    overview_levels 는 전용 컬럼화되어 더 이상 합본 대상이 아니다.
    """
    parts: list[str] = []
    if result.log:
        parts.append(result.log)
    if result.failure_reason:
        parts.append(f"[FAILURE] {result.failure_reason}")
    return "\n".join(parts)


# ─────────────────────────────────────────────────────────────
# 구체 구현 — S3 (v1.0 운영). boto3 지연 임포트(이식성·테스트 무의존).
#   ★ 실제 S3 왕복은 이 개발 환경에서 검증 불가 — EC2 리허설(§18 D35)에서 실측한다.
#   ★ 키 규약: COG=cog/{slide_id}.tif, minimap=minimap/{slide_id}.png,
#     thumbnail=thumbnail/{slide_id}.jpg (server_render 의 s3_key 소비 경로와 정합).
# ─────────────────────────────────────────────────────────────
DEFAULT_BUCKET = "slideatlas-slides"


def _s3_client():
    """boto3 S3 클라이언트(지연 임포트). 리전은 환경/인스턴스 롤에 위임."""
    import boto3  # type: ignore
    return boto3.client("s3", region_name=os.environ.get("AWS_REGION", "ap-northeast-2"))


class S3SourceReader(SourceReader):
    """원본 S3 객체 → 로컬 임시 파일. download_file 은 멀티파트 스트리밍(전체 메모리 로드 안 함)."""

    def __init__(self, default_bucket: Optional[str] = None, workdir: Optional[str] = None):
        self._bucket = default_bucket or os.environ.get("AWS_S3_BUCKET", DEFAULT_BUCKET)
        self._workdir = workdir

    def fetch_to_local(self, bucket: Optional[str], key: str) -> str:
        import tempfile
        b = bucket or self._bucket
        root = self._workdir or tempfile.mkdtemp(prefix="cog_src_")
        os.makedirs(root, exist_ok=True)
        local_path = os.path.join(root, os.path.basename(key) or "source")
        _s3_client().download_file(b, key, local_path)  # 스트리밍 다운로드
        return local_path


class S3ArtifactWriter(ArtifactWriter):
    """산출물 → S3 업로드. upload_file 은 멀티파트(대용량 COG 스트리밍 업로드)."""

    def __init__(self, bucket: Optional[str] = None):
        self._bucket = bucket or os.environ.get("AWS_S3_BUCKET", DEFAULT_BUCKET)

    def _put(self, key: str, local_path: str, content_type: str) -> str:
        _s3_client().upload_file(
            local_path, self._bucket, key,
            ExtraArgs={"ContentType": content_type},
        )
        return key

    def put_cog(self, slide_id: str, local_path: str) -> str:
        return self._put(f"cog/{slide_id}.tif", local_path, "image/tiff")

    def put_minimap(self, slide_id: str, local_path: str) -> str:
        return self._put(f"minimap/{slide_id}.png", local_path, "image/png")

    def put_thumbnail(self, slide_id: str, local_path: str) -> str:
        return self._put(f"thumbnail/{slide_id}.jpg", local_path, "image/jpeg")
