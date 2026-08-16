"""从任务内 taxonomy.json 加载商品分类规则。"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

_MODEL_SEPARATORS = re.compile(r"[\s\-_/·]+")


@dataclass(frozen=True)
class ModelNormalizationRules:
    separator: str = "space"
    uppercase: bool = False


@dataclass(frozen=True)
class UnitRule:
    attribute: str
    unit: str
    aliases: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CategorySchema:
    category_id: str
    category_name: str
    aliases: list[str] = field(default_factory=list)
    brand_aliases: Mapping[str, str] = field(default_factory=dict)
    model_normalization_rules: ModelNormalizationRules = field(
        default_factory=ModelNormalizationRules
    )
    searchable_attributes: list[str] = field(default_factory=list)
    identity_attributes: list[str] = field(default_factory=list)
    variant_attributes: list[str] = field(default_factory=list)
    attribute_schema: Mapping[str, Mapping[str, object]] = field(default_factory=dict)


@dataclass(frozen=True)
class TaxonomyFile:
    schema_version: str
    taxonomy_version: str
    categories: list[CategorySchema] = field(default_factory=list)
    unit_rules: list[UnitRule] = field(default_factory=list)
    common_brand_aliases: Mapping[str, str] = field(default_factory=dict)


class Taxonomy:
    """只读 taxonomy 查询视图。"""

    def __init__(self, data: TaxonomyFile) -> None:
        self._data = data
        self._by_id = {category.category_id: category for category in data.categories}
        self._alias_to_id: dict[str, str] = {}
        self._brand_alias = dict(data.common_brand_aliases)
        for category in data.categories:
            for alias in category.aliases:
                self._alias_to_id.setdefault(alias, category.category_id)
            for alias, canonical in category.brand_aliases.items():
                self._brand_alias.setdefault(alias, canonical)
                self._brand_alias.setdefault(canonical, canonical)

    @property
    def schema_version(self) -> str:
        return self._data.schema_version

    @property
    def taxonomy_version(self) -> str:
        return self._data.taxonomy_version

    def categories(self) -> list[CategorySchema]:
        return list(self._data.categories)

    def category_ids(self) -> list[str]:
        return list(self._by_id)

    def category_names(self) -> list[str]:
        return [category.category_name for category in self._data.categories]

    def get_category(self, category_id: str) -> CategorySchema | None:
        return self._by_id.get(category_id)

    def resolve_category(self, raw: str | None) -> tuple[str | None, str | None]:
        if not raw:
            return None, None
        key = raw.strip()
        category = self._by_id.get(key)
        if category is not None:
            return category.category_id, category.category_name
        category_id = self._alias_to_id.get(key)
        if category_id is None:
            return None, None
        category = self._by_id[category_id]
        return category.category_id, category.category_name

    def all_brand_aliases(self) -> dict[str, str]:
        return dict(self._brand_alias)

    def normalize_brand(self, raw: str | None) -> str | None:
        if not raw:
            return None
        key = raw.strip()
        return self._brand_alias.get(key, key if len(key) >= 2 else None)

    def normalize_model(self, raw: str | None, category_id: str | None) -> str | None:
        if not raw:
            return None
        text = _MODEL_SEPARATORS.sub(" ", raw.strip())
        category = self._by_id.get(category_id or "")
        if category is not None and category.model_normalization_rules.uppercase:
            text = text.upper()
        return text if text else None

    def attribute_role(self, category_id: str, attribute: str) -> str | None:
        category = self._by_id.get(category_id)
        if category is None:
            return None
        if attribute in category.identity_attributes:
            return "identity"
        if attribute in category.variant_attributes:
            return "variant"
        if attribute in category.searchable_attributes or attribute in category.attribute_schema:
            return "descriptive"
        return None

    def validate_attribute(self, category_id: str, key: str, value: str) -> bool:
        category = self._by_id.get(category_id)
        if category is None:
            return False
        schema = category.attribute_schema.get(key)
        if schema is None:
            return False
        allowed = schema.get("enum")
        return not isinstance(allowed, list) or value in allowed

    def identity_attributes(self, category_id: str) -> list[str]:
        category = self._by_id.get(category_id)
        return list(category.identity_attributes) if category is not None else []

    def variant_attributes(self, category_id: str) -> list[str]:
        category = self._by_id.get(category_id)
        return list(category.variant_attributes) if category is not None else []


def _json_object(value: object, field_name: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field_name} must be an object with string keys")
    return dict(value)


def _required_string(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _string_list(value: object, field_name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must be a list of strings")
    return list(value)


def _string_mapping(value: object, field_name: str) -> dict[str, str]:
    data = _json_object(value, field_name)
    if not all(isinstance(item, str) for item in data.values()):
        raise ValueError(f"{field_name} values must be strings")
    return {key: item for key, item in data.items() if isinstance(item, str)}


def _parse_category(value: object) -> CategorySchema:
    data = _json_object(value, "categories[]")
    category_id = _required_string(data, "category_id")
    rules_data = _json_object(
        data.get("model_normalization_rules", {}), "model_normalization_rules"
    )
    separator = rules_data.get("separator", "space")
    uppercase = rules_data.get("uppercase", False)
    if not isinstance(separator, str):
        raise ValueError("model_normalization_rules.separator must be a string")
    if not isinstance(uppercase, bool):
        raise ValueError("model_normalization_rules.uppercase must be a boolean")

    schemas_data = _json_object(data.get("attribute_schema", {}), "attribute_schema")
    attribute_schema: dict[str, dict[str, object]] = {}
    for attribute, schema_value in schemas_data.items():
        schema = _json_object(schema_value, f"attribute_schema.{attribute}")
        type_name = _required_string(schema, "type")
        parsed_schema: dict[str, object] = {"type": type_name}
        if "enum" in schema:
            parsed_schema["enum"] = _string_list(
                schema["enum"], f"attribute_schema.{attribute}.enum"
            )
        attribute_schema[attribute] = parsed_schema

    return CategorySchema(
        category_id=category_id,
        category_name=_required_string(data, "category_name"),
        aliases=_string_list(data.get("aliases", []), f"{category_id}.aliases"),
        brand_aliases=_string_mapping(
            data.get("brand_aliases", {}), f"{category_id}.brand_aliases"
        ),
        model_normalization_rules=ModelNormalizationRules(
            separator=separator,
            uppercase=uppercase,
        ),
        searchable_attributes=_string_list(
            data.get("searchable_attributes", []), f"{category_id}.searchable_attributes"
        ),
        identity_attributes=_string_list(
            data.get("identity_attributes", []), f"{category_id}.identity_attributes"
        ),
        variant_attributes=_string_list(
            data.get("variant_attributes", []), f"{category_id}.variant_attributes"
        ),
        attribute_schema=attribute_schema,
    )


def _parse_unit_rule(value: object) -> UnitRule:
    data = _json_object(value, "unit_rules[]")
    attribute = _required_string(data, "attribute")
    return UnitRule(
        attribute=attribute,
        unit=_required_string(data, "unit"),
        aliases=_string_list(data.get("aliases", []), f"{attribute}.aliases"),
    )


def _parse_taxonomy_file(value: object) -> TaxonomyFile:
    data = _json_object(value, "taxonomy")
    category_values = data.get("categories", [])
    unit_rule_values = data.get("unit_rules", [])
    if not isinstance(category_values, list):
        raise ValueError("categories must be a list")
    if not isinstance(unit_rule_values, list):
        raise ValueError("unit_rules must be a list")
    return TaxonomyFile(
        schema_version=_required_string(data, "schema_version"),
        taxonomy_version=_required_string(data, "taxonomy_version"),
        categories=[_parse_category(item) for item in category_values],
        unit_rules=[_parse_unit_rule(item) for item in unit_rule_values],
        common_brand_aliases=_string_mapping(
            data.get("common_brand_aliases", {}), "common_brand_aliases"
        ),
    )


@lru_cache(maxsize=8)
def load_taxonomy(path: Path | None = None) -> Taxonomy:
    """从独立任务包内的 JSON 文件加载 taxonomy。"""

    taxonomy_path = path or (Path(__file__).resolve().parent / "data" / "taxonomy.json")
    with taxonomy_path.open("r", encoding="utf-8") as file:
        return Taxonomy(_parse_taxonomy_file(json.load(file)))


def default_taxonomy() -> Taxonomy:
    return load_taxonomy()
