"""配置加载（方案 §13）。

外部地址、Token、Collection、模型和数据路径没有代码默认值，缺失时启动检查必须
失败并列出精确缺失项。算法类参数有方案 §13 定义的默认值。
"""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

_ENV_PREFIX = "SHIJIAJING"

# 仅算法类参数有默认值；外部资源标识不提供代码默认值（方案 §13）。
_DEFAULTS: dict[str, str] = {
    "VISION_TIMEOUT_SECONDS": "30",
    "TEXT_MODEL_TIMEOUT_SECONDS": "15",
    "RETRIEVAL_TIMEOUT_SECONDS": "3",
    "TURN_TIMEOUT_SECONDS": "60",
    "VISION_CACHE_TTL_SECONDS": "2592000",
    "INTENT_CACHE_TTL_SECONDS": "604800",
    "QUERY_REWRITE_CACHE_TTL_SECONDS": "604800",
    "RETRIEVAL_CACHE_TTL_SECONDS": "300",
    "EXPLANATION_CACHE_TTL_SECONDS": "86400",
    "POSTGRES_POOL_MIN_SIZE": "1",
    "POSTGRES_POOL_MAX_SIZE": "4",
    "POSTGRES_POOL_TIMEOUT_SECONDS": "30",
    "MAX_MODEL_REPAIRS": "2",
    "MAX_NETWORK_ATTEMPTS": "2",
    "RETRIEVAL_TOP_K_PER_CHANNEL": "100",
    "RETRIEVAL_UNION_LIMIT": "200",
    "MATCHING_CANDIDATE_LIMIT": "60",
    "PRODUCT_CANONICALIZATION_BATCH_SIZE": "20",
    "PRODUCT_CANONICALIZATION_MIN_CONFIDENCE": "0.75",
    "PRODUCT_CANONICALIZATION_CACHE_TTL_SECONDS": "604800",
    "PRODUCT_CANONICALIZATION_MODE": "taxonomy",
    "DYNAMIC_SCHEMA_BATCH_SIZE": "60",
    "DYNAMIC_SCHEMA_CONCEPT_MIN_CONFIDENCE": "0.90",
    "DYNAMIC_SCHEMA_ROLE_MIN_CONFIDENCE": "0.90",
    "DYNAMIC_SCHEMA_ROLE_MIN_SUPPORT": "2",
    "DYNAMIC_SCHEMA_MAX_CONCEPTS": "16",
    "DYNAMIC_SCHEMA_MAX_ATTRIBUTES_PER_CONCEPT": "64",
    "DYNAMIC_SCHEMA_CACHE_TTL_SECONDS": "604800",
    "DYNAMIC_CANONICALIZATION_BATCH_SIZE": "20",
    "DYNAMIC_CANONICALIZATION_FIELD_MIN_CONFIDENCE": "0.80",
    "DYNAMIC_SAME_ITEM_ACCEPT_THRESHOLD": "0.88",
    "DYNAMIC_SAME_ITEM_REVIEW_THRESHOLD": "0.74",
    "BRAND_HARD_FILTER_CONFIDENCE": "0.85",
    "MODEL_HARD_FILTER_CONFIDENCE": "0.90",
    "SAME_ITEM_ACCEPT_THRESHOLD": "0.82",
    "SAME_ITEM_REVIEW_THRESHOLD": "0.68",
    "RECOGNITION_REVIEW_THRESHOLD": "0.70",
    "MEMORY_RECALL_LIMIT": "20",
    "RECENT_TURNS_LIMIT": "6",
    "RECENT_TURNS_MAX_BYTES": "65536",
    "MEMORY_MUTATION_LEDGER_RETENTION_DAYS": "90",
    "RETRIEVAL_RRF_K": "60",
    "RETRIEVAL_RERANK_LIMIT": "60",
    "MAX_AGENT_TASKS": "32",
    "MAX_SUPERVISOR_REPLANS": "2",
    "AGENT_TASK_TIMEOUT_SECONDS": "30",
    "SUPERVISOR_PLANNER_MODE": "off",
    "SUPERVISOR_PLANNER_TIMEOUT_SECONDS": "8",
    "SUPERVISOR_PLANNER_MAX_REPAIRS": "1",
    "SUPERVISOR_PLANNER_MAX_TOKENS": "1500",
}

# 外部资源：缺失时必须启动失败（无默认值）
_REQUIRED_FOR_REAL_ADAPTERS = (
    "ARK_API_KEY",
    "ARK_BASE_URL",
    "ARK_VISION_MODEL",
    "ARK_TEXT_MODEL",
    "CHECKPOINT_BACKEND",
    "CHECKPOINT_DSN",
    "TRACE_BACKEND",
)

_MILVUS_REQUIRED = ("MILVUS_URI", "MILVUS_TOKEN", "MILVUS_COLLECTION")
_ENVIRONMENTS = {"dev", "test", "prod"}


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
    supervisor_model: str | None = None
    supervisor_planner_mode: str = "off"
    supervisor_planner_timeout_seconds: float = 8.0
    supervisor_planner_max_repairs: int = 1
    supervisor_planner_max_tokens: int = 1500
    max_agent_tasks: int = 32
    max_supervisor_replans: int = 2
    agent_task_timeout_seconds: float = 30.0
    request_ledger_backend: str = "disabled"
    request_ledger_dsn: str | None = None
    trace_backend: str = "structlog"
    trace_dsn: str | None = None
    taxonomy_path: str | None = None
    local_product_snapshot_path: str | None = None

    vision_timeout_seconds: float = 30.0
    text_model_timeout_seconds: float = 15.0
    retrieval_timeout_seconds: float = 3.0
    turn_timeout_seconds: float = 60.0
    vision_cache_ttl_seconds: int = 2_592_000
    intent_cache_ttl_seconds: int = 604_800
    query_rewrite_cache_ttl_seconds: int = 604_800
    retrieval_cache_ttl_seconds: int = 300
    explanation_cache_ttl_seconds: int = 86_400
    postgres_pool_min_size: int = 1
    postgres_pool_max_size: int = 4
    postgres_pool_timeout_seconds: float = 30.0
    max_model_repairs: int = 2
    max_network_attempts: int = 2
    retrieval_top_k_per_channel: int = 100
    retrieval_union_limit: int = 200
    matching_candidate_limit: int = 60
    product_canonicalization_enabled: bool = True
    product_canonicalization_mode: str = "taxonomy"
    product_canonicalization_batch_size: int = 20
    product_canonicalization_min_confidence: float = 0.75
    product_canonicalization_cache_ttl_seconds: int = 604_800
    dynamic_schema_batch_size: int = 60
    dynamic_schema_concept_min_confidence: float = 0.90
    dynamic_schema_role_min_confidence: float = 0.90
    dynamic_schema_role_min_support: int = 2
    dynamic_schema_max_concepts: int = 16
    dynamic_schema_max_attributes_per_concept: int = 64
    dynamic_schema_cache_ttl_seconds: int = 604_800
    dynamic_canonicalization_batch_size: int = 20
    dynamic_canonicalization_field_min_confidence: float = 0.80
    dynamic_same_item_accept_threshold: float = 0.88
    dynamic_same_item_review_threshold: float = 0.74
    brand_hard_filter_confidence: float = 0.85
    model_hard_filter_confidence: float = 0.90
    same_item_accept_threshold: float = 0.82
    same_item_review_threshold: float = 0.68
    memory_enabled: bool = False
    memory_recall_enabled: bool = True
    memory_commit_enabled: bool = True
    memory_backend: str = "disabled"
    memory_dsn: str | None = None
    memory_recall_limit: int = 20
    recent_turns_limit: int = 6
    recent_turns_max_bytes: int = 65_536
    memory_purge_enabled: bool = False
    memory_mutation_ledger_retention_days: int = 90
    hitl_enabled: bool = False
    recognition_review_threshold: float = 0.70
    memory_confirmation_required: bool = True
    cache_backend: str = "disabled"
    cache_dsn: str | None = None
    retrieval_fusion_strategy: str = "weighted"
    retrieval_rrf_k: int = 60
    retrieval_rerank_limit: int = 60
    retrieval_rerank_enabled: bool = False
    retrieval_index_version: str | None = None
    event_store_backend: str = "disabled"
    event_store_dsn: str | None = None

    # 偏好权重表配置化、版本化并进入 trace。
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
            milvus_configured = all(
                getattr(self, _to_attr(name)) not in (None, "") for name in _MILVUS_REQUIRED
            )
            snapshot_configured = self.local_product_snapshot_path not in (None, "")
            if not milvus_configured and not snapshot_configured:
                missing.extend((*_MILVUS_REQUIRED, "LOCAL_PRODUCT_SNAPSHOT_PATH"))
            if milvus_configured and self.embedding_model in (None, ""):
                missing.append("EMBEDDING_MODEL")
            if self.supervisor_planner_mode != "off" and not self.supervisor_model:
                missing.append("SUPERVISOR_MODEL")
        return missing

    def missing_models(self) -> list[str]:
        """模型相关配置缺失项（Fake 模式不需要）。"""
        missing: list[str] = []
        for name in ("ark_api_key", "ark_base_url", "ark_vision_model", "ark_text_model"):
            if getattr(self, name) in (None, ""):
                missing.append(name.upper())
        return missing

    def validate_engineering(self) -> list[str]:
        """校验二期 runtime 的枚举、DSN 和跨字段约束，返回精确字段名。"""
        errors: list[str] = []

        def require_finite_positive(name: str, value: float) -> None:
            if not math.isfinite(value) or value <= 0:
                errors.append(name)

        def require_finite_unit(name: str, value: float) -> None:
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                errors.append(name)

        def require_nonnegative(name: str, value: int) -> None:
            if value < 0:
                errors.append(name)

        def require_positive(name: str, value: int) -> None:
            if value < 1:
                errors.append(name)

        if self.env not in _ENVIRONMENTS:
            errors.append(f"ENV={self.env}")
        if self.supervisor_planner_mode not in {"off", "shadow", "active_replan", "active"}:
            errors.append(f"SUPERVISOR_PLANNER_MODE={self.supervisor_planner_mode}")
        if self.supervisor_planner_mode != "off" and not self.supervisor_model:
            errors.append("SUPERVISOR_MODEL")
        if self.checkpoint_backend not in {"sqlite", "postgres"}:
            errors.append(f"CHECKPOINT_BACKEND={self.checkpoint_backend}")
        if self.checkpoint_backend in {"sqlite", "postgres"} and not self.checkpoint_dsn:
            errors.append("CHECKPOINT_DSN")
        if self.trace_backend not in {"structlog", "opentelemetry"}:
            errors.append(f"TRACE_BACKEND={self.trace_backend}")
        if self.trace_backend == "opentelemetry" and not self.trace_dsn:
            errors.append("TRACE_DSN")
        for name, value in (
            ("REQUEST_LEDGER_BACKEND", self.request_ledger_backend),
            ("MEMORY_BACKEND", self.memory_backend),
            ("CACHE_BACKEND", self.cache_backend),
            ("EVENT_STORE_BACKEND", self.event_store_backend),
        ):
            allowed = {"disabled", "sqlite", "postgres"}
            if name == "CACHE_BACKEND":
                allowed.add("memory")
            if value not in allowed:
                errors.append(f"{name}={value}")
        if self.request_ledger_backend in {"sqlite", "postgres"} and not (
            self.request_ledger_dsn or self.checkpoint_dsn
        ):
            errors.append("REQUEST_LEDGER_DSN")
        if self.memory_enabled and self.memory_backend == "disabled":
            errors.append("MEMORY_BACKEND")
        if self.memory_enabled and self.memory_commit_enabled and not self.memory_recall_enabled:
            errors.append("MEMORY_COMMIT_REQUIRES_RECALL")
        if self.memory_backend in {"sqlite", "postgres"} and not self.memory_dsn:
            errors.append("MEMORY_DSN")
        if self.cache_backend in {"sqlite", "postgres"} and not self.cache_dsn:
            errors.append("CACHE_DSN")
        if self.event_store_backend in {"sqlite", "postgres"} and not self.event_store_dsn:
            errors.append("EVENT_STORE_DSN")
        if self.env == "prod" and self.event_store_backend == "disabled":
            errors.append("EVENT_STORE_BACKEND")
        if self.retrieval_fusion_strategy not in {"weighted", "rrf"}:
            errors.append(f"RETRIEVAL_FUSION_STRATEGY={self.retrieval_fusion_strategy}")
        if self.product_canonicalization_mode not in {
            "taxonomy",
            "dynamic_shadow",
            "hybrid",
            "dynamic",
        }:
            errors.append(f"PRODUCT_CANONICALIZATION_MODE={self.product_canonicalization_mode}")
        for name, value in (
            ("VISION_TIMEOUT_SECONDS", self.vision_timeout_seconds),
            ("TEXT_MODEL_TIMEOUT_SECONDS", self.text_model_timeout_seconds),
            ("RETRIEVAL_TIMEOUT_SECONDS", self.retrieval_timeout_seconds),
            ("TURN_TIMEOUT_SECONDS", self.turn_timeout_seconds),
            ("POSTGRES_POOL_TIMEOUT_SECONDS", self.postgres_pool_timeout_seconds),
            ("AGENT_TASK_TIMEOUT_SECONDS", self.agent_task_timeout_seconds),
            ("SUPERVISOR_PLANNER_TIMEOUT_SECONDS", self.supervisor_planner_timeout_seconds),
        ):
            require_finite_positive(name, value)
        for name, value in (
            ("VISION_CACHE_TTL_SECONDS", self.vision_cache_ttl_seconds),
            ("INTENT_CACHE_TTL_SECONDS", self.intent_cache_ttl_seconds),
            ("QUERY_REWRITE_CACHE_TTL_SECONDS", self.query_rewrite_cache_ttl_seconds),
            ("RETRIEVAL_CACHE_TTL_SECONDS", self.retrieval_cache_ttl_seconds),
            ("EXPLANATION_CACHE_TTL_SECONDS", self.explanation_cache_ttl_seconds),
            (
                "PRODUCT_CANONICALIZATION_CACHE_TTL_SECONDS",
                self.product_canonicalization_cache_ttl_seconds,
            ),
            ("DYNAMIC_SCHEMA_CACHE_TTL_SECONDS", self.dynamic_schema_cache_ttl_seconds),
        ):
            require_positive(name, value)
        for name, value in (
            ("BRAND_HARD_FILTER_CONFIDENCE", self.brand_hard_filter_confidence),
            ("MODEL_HARD_FILTER_CONFIDENCE", self.model_hard_filter_confidence),
            ("SAME_ITEM_ACCEPT_THRESHOLD", self.same_item_accept_threshold),
            ("SAME_ITEM_REVIEW_THRESHOLD", self.same_item_review_threshold),
            ("RECOGNITION_REVIEW_THRESHOLD", self.recognition_review_threshold),
            (
                "PRODUCT_CANONICALIZATION_MIN_CONFIDENCE",
                self.product_canonicalization_min_confidence,
            ),
            ("DYNAMIC_SCHEMA_CONCEPT_MIN_CONFIDENCE", self.dynamic_schema_concept_min_confidence),
            ("DYNAMIC_SCHEMA_ROLE_MIN_CONFIDENCE", self.dynamic_schema_role_min_confidence),
            (
                "DYNAMIC_CANONICALIZATION_FIELD_MIN_CONFIDENCE",
                self.dynamic_canonicalization_field_min_confidence,
            ),
            ("DYNAMIC_SAME_ITEM_ACCEPT_THRESHOLD", self.dynamic_same_item_accept_threshold),
            ("DYNAMIC_SAME_ITEM_REVIEW_THRESHOLD", self.dynamic_same_item_review_threshold),
        ):
            require_finite_unit(name, value)
        for name, value in (
            ("MAX_MODEL_REPAIRS", self.max_model_repairs),
            ("MAX_NETWORK_ATTEMPTS", self.max_network_attempts),
        ):
            require_nonnegative(name, value)
        for name, value in (
            ("RETRIEVAL_TOP_K_PER_CHANNEL", self.retrieval_top_k_per_channel),
            ("RETRIEVAL_UNION_LIMIT", self.retrieval_union_limit),
            ("MATCHING_CANDIDATE_LIMIT", self.matching_candidate_limit),
            (
                "PRODUCT_CANONICALIZATION_BATCH_SIZE",
                self.product_canonicalization_batch_size,
            ),
            ("DYNAMIC_SCHEMA_BATCH_SIZE", self.dynamic_schema_batch_size),
            ("DYNAMIC_SCHEMA_ROLE_MIN_SUPPORT", self.dynamic_schema_role_min_support),
            ("DYNAMIC_SCHEMA_MAX_CONCEPTS", self.dynamic_schema_max_concepts),
            (
                "DYNAMIC_SCHEMA_MAX_ATTRIBUTES_PER_CONCEPT",
                self.dynamic_schema_max_attributes_per_concept,
            ),
            ("DYNAMIC_CANONICALIZATION_BATCH_SIZE", self.dynamic_canonicalization_batch_size),
            ("MEMORY_RECALL_LIMIT", self.memory_recall_limit),
            ("RECENT_TURNS_LIMIT", self.recent_turns_limit),
            ("RECENT_TURNS_MAX_BYTES", self.recent_turns_max_bytes),
            (
                "MEMORY_MUTATION_LEDGER_RETENTION_DAYS",
                self.memory_mutation_ledger_retention_days,
            ),
            ("RETRIEVAL_RRF_K", self.retrieval_rrf_k),
            ("RETRIEVAL_RERANK_LIMIT", self.retrieval_rerank_limit),
            ("MAX_AGENT_TASKS", self.max_agent_tasks),
            ("MAX_SUPERVISOR_REPLANS", self.max_supervisor_replans),
            ("SUPERVISOR_PLANNER_MAX_REPAIRS", self.supervisor_planner_max_repairs),
            ("SUPERVISOR_PLANNER_MAX_TOKENS", self.supervisor_planner_max_tokens),
        ):
            require_positive(name, value)
        if self.same_item_review_threshold > self.same_item_accept_threshold:
            errors.append("SAME_ITEM_THRESHOLD_ORDER")
        if self.dynamic_same_item_review_threshold > self.dynamic_same_item_accept_threshold:
            errors.append("DYNAMIC_SAME_ITEM_THRESHOLD_ORDER")
        if self.postgres_pool_min_size < 1:
            errors.append("POSTGRES_POOL_MIN_SIZE")
        if self.postgres_pool_max_size < self.postgres_pool_min_size:
            errors.append("POSTGRES_POOL_MAX_SIZE")
        return errors

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
        try:
            return float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"配置错误：{_env_name(name)} 必须是数字") from exc

    def getb(name: str, default: bool) -> bool:
        raw = env_source.get(_env_name(name))
        if raw is None or not raw.strip():
            return default
        normalized = raw.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        raise ValueError(f"{_env_name(name)} 只能是 true/false")

    def geti(name: str) -> int:
        raw = env_source.get(_env_name(name))
        if raw is None or not raw.strip():
            raw = _DEFAULTS[name]
        try:
            return int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"配置错误：{_env_name(name)} 必须是整数") from exc

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
        supervisor_model=get("SUPERVISOR_MODEL"),
        supervisor_planner_mode=get("SUPERVISOR_PLANNER_MODE") or "off",
        supervisor_planner_timeout_seconds=getf("SUPERVISOR_PLANNER_TIMEOUT_SECONDS"),
        supervisor_planner_max_repairs=geti("SUPERVISOR_PLANNER_MAX_REPAIRS"),
        supervisor_planner_max_tokens=geti("SUPERVISOR_PLANNER_MAX_TOKENS"),
        max_agent_tasks=geti("MAX_AGENT_TASKS"),
        max_supervisor_replans=geti("MAX_SUPERVISOR_REPLANS"),
        agent_task_timeout_seconds=getf("AGENT_TASK_TIMEOUT_SECONDS"),
        request_ledger_backend=get("REQUEST_LEDGER_BACKEND") or "sqlite",
        request_ledger_dsn=get("REQUEST_LEDGER_DSN"),
        trace_backend=get("TRACE_BACKEND") or "structlog",
        trace_dsn=get("TRACE_DSN"),
        taxonomy_path=get("TAXONOMY_PATH"),
        local_product_snapshot_path=get("LOCAL_PRODUCT_SNAPSHOT_PATH"),
        vision_timeout_seconds=getf("VISION_TIMEOUT_SECONDS"),
        text_model_timeout_seconds=getf("TEXT_MODEL_TIMEOUT_SECONDS"),
        retrieval_timeout_seconds=getf("RETRIEVAL_TIMEOUT_SECONDS"),
        turn_timeout_seconds=getf("TURN_TIMEOUT_SECONDS"),
        vision_cache_ttl_seconds=geti("VISION_CACHE_TTL_SECONDS"),
        intent_cache_ttl_seconds=geti("INTENT_CACHE_TTL_SECONDS"),
        query_rewrite_cache_ttl_seconds=geti("QUERY_REWRITE_CACHE_TTL_SECONDS"),
        retrieval_cache_ttl_seconds=geti("RETRIEVAL_CACHE_TTL_SECONDS"),
        explanation_cache_ttl_seconds=geti("EXPLANATION_CACHE_TTL_SECONDS"),
        postgres_pool_min_size=geti("POSTGRES_POOL_MIN_SIZE"),
        postgres_pool_max_size=geti("POSTGRES_POOL_MAX_SIZE"),
        postgres_pool_timeout_seconds=getf("POSTGRES_POOL_TIMEOUT_SECONDS"),
        max_model_repairs=geti("MAX_MODEL_REPAIRS"),
        max_network_attempts=geti("MAX_NETWORK_ATTEMPTS"),
        retrieval_top_k_per_channel=geti("RETRIEVAL_TOP_K_PER_CHANNEL"),
        retrieval_union_limit=geti("RETRIEVAL_UNION_LIMIT"),
        matching_candidate_limit=geti("MATCHING_CANDIDATE_LIMIT"),
        product_canonicalization_enabled=getb("PRODUCT_CANONICALIZATION_ENABLED", True),
        product_canonicalization_mode=(
            get("PRODUCT_CANONICALIZATION_MODE") or _DEFAULTS["PRODUCT_CANONICALIZATION_MODE"]
        ),
        product_canonicalization_batch_size=geti("PRODUCT_CANONICALIZATION_BATCH_SIZE"),
        product_canonicalization_min_confidence=getf("PRODUCT_CANONICALIZATION_MIN_CONFIDENCE"),
        product_canonicalization_cache_ttl_seconds=geti(
            "PRODUCT_CANONICALIZATION_CACHE_TTL_SECONDS"
        ),
        dynamic_schema_batch_size=geti("DYNAMIC_SCHEMA_BATCH_SIZE"),
        dynamic_schema_concept_min_confidence=getf("DYNAMIC_SCHEMA_CONCEPT_MIN_CONFIDENCE"),
        dynamic_schema_role_min_confidence=getf("DYNAMIC_SCHEMA_ROLE_MIN_CONFIDENCE"),
        dynamic_schema_role_min_support=geti("DYNAMIC_SCHEMA_ROLE_MIN_SUPPORT"),
        dynamic_schema_max_concepts=geti("DYNAMIC_SCHEMA_MAX_CONCEPTS"),
        dynamic_schema_max_attributes_per_concept=geti("DYNAMIC_SCHEMA_MAX_ATTRIBUTES_PER_CONCEPT"),
        dynamic_schema_cache_ttl_seconds=geti("DYNAMIC_SCHEMA_CACHE_TTL_SECONDS"),
        dynamic_canonicalization_batch_size=geti("DYNAMIC_CANONICALIZATION_BATCH_SIZE"),
        dynamic_canonicalization_field_min_confidence=getf(
            "DYNAMIC_CANONICALIZATION_FIELD_MIN_CONFIDENCE"
        ),
        dynamic_same_item_accept_threshold=getf("DYNAMIC_SAME_ITEM_ACCEPT_THRESHOLD"),
        dynamic_same_item_review_threshold=getf("DYNAMIC_SAME_ITEM_REVIEW_THRESHOLD"),
        brand_hard_filter_confidence=getf("BRAND_HARD_FILTER_CONFIDENCE"),
        model_hard_filter_confidence=getf("MODEL_HARD_FILTER_CONFIDENCE"),
        same_item_accept_threshold=getf("SAME_ITEM_ACCEPT_THRESHOLD"),
        same_item_review_threshold=getf("SAME_ITEM_REVIEW_THRESHOLD"),
        memory_enabled=getb("MEMORY_ENABLED", False),
        memory_recall_enabled=getb("MEMORY_RECALL_ENABLED", True),
        memory_commit_enabled=getb("MEMORY_COMMIT_ENABLED", True),
        memory_backend=get("MEMORY_BACKEND") or "disabled",
        memory_dsn=get("MEMORY_DSN"),
        memory_recall_limit=geti("MEMORY_RECALL_LIMIT"),
        recent_turns_limit=geti("RECENT_TURNS_LIMIT"),
        recent_turns_max_bytes=geti("RECENT_TURNS_MAX_BYTES"),
        memory_purge_enabled=getb("MEMORY_PURGE_ENABLED", False),
        memory_mutation_ledger_retention_days=geti("MEMORY_MUTATION_LEDGER_RETENTION_DAYS"),
        hitl_enabled=getb("HITL_ENABLED", False),
        recognition_review_threshold=getf("RECOGNITION_REVIEW_THRESHOLD"),
        memory_confirmation_required=getb("MEMORY_CONFIRMATION_REQUIRED", True),
        cache_backend=get("CACHE_BACKEND") or "disabled",
        cache_dsn=get("CACHE_DSN"),
        retrieval_fusion_strategy=get("RETRIEVAL_FUSION_STRATEGY") or "weighted",
        retrieval_rrf_k=geti("RETRIEVAL_RRF_K"),
        retrieval_rerank_limit=geti("RETRIEVAL_RERANK_LIMIT"),
        retrieval_rerank_enabled=getb("RETRIEVAL_RERANK_ENABLED", False),
        retrieval_index_version=get("RETRIEVAL_INDEX_VERSION"),
        event_store_backend=get("EVENT_STORE_BACKEND") or "disabled",
        event_store_dsn=get("EVENT_STORE_DSN"),
        preference_weights={
            "lowest_price": {"price_utility": 0.35, "intent_relevance": 0.25},
            "official_store": {"seller_trust": 0.25, "intent_relevance": 0.25},
            "high_rating": {"rating_quality": 0.25, "intent_relevance": 0.25},
            "high_sales": {"sales_quality": 0.20, "intent_relevance": 0.25},
            "fast_delivery": {"freshness": 0.25, "intent_relevance": 0.25},
        },
    )
