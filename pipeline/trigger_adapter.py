"""
pipeline/trigger_adapter.py — 트리거 → ConversionJob 파싱 어댑터 (골격, 1단계)

목적(§4-3): 변환 트리거가 무엇이든(v1.0 HTTP / v1.5 SQS / v2.0 Lambda) 여기서 ConversionJob
한 가지 모양으로 정규화한다. conversion_engine 은 트리거를 모른다 — Job 만 받는다.
마이그레이션 시 이 파일의 어댑터만 교체하고 엔진은 무변경.

★ 본체 미구현 — 시그니처 + docstring + TODO 만. 실제 파싱/검증은 다음 단계.
"""

from __future__ import annotations

from typing import Any, Dict, List
from abc import ABC, abstractmethod

from .models import ConversionJob, InputFormat


class TriggerAdapter(ABC):
    """트리거 페이로드 → ConversionJob 리스트. 구현체별로 입력 모양만 다르다."""

    @abstractmethod
    def parse(self, raw_event: Any) -> List[ConversionJob]:
        """트리거 원본 이벤트 → ConversionJob 목록(배치 가능). 미지원/형식오류는 ValueError."""
        raise NotImplementedError


class HttpTriggerAdapter(TriggerAdapter):
    """v1.0 — 어드민 업로드 HTTP 요청을 ConversionJob 으로 파싱(골격)."""

    def parse(self, raw_event: Dict[str, Any]) -> List[ConversionJob]:
        # TODO(2단계): request JSON/form 에서 slide_id·source_s3_key·input_format·subject_code 추출.
        #   - input_format 은 InputFormat.coerce(파일 확장자) 로 정규화(미지원이면 ValueError).
        #   - 단건 업로드 → [ConversionJob] 1개. (배치 적재 D30 은 별도 어댑터/엔트리)
        #   - 환경변수·DB 참조 금지: 순수 파싱만(이식성).
        raise NotImplementedError("HttpTriggerAdapter.parse — 2단계 구현 예정")


class SqsTriggerAdapter(TriggerAdapter):
    """v1.5 — SQS 메시지(ConversionJob.to_dict JSON) 파싱. TODO."""

    def parse(self, raw_event: Dict[str, Any]) -> List[ConversionJob]:
        # TODO(v1.5): SQS Records[].body(JSON) → ConversionJob.from_dict. 배치 다건 지원.
        raise NotImplementedError("SqsTriggerAdapter — v1.5")


class LambdaTriggerAdapter(TriggerAdapter):
    """v2.0 — S3 이벤트/Lambda 직접 호출 파싱. TODO."""

    def parse(self, raw_event: Dict[str, Any]) -> List[ConversionJob]:
        # TODO(v2.0): S3 Put 이벤트에서 객체 키→slide_id 매핑 후 ConversionJob 생성.
        raise NotImplementedError("LambdaTriggerAdapter — v2.0")
