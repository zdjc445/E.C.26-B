"""配置加载（方案 §23）。

外部地址、Token、Collection、模型和数据路径没有代码默认值，缺失时启动检查必须
失败并列出精确缺失项。算法类参数有方案 §23 定义的默认值。
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

_ENV_PREFIX = "SHIJIAJING"

# 仅算法类参数有默认值（§23 运行参数表）
_DEFAULTS: dict[str, str] = {
    "VISION_TIMEOUT_SECONDS": "30",
    "TEXT_MODEL_TIMEOUT_SECONDS": "15",
    "RETRIEVAL_TIMEOUT_SECONDS": "3",
    "TURN_TIMEOUT_SECONDS": "60",
    "MAX_MODEL_REPAIRS": "2",
    "MAX_NETWORK_ATTEMPTS": "2",
    "MAX_WORKFLOW_STEPS": "40",
    "RETRIEVAL_TOP_K_PER_CHANNEL": "100",
    "RETRIEVAL_UNION_LIMIT": "200",
    "MATCHING_CANDIDATE_LIMIT": "60",
    "BRAND_HARD_FILTER_CONFIDENCE": "0.85",
    "MODEL_HARD_FILTER_CONFIDENCE": "0.90",
    "SAME_ITEM_ACCEPT_THRESHOLD": "0.82",
    "SAME_ITEM_REVIEW_THRESHOLD": "0.68",
}

# 外部资源：缺失时必须启动失败（无默认值）
_REQUIRED_FOR_REAL_ADAPTERS = (
    "ARK_API_KEY",
    "ARK_BASE_URL",
    "ARK_VISION_MODEL",
    "ARK_TEXT_MODEL",
    "EMBEDDING_MODEL",
    "MILVUS_URI",
    "MILVUS_TOKEN",
    "MILVUS_COLLECTION",
    "CHECKPOINT_BACKEND",
    "CHECKPOINT_DSN",
    "TRACE_BACKEND",
    "TRACE_DSN",
    "TAXONOMY_PATH",
    "LOCAL_PRODUCT_SNAPSHOT_PATH",
)


def _env_name(name: str) -> str:
    return f"{_ENV_PREFIX}_{name}"


@dataclass(frozen=True)
class Settings:
    """不可变配置对象。"""

    env: str = "dev"
    ark_api_key: str | None = None
    ark_base_url: str | None = None
    ark_vision_model: str | None = None
    ark_text_model: str | None = None
    embedding_model: str | None = None
    milvus_uri: str | None = None
    milvus_token: str | None = None
    milvus_collection: str | None = None
    checkpoint_backend: str = "sqlite"
    checkpoint_dsn: str | None = None
    trace_backend: str = "structlog"
    trace_dsn: str | None = None
    taxonomy_path: str | None = None
    local_product_snapshot_path: str | None = None

    vision_timeout_seconds: float = 30.0
    text_model_timeout_seconds: float = 15.0
    retrieval_timeout_seconds: float = 3.0
    turn_timeout_seconds: float = 60.0
    max_model_repairs: int = 2
    max_network_attempts: int = 2
    max_workflow_steps: int = 40
    retrieval_top_k_per_channel: int = 100
    retrieval_union_limit: int = 200
    matching_candidate_limit: int = 60
    brand_hard_filter_confidence: float = 0.85
    model_hard_filter_confidence: float = 0.90
    same_item_accept_threshold: float = 0.82
    same_item_review_threshold: float = 0.68

    # 偏好权重表（§15.4，配置化、版本化并进入 trace）
    preference_weights: dict[str, dict[str, float]] = field(
        default_factory=dict[str, dict[str, float]]
    )

    def validate(self, *, require_real_adapters: bool = False) -> list[str]:
        """返回缺失项列表。require_real_adapters=True 时校验外部资源。"""
        missing: list[str] = []
        if require_real_adapters:
            for name in _REQUIRED_FOR_REAL_ADAPTERS:
                if getattr(self, _to_attr(name)) in (None, ""):
                    missing.append(name)
        return missing

    def missing_models(self) -> list[str]:
        """模型相关配置缺失项（Fake 模式不需要）。"""
        missing: list[str] = []
        for name in ("ark_api_key", "ark_base_url", "ark_vision_model", "ark_text_model"):
            if getattr(self, name) in (None, ""):
                missing.append(name.upper())
        return missing

    @property
    def taxonomy_path_resolved(self) -> Path:
        return (
            Path(self.taxonomy_path)
            if self.taxonomy_path
            else Path(__file__).parent / "data" / "taxonomy.json"
        )

    @property
    def snapshot_path(self) -> Path | None:
        return Path(self.local_product_snapshot_path) if self.local_product_snapshot_path else None


def _to_attr(env_suffix: str) -> str:
    # 字段名即环境名小写（ARK_API_KEY → ark_api_key）；驼峰转换会破坏三/四段名称
    return env_suffix.lower()


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """从环境变量加载配置。env 参数用于测试注入，默认读 os.environ。"""
    env_source: Mapping[str, str] = os.environ if env is None else env

    def get(name: str) -> str | None:
        v = env_source.get(_env_name(name))
        return v.strip() if v is not None and v.strip() else None

    def getf(name: str) -> float:
        raw = env_source.get(_env_name(name))
        if raw is None or not raw.strip():
            raw = _DEFAULTS[name]
        return float(raw)

    def geti(name: str) -> int:
        raw = env_source.get(_env_name(name))
        if raw is None or not raw.strip():
            raw = _DEFAULTS[name]
        return int(raw)

    return Settings(
        env=get("ENV") or "dev",
        ark_api_key=get("ARK_API_KEY"),
        ark_base_url=get("ARK_BASE_URL"),
        ark_vision_model=get("ARK_VISION_MODEL"),
        ark_text_model=get("ARK_TEXT_MODEL"),
        embedding_model=get("EMBEDDING_MODEL"),
        milvus_uri=get("MILVUS_URI"),
        milvus_token=get("MILVUS_TOKEN"),
        milvus_collection=get("MILVUS_COLLECTION"),
        checkpoint_backend=get("CHECKPOINT_BACKEND") or "sqlite",
        checkpoint_dsn=get("CHECKPOINT_DSN"),
        trace_backend=get("TRACE_BACKEND") or "structlog",
        trace_dsn=get("TRACE_DSN"),
        taxonomy_path=get("TAXONOMY_PATH"),
        local_product_snapshot_path=get("LOCAL_PRODUCT_SNAPSHOT_PATH"),
        vision_timeout_seconds=getf("VISION_TIMEOUT_SECONDS"),
        text_model_timeout_seconds=getf("TEXT_MODEL_TIMEOUT_SECONDS"),
        retrieval_timeout_seconds=getf("RETRIEVAL_TIMEOUT_SECONDS"),
        turn_timeout_seconds=getf("TURN_TIMEOUT_SECONDS"),
        max_model_repairs=geti("MAX_MODEL_REPAIRS"),
        max_network_attempts=geti("MAX_NETWORK_ATTEMPTS"),
        max_workflow_steps=geti("MAX_WORKFLOW_STEPS"),
        retrieval_top_k_per_channel=geti("RETRIEVAL_TOP_K_PER_CHANNEL"),
        retrieval_union_limit=geti("RETRIEVAL_UNION_LIMIT"),
        matching_candidate_limit=geti("MATCHING_CANDIDATE_LIMIT"),
        brand_hard_filter_confidence=getf("BRAND_HARD_FILTER_CONFIDENCE"),
        model_hard_filter_confidence=getf("MODEL_HARD_FILTER_CONFIDENCE"),
        same_item_accept_threshold=getf("SAME_ITEM_ACCEPT_THRESHOLD"),
        same_item_review_threshold=getf("SAME_ITEM_REVIEW_THRESHOLD"),
        preference_weights={
            "lowest_price": {"price_utility": 0.35, "intent_relevance": 0.25},
            "official_store": {"seller_trust": 0.25, "intent_relevance": 0.25},
            "high_rating": {"rating_quality": 0.25, "intent_relevance": 0.25},
            "high_sales": {"sales_quality": 0.20, "intent_relevance": 0.25},
            "fast_delivery": {"freshness": 0.25, "intent_relevance": 0.25},
        },
    )
