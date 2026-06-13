"""
pipeline/models.py — COG 변환 파이프라인 데이터 계약 + 상태 머신 (1단계)

★ 이 파일의 ConversionJob / ConversionResult / ConversionStatus 는 **변경 금지 계약**이다(§4-3).
  트리거(HTTP/SQS/Lambda)·엔진·스토리지가 모두 이 한 가지 모양으로만 주고받는다.
  필드 추가는 가능하나(뒤에 Optional 추가), 기존 필드의 이름·의미·타입 변경은 금지.

설계 원칙(이식성):
- 순수 dataclass + enum + 원시 타입만. Flask/DB/boto3/환경변수 의존 0.
- JSON 직렬화 가능(SQS 메시지·Lambda payload로 그대로 실어 나를 수 있어야 함).
  → enum 은 .value(문자열)로, to_dict/from_dict 제공.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Dict, Any


# ─────────────────────────────────────────────────────────────
# 입력 포맷 (slides.original_format 와 동일 어휘)
# ─────────────────────────────────────────────────────────────
class InputFormat(str, Enum):
    SVS = "SVS"        # Aperio (TCGA·Motic 샘플)
    TIFF = "TIFF"      # 피라미드 TIFF (뷰웍스 LH210/LH510 운영 입력 전제)
    DCM = "DCM"        # DICOM WSI (뷰웍스 출력 가능)
    NDPI = "NDPI"      # Hamamatsu (향후)
    VSI = "VSI"        # Olympus (향후)

    @classmethod
    def coerce(cls, raw: str) -> "InputFormat":
        """파일 확장자/문자열 → InputFormat. 미지원 포맷은 ValueError(엔진이 failed 처리)."""
        return cls(str(raw or "").strip().upper())


# ─────────────────────────────────────────────────────────────
# 변환 상태 머신 (§4-5) — slides.conversion_status 와 1:1
# ─────────────────────────────────────────────────────────────
class ConversionStatus(str, Enum):
    PENDING = "pending"             # 업로드 완료, 변환 대기
    CONVERTING = "converting"       # COG 변환 중
    QC_CHECK = "qc_check"           # 자동 QC 검증 중
    READY = "ready"                 # 변환·QC 통과 (MPP 있음)
    READY_NO_MPP = "ready_no_mpp"   # 타일 정상 + MPP 추출 실패 → 배율 비활성 서빙 (종착)
    FAILED = "failed"               # 변환/QC 실패


# §4-5 전이 규칙:
#   pending → converting → qc_check → ready
#                       ↘ failed    ↘ failed  ↘ ready_no_mpp
# + 운영 경로(현행 코드 정합):
#   ready_no_mpp → pending  : 어드민 수동 MPP 입력 후 재처리 (server_render.py api_slide_set_mpp, L3917)
#   failed       → pending  : 어드민 재변환 (§15-5 "failed: 로그+재변환")
#   ready        → (종착, 전이 없음) : 배포(deploy_status)는 직교 축이라 여기서 안 다룸(§4-5·§0-4)
ALLOWED_TRANSITIONS: Dict[ConversionStatus, frozenset] = {
    ConversionStatus.PENDING:      frozenset({ConversionStatus.CONVERTING}),
    ConversionStatus.CONVERTING:   frozenset({ConversionStatus.QC_CHECK, ConversionStatus.FAILED}),
    ConversionStatus.QC_CHECK:     frozenset({ConversionStatus.READY,
                                              ConversionStatus.READY_NO_MPP,
                                              ConversionStatus.FAILED}),
    ConversionStatus.READY:        frozenset(),                       # 종착
    ConversionStatus.READY_NO_MPP: frozenset({ConversionStatus.PENDING}),  # 수동 MPP 후 재처리만
    ConversionStatus.FAILED:       frozenset({ConversionStatus.PENDING}),  # 재변환만
}


class IllegalTransition(Exception):
    """허용되지 않은 상태 전이 시도. failed→ready 같은 오전이를 코드 레벨에서 차단."""


def can_transition(frm: ConversionStatus, to: ConversionStatus) -> bool:
    return to in ALLOWED_TRANSITIONS.get(frm, frozenset())


def assert_transition(frm: ConversionStatus, to: ConversionStatus) -> None:
    """허용 단일 전이가 아니면 IllegalTransition. 엔진의 단계별 진행이 호출(pending→converting 등)."""
    if not can_transition(frm, to):
        raise IllegalTransition(f"{frm.value} → {to.value} 는 허용되지 않는 전이입니다(§4-5)")


def is_reachable(frm: ConversionStatus, to: ConversionStatus) -> bool:
    """frm 에서 to 로 **단일 정방향 변환 실행 경로**로 도달 가능한지(BFS, 복구 역간선 제외).

    ★ persist_result(⑦ update_db)용. 엔진은 pending→converting→qc_check→ready 를 메모리에서
      진행하지만 DB 행은 변환 시작 시점 상태(pending/converting)에 머물러 있다가 종착 결과로 한 번에
      UPDATE 된다. 따라서 'DB 현재상태 → 결과상태'는 단일 홉이 아니라 **경로 도달성**으로 검증한다.

    ★ 단, 복구 역간선(failed→pending, ready_no_mpp→pending — 어드민 재처리/ MPP 재입력이 *별도의*
      단일 DB UPDATE 로 수행하는 리셋)은 BFS 에서 **제외**한다. 그래야 §4-5 가 명시한 'failed→ready
      오전이'가 한 번의 persist 로 통과하지 못한다(failed 는 정방향 출구가 없어 ready 에 직접 도달 불가).
      pending/converting/qc_check 같은 in-flight 상태에서만 종착으로 도달한다.
        - pending→ready ✓(정방향)  · converting→ready ✓  · qc_check→ready_no_mpp ✓
        - failed→ready ✗(차단)     · ready_no_mpp→ready ✗(어드민이 먼저 pending 으로 리셋해야 함)
        - ready→* ✗(완전 종착, 덮어쓰기 차단)
      판별: PENDING 으로 들어가는 간선(복구 리셋)을 traversal 에서 무시한다."""
    if frm == to:
        return False
    seen = {frm}
    frontier = [frm]
    while frontier:
        nxt = []
        for s in frontier:
            for t in ALLOWED_TRANSITIONS.get(s, frozenset()):
                if t == ConversionStatus.PENDING:
                    continue  # 복구 역간선(리셋) — 정방향 경로 아님
                if t == to:
                    return True
                if t not in seen:
                    seen.add(t)
                    nxt.append(t)
        frontier = nxt
    return False


def assert_reachable(frm: ConversionStatus, to: ConversionStatus) -> None:
    """경로 도달 불가면 IllegalTransition(persist_result 의 회귀/오전이 차단)."""
    if not is_reachable(frm, to):
        raise IllegalTransition(
            f"{frm.value} → {to.value} 는 도달 불가한 상태 전이입니다(§4-5, 경로 없음)")


def resolve_terminal_status(mpp: Optional[float]) -> ConversionStatus:
    """qc_check 통과 후 종착 상태 결정.

    ★ MPP 없으면(None) READY_NO_MPP 로만 간다. 임의 기본값(0.25 등)으로 READY 를 만드는 경로는
      절대 두지 않는다(§4-1·§4-5). READY 는 mpp 가 유효한 양수일 때만 도달.
      0/음수도 무효 MPP 로 보고 READY_NO_MPP (뷰어 가드 `!SLIDE_MPP` 와 정합 — viewer.html).
    """
    if mpp is None or mpp <= 0:
        return ConversionStatus.READY_NO_MPP
    return ConversionStatus.READY


# ─────────────────────────────────────────────────────────────
# ConversionJob — 변환 요청 송장 (트리거 → 엔진, 단일 모양)
# ─────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ConversionJob:
    """변환 요청. 트리거(HTTP/SQS/Lambda)가 무엇이든 이 한 가지 모양으로 엔진에 전달된다.

    frozen=True: 잡은 불변(큐에서 재시도해도 동일 입력 보장).
    """
    slide_id: str                          # 'SA-HST-001' (slides.id)
    source_s3_key: str                     # 원본 업로드 S3 키(변환 전 SVS/TIFF/DCM 위치)
    input_format: InputFormat              # SVS|TIFF|DCM|... (slides.original_format 어휘)
    subject_code: str                      # 'HST' 등 (과목 축, slides.subject_code)
    source_bucket: Optional[str] = None    # 원본 버킷(미지정 시 storage_adapter 기본값)
    original_filename: Optional[str] = None  # 진단/로그용 원본 파일명
    requested_at: Optional[str] = None     # ISO8601 문자열(트리거 무관, 직렬화 안전)

    # ── 직렬화(SQS/Lambda 이식) ──
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["input_format"] = self.input_format.value
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ConversionJob":
        return cls(
            slide_id=d["slide_id"],
            source_s3_key=d["source_s3_key"],
            input_format=InputFormat.coerce(d["input_format"]),
            subject_code=d["subject_code"],
            source_bucket=d.get("source_bucket"),
            original_filename=d.get("original_filename"),
            requested_at=d.get("requested_at"),
        )


# ─────────────────────────────────────────────────────────────
# ConversionResult — 변환 결과 송장 (엔진 → 스토리지, 단일 모양)
# ─────────────────────────────────────────────────────────────
#
# ★★ slides 컬럼 1:1 매핑표 (storage_adapter 가 이 매핑으로 UPDATE) ★★
#   ConversionResult 필드      →  slides 컬럼          타입          비고
#   ────────────────────────────────────────────────────────────────────────────
#   slide_id                  →  id                   VARCHAR(50)   WHERE 키(갱신 대상 식별, 값 변경 안 함)
#   status                    →  conversion_status    VARCHAR(20)   §4-5 enum 값(.value)
#   mpp                       →  mpp                  FLOAT         None 허용(ready_no_mpp)
#   width                     →  width                INT
#   height                    →  height               INT
#   cog_s3_key                →  s3_key               VARCHAR(500)  변환된 COG TIFF S3 경로
#   minimap_s3_key            →  s3_minimap_key       VARCHAR(500)
#   thumbnail_s3_key          →  s3_thumbnail_key     VARCHAR(500)
#   knowledge_base            →  knowledge_base       JSONB         kb 초안(generate_kb_json) ※검수본 보존 규칙 아래
#   overview_levels           →  overview_levels      INT           COG 오버뷰 레벨 수(전용 컬럼, db/slides_overview_levels_migration.sql)
#   log                       →  conversion_log       TEXT          단계 로그(성공/실패 공통)
#   qc_passed_at              →  qc_passed_at         TIMESTAMP     ready/ready_no_mpp 도달 시각(ISO 문자열)
#   ────────────────────────────────────────────────────────────────────────────
#   ※ overview_levels 는 전용 컬럼화 예외(타일서버 매 요청 조회 운영 데이터라 자유텍스트 로그 묻기 회피).
#   ※ 전용 컬럼이 없는 필드(슬라이드 스키마 무변경 원칙):
#     failure_reason   → 전용 컬럼 없음(reject_reason 은 사람의 '배포 반려'용 §15-3, 변환 실패와 다른 축).
#                        status=failed 신호 + conversion_log 에 사유 합본으로 기록(사람이 읽는 실패 사유라 로그가 맞음).
#
#   ★ 행 생성/갱신 경계(persist_result 계약): 변환은 **기존 pending 행을 UPDATE 만** 한다(INSERT 안 함).
#     slides 행 생성 주체는 D30 배치 파서(교육용 메타: title_ko/title_en/organ_code/stain/license_source/
#     subject_code). 변환은 위 '변환 산출 컬럼'만 쓰고 교육용 메타 컬럼은 절대 건드리지 않는다.
#   ★ knowledge_base 검수본 보존: kb 는 변환이 만드는 '초안'이고, 검수자가 배포 단계에서 보완한 '최종본'이
#     있다(§5-4). 재처리(failed/ready_no_mpp → pending → 재변환) 시 초안이 검수 완료된 kb 를 덮어쓰면 안 된다.
#     (검수 여부 판별 방식은 본체 단계에서 결정 — 지금은 '재처리가 검수본을 날리지 않는다'는 불변식만 확정.)
#
@dataclass
class ConversionResult:
    """변환 결과. 엔진이 만들어 storage_adapter 가 slides 컬럼에 1:1로 꽂는다(위 매핑표).

    실패 시: status=FAILED, failure_reason 채움, COG/이미지 키·치수·mpp 는 None 가능.
    ready_no_mpp 시: mpp=None 이지만 cog/minimap/thumbnail·width·height 는 채워짐(서빙 가능).
    """
    slide_id: str
    status: ConversionStatus
    mpp: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    cog_s3_key: Optional[str] = None
    minimap_s3_key: Optional[str] = None
    thumbnail_s3_key: Optional[str] = None
    knowledge_base: Optional[Dict[str, Any]] = None
    overview_levels: Optional[int] = None      # → slides.overview_levels (전용 컬럼, 매핑표 참조)
    qc_passed_at: Optional[str] = None         # ISO8601; ready/ready_no_mpp 도달 시 설정
    log: Optional[str] = None                  # → conversion_log
    failure_reason: Optional[str] = None       # 전용 컬럼 없음 → status=failed + conversion_log

    # ── 직렬화(SQS/Lambda 이식) ──
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ConversionResult":
        d = dict(d)
        d["status"] = ConversionStatus(d["status"])
        return cls(**d)

    @classmethod
    def failed(cls, slide_id: str, reason: str, log: Optional[str] = None) -> "ConversionResult":
        """실패 결과 팩토리. 임의 MPP·치수로 채우지 않는다(§4-1)."""
        return cls(slide_id=slide_id, status=ConversionStatus.FAILED,
                   failure_reason=reason, log=log)
