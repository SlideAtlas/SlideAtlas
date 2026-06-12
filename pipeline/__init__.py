"""
pipeline/ — SlideAtlas COG 변환 파이프라인 (§4)

1단계: 데이터 계약(ConversionJob/ConversionResult) + 상태 머신(ConversionStatus) + 4모듈 골격.
변환 엔진 본체·S3·DB 쓰기는 2단계. 변환 라이브러리는 아직 requirements 미추가.

★ ConversionJob/ConversionResult/ConversionStatus 는 변경 금지 계약(§4-3). CEO 검토 후 확정.
"""

from .models import (
    ConversionJob,
    ConversionResult,
    ConversionStatus,
    InputFormat,
    ALLOWED_TRANSITIONS,
    can_transition,
    assert_transition,
    resolve_terminal_status,
    IllegalTransition,
)

__all__ = [
    "ConversionJob",
    "ConversionResult",
    "ConversionStatus",
    "InputFormat",
    "ALLOWED_TRANSITIONS",
    "can_transition",
    "assert_transition",
    "resolve_terminal_status",
    "IllegalTransition",
]
