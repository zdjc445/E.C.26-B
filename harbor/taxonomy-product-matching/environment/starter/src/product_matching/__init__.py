"""独立 taxonomy 商品匹配任务公开接口。"""

from product_matching.models import NormalizedCandidate, Offer, PairResult, SkuGroup
from product_matching.normalization import TaxonomyNormalizer
from product_matching.same_item import PairSimilarityProviders, SameItemMatcher
from product_matching.sku import SkuSplitter, spu_id_for
from product_matching.taxonomy import (
    CategorySchema,
    ModelNormalizationRules,
    Taxonomy,
    TaxonomyFile,
    UnitRule,
    default_taxonomy,
    load_taxonomy,
)

__all__ = [
    "CategorySchema",
    "ModelNormalizationRules",
    "NormalizedCandidate",
    "Offer",
    "PairResult",
    "PairSimilarityProviders",
    "SameItemMatcher",
    "SkuGroup",
    "SkuSplitter",
    "Taxonomy",
    "TaxonomyFile",
    "TaxonomyNormalizer",
    "UnitRule",
    "default_taxonomy",
    "load_taxonomy",
    "spu_id_for",
]
