from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "backend/src/main/resources/db/migration/V1__init_schema.sql"
REPOSITORY = ROOT / "backend/src/main/java/com/ec26b/shoppingagent/persistence/PostgresShoppingStateRepository.java"
SERVICE = ROOT / "backend/src/main/java/com/ec26b/shoppingagent/service/ShoppingService.java"
CONFIG = ROOT / "backend/src/main/resources/application.yml"


REQUIRED_TABLES = {
    "users",
    "user_sessions",
    "uploaded_images",
    "recognitions",
    "products",
    "platform_products",
    "price_records",
    "review_summaries",
    "search_tasks",
    "search_task_items",
    "search_task_refinements",
    "comparisons",
    "comparison_items",
    "recommendations",
    "recommendation_evidence",
    "favorites",
    "price_alerts",
}

REPOSITORY_WRITES = {
    "saveUser": "users",
    "saveRefreshSession": "user_sessions",
    "deleteRefreshSession": "user_sessions",
    "saveImage": "uploaded_images",
    "saveRecognition": "recognitions",
    "saveSearchTask": "search_tasks",
    "saveRefinement": "search_task_refinements",
    "saveComparison": "comparisons",
    "saveRecommendation": "recommendations",
    "saveFavorite": "favorites",
    "deleteFavorite": "favorites",
    "savePriceAlert": "price_alerts",
    "deletePriceAlert": "price_alerts",
}


def main() -> None:
    schema = SCHEMA.read_text(encoding="utf-8")
    repository = REPOSITORY.read_text(encoding="utf-8")
    service = SERVICE.read_text(encoding="utf-8")
    config = CONFIG.read_text(encoding="utf-8")

    tables = set(re.findall(r"CREATE TABLE ([a-z_]+)", schema))
    missing = sorted(REQUIRED_TABLES - tables)
    check(not missing, f"missing tables in Flyway schema: {missing}")

    for method, table in REPOSITORY_WRITES.items():
        check(f"public void {method}" in repository, f"missing repository method {method}")
        check(table in repository, f"{method} does not mention table {table}")

    schema_evidence_types = enum_values(schema, "ck_recommendation_evidence_type")
    service_evidence_types = set(re.findall(r'new RecommendationEvidenceDto\("([^"]+)"', service))
    check(
        service_evidence_types <= schema_evidence_types,
        "service emits evidence types not accepted by schema: "
        f"{sorted(service_evidence_types - schema_evidence_types)}",
    )

    source_types = enum_values(schema, "ck_platform_products_source_type")
    service_sources = set(re.findall(r'"(mock|official_api|sample_dataset)"', service))
    check(
        service_sources <= source_types,
        f"service source types not accepted by schema: {sorted(service_sources - source_types)}",
    )

    for status in ("pending", "succeeded", "failed"):
        check(status in schema, f"schema missing status {status}")

    check("POSTGRES_PERSISTENCE_FAIL_FAST:true" in config, "postgres profile must fail fast by default")
    check("POSTGRES_PERSISTENCE_FAIL_FAST:false" in config, "default profile must allow no-op persistence")
    check("if (failFast)" in repository, "Postgres repository must honor failFast")

    print("postgres persistence contract ok")


def enum_values(schema: str, constraint_name: str) -> set[str]:
    match = re.search(
        rf"CONSTRAINT {constraint_name} CHECK \([^)]* IN \(([^)]+)\)\)",
        schema,
        re.MULTILINE,
    )
    check(match is not None, f"missing constraint {constraint_name}")
    return set(re.findall(r"'([^']+)'", match.group(1)))


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


if __name__ == "__main__":
    main()
