"""Taxonomy 驱动的 Offer 标准化。"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Mapping

from product_matching.models import NormalizedCandidate, Offer
from product_matching.taxonomy import Taxonomy

_MODEL_SEPARATORS = re.compile(r"[\s\-_/·]+")
_UNIT_PATTERNS: list[tuple[re.Pattern[str], str, float]] = [
    (re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([Ll]|升)\s*$"), "L", 1.0),
    (re.compile(r"^\s*(\d+(?:\.\d+)?)\s*毫升\s*$"), "L", 0.001),
    (re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(ml|ML)\s*$"), "L", 0.001),
    (re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(w|W|瓦)\s*$"), "W", 1.0),
    (re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(kw|kW|KW|千瓦)\s*$"), "W", 1000.0),
    (re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(h|H|小时)\s*$"), "h", 1.0),
]


class TaxonomyNormalizer:
    def __init__(self, taxonomy: Taxonomy) -> None:
        self._taxonomy = taxonomy

    def normalize_offer(self, offer: Offer) -> NormalizedCandidate:
        failures: list[str] = []
        category_id = self._taxonomy.resolve_category(offer.category_id)[0]

        brand = self._taxonomy.normalize_brand(offer.brand)
        if offer.brand and not brand:
            failures.append("brand")
        model = self._taxonomy.normalize_model(offer.model, category_id)
        if offer.model and not model:
            failures.append("model")

        identity: dict[str, str] = {}
        for key, raw in offer.identity_attributes.items():
            normalized = self._normalize_attribute(category_id, key, raw)
            if normalized is not None:
                identity[key] = normalized
            else:
                failures.append(f"identity:{key}")

        variant: dict[str, str] = {}
        for key, raw in offer.variant_attributes.items():
            normalized = self._normalize_attribute(category_id, key, raw)
            if normalized is not None:
                variant[key] = normalized
            else:
                failures.append(f"variant:{key}")

        return NormalizedCandidate(
            offer_id=offer.offer_id,
            offer=offer,
            normalized_category_id=category_id,
            normalized_brand=brand,
            normalized_model=model,
            normalized_identity=identity,
            normalized_variant=variant,
            normalization_failures=failures,
            recall_score=0.0,
        )

    def normalize_recognition(
        self,
        *,
        category_id: str | None,
        brand: str | None,
        model: str | None,
        attributes: Mapping[str, str] | None,
    ) -> dict[str, object]:
        normalized_category_id, category_name = self._taxonomy.resolve_category(category_id)
        normalized_brand = self._taxonomy.normalize_brand(brand) if brand else None
        normalized_model = (
            self._taxonomy.normalize_model(model, normalized_category_id) if model else None
        )
        normalized_attributes: dict[str, str] = {}
        for key, raw in (attributes or {}).items():
            normalized = self._normalize_attribute(normalized_category_id, key, raw)
            if normalized is not None:
                normalized_attributes[key] = normalized
        return {
            "category_id": normalized_category_id,
            "category_name": category_name,
            "brand": normalized_brand,
            "model": normalized_model,
            "attributes": normalized_attributes,
        }

    def _normalize_attribute(self, category_id: str | None, key: str, raw: str) -> str | None:
        text = unicodedata.normalize("NFKC", raw).strip()
        text = re.sub(r"\s+", " ", text)
        if not text:
            return None

        for pattern, unit, factor in _UNIT_PATTERNS:
            match = pattern.match(text)
            if match is not None:
                number = float(match.group(1)) * factor
                text = f"{number:g}{unit}"
                break

        if category_id:
            category = self._taxonomy.get_category(category_id)
            schema = category.attribute_schema.get(key) if category is not None else None
            allowed = schema.get("enum") if schema is not None else None
            if isinstance(allowed, list):
                for candidate in allowed:
                    if isinstance(candidate, str) and (
                        candidate == text or candidate in text or text in candidate
                    ):
                        return candidate
                return None
        return text

    @staticmethod
    def model_equivalent(a: str, b: str) -> bool:
        def normalize(value: str) -> str:
            value = unicodedata.normalize("NFKC", value).strip().upper()
            return _MODEL_SEPARATORS.sub(" ", value)

        return bool(normalize(a)) and normalize(a) == normalize(b)

    @staticmethod
    def title_token_similarity(a: str, b: str) -> float:
        def tokens(value: str) -> set[str]:
            return {
                token
                for token in re.split(r"\W+", unicodedata.normalize("NFKC", value).lower())
                if len(token) >= 2
            }

        left, right = tokens(a), tokens(b)
        if not left or not right:
            return 0.0
        return len(left & right) / math.sqrt(len(left) * len(right))
