"""向量化适配器（方案 §13、ports/embeddings）。

- ``ArkTextEmbedding``：Ark OpenAI 兼容 ``/embeddings`` 端点，模型名来自
  ``settings.embedding_model``（不硬编码）。维度按实际模型契约确定：
  首次调用后缓存，供 Milvus 建集合时读取。
- 图像向量：spec 要求"可配置多模态 Embedding Provider"，且不得用 VLM 文本
  描述代替图像特征。未配置真实 provider 时使用 ``UnavailableImageEmbedding``，
  明确不可用（检索适配器跳过图像通道并在 channel_counts 中如实反映），
  绝不伪造图像向量。
"""

from __future__ import annotations

import httpx
from openai import AsyncOpenAI

from shijiajing_agent.config import Settings
from shijiajing_agent.contracts import ImageRef
from shijiajing_agent.errors import RetrievalUnavailableError
from shijiajing_agent.ports.models import ImageEmbeddingPort, TextEmbeddingPort


class ArkTextEmbedding:
    """Ark OpenAI 兼容文本向量（TextEmbeddingPort）。"""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not settings.embedding_model or not settings.ark_api_key or not settings.ark_base_url:
            raise ValueError(
                "embedding 配置缺失，请设置 SHIJIAJING_EMBEDDING_MODEL / "
                "SHIJIAJING_ARK_API_KEY / SHIJIAJING_ARK_BASE_URL"
            )
        self._settings = settings
        self._dimension: int | None = None
        http_client = httpx.AsyncClient(transport=transport) if transport else None
        self._client = AsyncOpenAI(
            base_url=settings.ark_base_url,
            api_key=settings.ark_api_key,
            http_client=http_client,
            max_retries=0,
        )

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            raise RuntimeError("embedding 维度未知：请先调用 embed_texts 完成首次调用")
        return self._dimension

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            resp = await self._client.embeddings.create(
                model=self._settings.embedding_model or "",
                input=texts,
                timeout=self._settings.text_model_timeout_seconds,
            )
        except Exception as exc:
            raise RetrievalUnavailableError(f"embedding 调用失败：{exc}") from exc
        vectors = [list(item.embedding) for item in resp.data]
        if self._dimension is None and vectors:
            self._dimension = len(vectors[0])
        return vectors

    async def close(self) -> None:
        await self._client.close()


class UnavailableImageEmbedding:
    """未配置多模态图像向量 provider 时的占位实现：明确不可用。

    检索适配器捕获后跳过图像通道，不把缺失图像信号当作 0 分混入融合。
    """

    async def embed_image(self, image: ImageRef) -> list[float]:
        raise RetrievalUnavailableError(
            "图像向量 provider 未配置（设置 SHIJIAJING_IMAGE_EMBEDDING_* 后接入）"
        )


def build_embedding_ports(
    settings: Settings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    image: ImageEmbeddingPort | None = None,
) -> tuple[TextEmbeddingPort, ImageEmbeddingPort]:
    """装配向量端口：文本向量必须可用；图像向量缺省为明确不可用占位。"""
    text: TextEmbeddingPort = ArkTextEmbedding(settings, transport=transport)
    return text, image or UnavailableImageEmbedding()
