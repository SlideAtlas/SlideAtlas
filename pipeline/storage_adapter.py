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

from abc import ABC, abstractmethod
from typing import Optional, Any

from .models import ConversionResult, ConversionStatus


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
    raise NotImplementedError("persist_result — 2단계 구현 예정")


def _compose_log(result: ConversionResult) -> str:
    """conversion_log 본문 합성: 단계 로그 + (실패 시) failure_reason.

    전용 컬럼이 없는 failure_reason 를 여기로 흡수한다(사람이 읽는 실패 사유라 로그가 맞음, 매핑표 참조).
    overview_levels 는 전용 컬럼화되어 더 이상 합본 대상이 아니다. TODO: 포맷 확정.
    """
    raise NotImplementedError("_compose_log — 2단계 구현 예정")
