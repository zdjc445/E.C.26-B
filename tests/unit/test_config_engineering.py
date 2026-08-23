"""二期环境枚举和生产 Event Store 配置契约。"""

from __future__ import annotations

import pytest

from shijiajing_agent.config import Settings, load_settings


def test_environment_names_are_exact() -> None:
    assert load_settings({"SHIJIAJING_ENV": "prod"}).env == "prod"
    assert Settings(env="dev", checkpoint_dsn="checkpoint.db").validate_engineering() == []
    assert Settings(env="test", checkpoint_dsn="checkpoint.db").validate_engineering() == []


def test_unknown_environment_is_rejected() -> None:
    errors = Settings(env="production").validate_engineering()
    assert "ENV=production" in errors
    assert "CHECKPOINT_DSN" in errors


def test_checkpoint_dsn_is_required_for_legacy_and_native_backends() -> None:
    for mode in ("legacy", "native"):
        errors = Settings(graph_persistence_mode=mode).validate_engineering()
        assert errors.count("CHECKPOINT_DSN") == 1


def test_production_requires_persistent_event_store() -> None:
    settings = Settings(env="prod")
    assert "EVENT_STORE_BACKEND" in settings.validate_engineering()
    configured = Settings(
        env="prod",
        checkpoint_dsn="checkpoint.db",
        event_store_backend="sqlite",
        event_store_dsn="events.db",
    )
    assert configured.validate_engineering() == []


def test_postgres_pool_settings_are_loaded_and_validated() -> None:
    settings = load_settings(
        {
            "SHIJIAJING_POSTGRES_POOL_MIN_SIZE": "2",
            "SHIJIAJING_POSTGRES_POOL_MAX_SIZE": "8",
            "SHIJIAJING_POSTGRES_POOL_TIMEOUT_SECONDS": "12.5",
            "SHIJIAJING_VISION_CACHE_TTL_SECONDS": "3600",
            "SHIJIAJING_INTENT_CACHE_TTL_SECONDS": "1800",
            "SHIJIAJING_QUERY_REWRITE_CACHE_TTL_SECONDS": "900",
            "SHIJIAJING_RETRIEVAL_CACHE_TTL_SECONDS": "300",
            "SHIJIAJING_EXPLANATION_CACHE_TTL_SECONDS": "600",
        }
    )
    assert settings.postgres_pool_min_size == 2
    assert settings.postgres_pool_max_size == 8
    assert settings.postgres_pool_timeout_seconds == 12.5
    assert settings.vision_cache_ttl_seconds == 3600
    assert settings.intent_cache_ttl_seconds == 1800
    assert settings.query_rewrite_cache_ttl_seconds == 900
    assert settings.retrieval_cache_ttl_seconds == 300
    assert settings.explanation_cache_ttl_seconds == 600

    invalid = Settings(
        checkpoint_dsn="checkpoint.db",
        postgres_pool_min_size=0,
        postgres_pool_max_size=-1,
        postgres_pool_timeout_seconds=0,
    )
    errors = invalid.validate_engineering()
    assert "POSTGRES_POOL_MIN_SIZE" in errors
    assert "POSTGRES_POOL_MAX_SIZE" in errors
    assert "POSTGRES_POOL_TIMEOUT_SECONDS" in errors


def test_memory_rollout_flags_are_loaded_and_commit_requires_recall() -> None:
    settings = load_settings(
        {
            "SHIJIAJING_MEMORY_RECALL_ENABLED": "true",
            "SHIJIAJING_MEMORY_COMMIT_ENABLED": "false",
        }
    )
    assert settings.memory_recall_enabled is True
    assert settings.memory_commit_enabled is False

    invalid = Settings(
        checkpoint_dsn="checkpoint.db",
        memory_enabled=True,
        memory_recall_enabled=False,
        memory_commit_enabled=True,
        memory_backend="sqlite",
        memory_dsn="memory.db",
    )
    assert "MEMORY_COMMIT_REQUIRES_RECALL" in invalid.validate_engineering()


def test_numeric_engineering_settings_reject_invalid_values() -> None:
    invalid = Settings(
        checkpoint_dsn="checkpoint.db",
        vision_timeout_seconds=0.0,
        text_model_timeout_seconds=float("nan"),
        retrieval_timeout_seconds=float("inf"),
        turn_timeout_seconds=-1.0,
        postgres_pool_timeout_seconds=float("nan"),
        vision_cache_ttl_seconds=0,
        intent_cache_ttl_seconds=0,
        query_rewrite_cache_ttl_seconds=0,
        retrieval_cache_ttl_seconds=0,
        explanation_cache_ttl_seconds=0,
        max_model_repairs=-1,
        max_network_attempts=-1,
        max_workflow_steps=0,
        retrieval_top_k_per_channel=0,
        retrieval_union_limit=0,
        matching_candidate_limit=0,
        brand_hard_filter_confidence=-0.1,
        model_hard_filter_confidence=1.1,
        same_item_accept_threshold=0.2,
        same_item_review_threshold=0.8,
        memory_recall_limit=0,
        recent_turns_limit=0,
        recognition_review_threshold=float("inf"),
        retrieval_rrf_k=0,
        retrieval_rerank_limit=0,
    )

    errors = invalid.validate_engineering()
    expected = {
        "VISION_TIMEOUT_SECONDS",
        "TEXT_MODEL_TIMEOUT_SECONDS",
        "RETRIEVAL_TIMEOUT_SECONDS",
        "TURN_TIMEOUT_SECONDS",
        "POSTGRES_POOL_TIMEOUT_SECONDS",
        "VISION_CACHE_TTL_SECONDS",
        "INTENT_CACHE_TTL_SECONDS",
        "QUERY_REWRITE_CACHE_TTL_SECONDS",
        "RETRIEVAL_CACHE_TTL_SECONDS",
        "EXPLANATION_CACHE_TTL_SECONDS",
        "MAX_MODEL_REPAIRS",
        "MAX_NETWORK_ATTEMPTS",
        "MAX_WORKFLOW_STEPS",
        "RETRIEVAL_TOP_K_PER_CHANNEL",
        "RETRIEVAL_UNION_LIMIT",
        "MATCHING_CANDIDATE_LIMIT",
        "BRAND_HARD_FILTER_CONFIDENCE",
        "MODEL_HARD_FILTER_CONFIDENCE",
        "SAME_ITEM_THRESHOLD_ORDER",
        "MEMORY_RECALL_LIMIT",
        "RECENT_TURNS_LIMIT",
        "RECOGNITION_REVIEW_THRESHOLD",
        "RETRIEVAL_RRF_K",
        "RETRIEVAL_RERANK_LIMIT",
    }
    assert expected.issubset(errors)


def test_numeric_engineering_settings_accept_documented_boundaries() -> None:
    valid = Settings(
        checkpoint_dsn="checkpoint.db",
        vision_timeout_seconds=0.001,
        text_model_timeout_seconds=0.001,
        retrieval_timeout_seconds=0.001,
        turn_timeout_seconds=0.001,
        vision_cache_ttl_seconds=1,
        intent_cache_ttl_seconds=1,
        query_rewrite_cache_ttl_seconds=1,
        retrieval_cache_ttl_seconds=1,
        explanation_cache_ttl_seconds=1,
        postgres_pool_min_size=1,
        postgres_pool_max_size=1,
        postgres_pool_timeout_seconds=0.001,
        max_model_repairs=0,
        max_network_attempts=0,
        max_workflow_steps=1,
        retrieval_top_k_per_channel=1,
        retrieval_union_limit=1,
        matching_candidate_limit=1,
        brand_hard_filter_confidence=0.0,
        model_hard_filter_confidence=1.0,
        same_item_accept_threshold=0.5,
        same_item_review_threshold=0.5,
        memory_recall_limit=1,
        recent_turns_limit=1,
        recognition_review_threshold=0.0,
        retrieval_rrf_k=1,
        retrieval_rerank_limit=1,
    )

    assert valid.validate_engineering() == []


def test_numeric_environment_parse_errors_name_exact_field() -> None:
    with pytest.raises(ValueError, match="SHIJIAJING_MAX_NETWORK_ATTEMPTS"):
        load_settings({"SHIJIAJING_MAX_NETWORK_ATTEMPTS": "two"})

    with pytest.raises(ValueError, match="SHIJIAJING_TURN_TIMEOUT_SECONDS"):
        load_settings({"SHIJIAJING_TURN_TIMEOUT_SECONDS": "fast"})
