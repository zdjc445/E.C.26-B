"""模型 Port（方案 §4.1、§11）。

Port 名称和方法签名由 Agent 工程定义，具体供应商放在 adapters/，
不得反向污染领域模型。所有模型 Port 使用 async def。
"""

from __future__ import annotations

from typing import Protocol

from shijiajing_agent.contracts import (
    ImageRef,
    IntentPatch,
    RecognitionResult,
    RetrievalQuery,
    ShoppingConstraints,
)
from shijiajing_agent.domain.evidence import EvidenceBundle
from shijiajing_agent.domain.taxonomy import Taxonomy
from shijiajing_agent.ports.lifecycle import ResourceLifecyclePort


class VisionModelPort(ResourceLifecyclePort, Protocol):
    """VLM 商品识别。输入图片、taxonomy 支持品类列表与属性 schema。"""

    async def recognize(self, image: ImageRef, taxonomy: Taxonomy) -> RecognitionResult: ...


class IntentModelPort(Protocol):
    """文本意图抽取。模型只输出当前轮 patch。"""

    async def extract_intent(
        self, text: str, prev_constraints: ShoppingConstraints | None, taxonomy: Taxonomy
    ) -> IntentPatch: ...


class QueryRewritePort(Protocol):
    """查询改写。模型只能改写 query_text 和扩展 soft_terms。"""

    async def rewrite(
        self,
        text: str,
        constraints: ShoppingConstraints | None,
        recognition: RecognitionResult | None,
    ) -> RetrievalQuery: ...


class ExplanationModelPort(Protocol):
    """事实约束的结果解释。只接收 EvidenceBundle。"""

    async def explain(self, bundle: EvidenceBundle) -> str: ...


class TextEmbeddingPort(Protocol):
    """文本向量。"""

    async def embed_texts(self, texts: list[str]) -> list[list[float]]: ...

    @property
    def dimension(self) -> int: ...


class ImageEmbeddingPort(Protocol):
    """图像向量。"""

    async def embed_image(self, image: ImageRef) -> list[float]: ...
