"""Taxonomy 加载、查询与别名解析（方案 §12）。

taxonomy.json 必须版本化。实现 Agent 从确认的数据文件读取精确 ID；
本文不猜测外部商品库的 ID。
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import TypedDict

from pydantic import BaseModel, ConfigDict, Field

# 型号分隔符与空白标准化：- _ / · 统一为空格。
_MODEL_SEPARATORS = re.compile(r"[\s\-_/·]+")


class AttributeSchema(TypedDict, total=False):
    """品类属性 schema：type + 可选 enum 白名单。"""

    type: str
    enum: list[str]


class ModelNormalizationRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    separator: str = "space"
    uppercase: bool = False


class UnitRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attribute: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list[str])


class CategorySchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_id: str = Field(min_length=1)
    category_name: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list[str])
    brand_aliases: dict[str, str] = Field(default_factory=dict[str, str])
    model_normalization_rules: ModelNormalizationRules = Field(
        default_factory=ModelNormalizationRules
    )
    searchable_attributes: list[str] = Field(default_factory=list[str])
    identity_attributes: list[str] = Field(default_factory=list[str])
    variant_attributes: list[str] = Field(default_factory=list[str])
    attribute_schema: dict[str, AttributeSchema] = Field(default_factory=dict[str, AttributeSchema])


class TaxonomyFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(min_length=1)
    taxonomy_version: str = Field(min_length=1)
    categories: list[CategorySchema] = Field(default_factory=list[CategorySchema])
    unit_rules: list[UnitRule] = Field(default_factory=list[UnitRule])
    common_brand_aliases: dict[str, str] = Field(default_factory=dict[str, str])


class Taxonomy:
    """只读 taxonomy 视图。

    所有查询为同步纯函数，可安全并发读取。
    """

    def __init__(self, data: TaxonomyFile) -> None:
        self._data = data
        self._by_id: dict[str, CategorySchema] = {c.category_id: c for c in data.categories}
        self._alias_to_id: dict[str, str] = {}
        self._brand_alias: dict[str, str] = dict(data.common_brand_aliases)
        for cat in data.categories:
            for alias in cat.aliases:
                self._alias_to_id.setdefault(alias, cat.category_id)
            for alias, canonical in cat.brand_aliases.items():
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

    def get_category(self, category_id: str) -> CategorySchema | None:
        return self._by_id.get(category_id)

    def category_names(self) -> list[str]:
        return [c.category_name for c in self._data.categories]

    def resolve_category(self, raw: str | None) -> tuple[str | None, str | None]:
        """按 ID 或别名解析标准品类。返回 (category_id, category_name)。"""
        if not raw:
            return None, None
        raw = raw.strip()
        if raw in self._by_id:
            cat = self._by_id[raw]
            return cat.category_id, cat.category_name
        cat_id = self._alias_to_id.get(raw)
        if cat_id:
            cat = self._by_id[cat_id]
            return cat.category_id, cat.category_name
        return None, None

    def all_brand_aliases(self) -> dict[str, str]:
        """全部已注册品牌别名（含 canonical 自身），用于规则解析。"""
        return dict(self._brand_alias)

    def normalize_brand(self, raw: str | None) -> str | None:
        """显式品牌别名映射。不根据大小写或模糊相似度猜测未知品牌。"""
        if not raw:
            return None
        key = raw.strip()
        return self._brand_alias.get(key, key if len(key) >= 2 else None)

    def normalize_model(self, raw: str | None, category_id: str | None) -> str | None:
        """型号分隔符和空白标准化。"""
        if not raw:
            return None
        text = _MODEL_SEPARATORS.sub(" ", raw.strip())
        cat = self._by_id.get(category_id or "")
        if cat and cat.model_normalization_rules.uppercase:
            text = text.upper()
        return text if text else None

    def attribute_role(self, category_id: str, attribute: str) -> str | None:
        """返回属性角色：identity / variant / descriptive。"""
        cat = self._by_id.get(category_id)
        if not cat:
            return None
        if attribute in cat.identity_attributes:
            return "identity"
        if attribute in cat.variant_attributes:
            return "variant"
        if attribute in cat.searchable_attributes or attribute in cat.attribute_schema:
            return "descriptive"
        return None

    def validate_attribute(self, category_id: str, key: str, value: str) -> bool:
        """校验属性键属于品类 schema；enum 类型校验值。"""
        cat = self._by_id.get(category_id)
        if not cat:
            return False
        schema = cat.attribute_schema.get(key)
        if schema is None:
            return False
        allowed = schema.get("enum")
        if allowed and value not in allowed:
            return False
        return True

    def identity_attributes(self, category_id: str) -> list[str]:
        cat = self._by_id.get(category_id)
        return list(cat.identity_attributes) if cat else []

    def variant_attributes(self, category_id: str) -> list[str]:
        cat = self._by_id.get(category_id)
        return list(cat.variant_attributes) if cat else []


@lru_cache(maxsize=8)
def load_taxonomy(path: Path | None = None) -> Taxonomy:
    """加载 taxonomy 文件（带进程级缓存）。"""
    p = path or (Path(__file__).resolve().parent.parent / "data" / "taxonomy.json")
    with p.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    return Taxonomy(TaxonomyFile.model_validate(raw))
