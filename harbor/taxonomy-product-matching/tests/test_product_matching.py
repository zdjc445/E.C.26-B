from __future__ import annotations

import hashlib
import json
import unittest
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock, patch

import product_matching.models as models_module
import product_matching.taxonomy as taxonomy_module

from product_matching import (
    CategorySchema,
    ModelNormalizationRules,
    Offer,
    PairSimilarityProviders,
    SameItemMatcher,
    SkuSplitter,
    Taxonomy,
    TaxonomyFile,
    TaxonomyNormalizer,
    default_taxonomy,
    spu_id_for,
)


def offer(
    offer_id: str,
    *,
    platform: str = "jd",
    title: str = "Sony WH-1000XM5 头戴式无线降噪耳机",
    source_product_id: str | None = None,
    source_updated_at: str | None = None,
    category_id: str | None = "headphone",
    brand: str | None = "Sony",
    model: str | None = "WH-1000XM5",
    same_item_key: str | None = None,
    identity: dict[str, str] | None = None,
    variant: dict[str, str] | None = None,
    price: float | None = None,
    shipping_fee: float | None = None,
    coupon_amount: float | None = None,
    shop_id: str | None = None,
) -> Offer:
    return Offer(
        offer_id=offer_id,
        platform=platform,
        title=title,
        source_product_id=source_product_id or offer_id,
        source_updated_at=source_updated_at,
        category_id=category_id,
        brand=brand,
        model=model,
        same_item_key=same_item_key,
        identity_attributes=(
            identity
            if identity is not None
            else {"connectivity": "蓝牙", "wearing_style": "头戴式"}
        ),
        variant_attributes=(
            variant if variant is not None else {"color": "黑色", "set_type": "单件"}
        ),
        price=price,
        shipping_fee=shipping_fee,
        coupon_amount=coupon_amount,
        shop_id=shop_id,
    )


class TaxonomyNormalizerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.taxonomy = default_taxonomy()
        self.normalizer = TaxonomyNormalizer(self.taxonomy)

    def test_loads_standalone_project_format_taxonomy_json(self) -> None:
        self.assertEqual(self.taxonomy.schema_version, "1.0")
        self.assertEqual(self.taxonomy.taxonomy_version, "2026.08.1")
        self.assertEqual(
            self.taxonomy.resolve_category("智能腕表"),
            ("smartwatch", "智能手表"),
        )

    def test_protected_contract_files_are_unchanged(self) -> None:
        taxonomy_path = Path(taxonomy_module.__file__).resolve()
        protected_files = {
            Path(models_module.__file__).resolve(): (
                "a08468bdcbbd4489d9fe7d657afe58749c77a3692b85ac4272b6350de802310e"
            ),
            taxonomy_path: (
                "1c0ea15125539669a1dc5ede45a692e7a58d973fd7432a6138f9a55743ce3c5e"
            ),
            taxonomy_path.parent / "data" / "taxonomy.json": (
                "65c49d61fb73ca8826949a43b7239a7b1d82796d1d9f7598c959e4a79fab9dbf"
            ),
        }
        for path, expected_digest in protected_files.items():
            with self.subTest(path=path.name):
                normalized_bytes = path.read_text(encoding="utf-8").replace("\r\n", "\n").encode()
                self.assertEqual(hashlib.sha256(normalized_bytes).hexdigest(), expected_digest)

    def test_normalizes_offer_with_project_taxonomy_rules(self) -> None:
        result = self.normalizer.normalize_offer(
            offer("a", category_id="蓝牙耳机", brand="索尼", model="wh_1000xm5")
        )
        self.assertEqual(result.normalized_category_id, "headphone")
        self.assertEqual(result.normalized_brand, "Sony")
        self.assertEqual(result.normalized_model, "WH 1000XM5")
        self.assertEqual(result.normalized_identity["connectivity"], "蓝牙")
        self.assertEqual(result.normalized_variant["color"], "黑色")
        self.assertEqual(result.normalization_failures, [])

    def test_unknown_category_is_not_guessed(self) -> None:
        result = self.normalizer.normalize_offer(offer("a", category_id="ghost"))
        self.assertIsNone(result.normalized_category_id)

    def test_unknown_brand_is_kept_but_single_character_brand_fails(self) -> None:
        unknown = self.normalizer.normalize_offer(offer("a", brand="NoSuchBrand"))
        invalid = self.normalizer.normalize_offer(offer("b", brand="A"))
        self.assertEqual(unknown.normalized_brand, "NoSuchBrand")
        self.assertIsNone(invalid.normalized_brand)
        self.assertIn("brand", invalid.normalization_failures)

    def test_enum_values_are_canonicalized_by_taxonomy(self) -> None:
        result = self.normalizer.normalize_offer(
            offer("a", identity={"connectivity": "支持蓝牙连接", "wearing_style": "头戴式"})
        )
        self.assertEqual(result.normalized_identity["connectivity"], "蓝牙")

    def test_invalid_enum_is_removed_and_failure_is_recorded(self) -> None:
        result = self.normalizer.normalize_offer(
            offer("a", identity={"connectivity": "量子连接", "wearing_style": "头戴式"})
        )
        self.assertNotIn("connectivity", result.normalized_identity)
        self.assertIn("identity:connectivity", result.normalization_failures)

    def test_model_and_variant_failures_are_recorded_and_recall_starts_at_zero(self) -> None:
        result = self.normalizer.normalize_offer(
            offer(
                "failure-details",
                model="   ",
                variant={"color": "黑色", "set_type": "礼盒"},
            )
        )
        self.assertIsNone(result.normalized_model)
        self.assertEqual(result.normalized_variant, {"color": "黑色"})
        self.assertEqual(result.normalization_failures, ["model", "variant:set_type"])
        self.assertEqual(result.recall_score, 0.0)

    def test_empty_enum_rejects_every_value(self) -> None:
        taxonomy = Taxonomy(
            TaxonomyFile(
                schema_version="1.0",
                taxonomy_version="test",
                categories=[
                    CategorySchema(
                        category_id="service",
                        category_name="服务",
                        identity_attributes=["mode"],
                        attribute_schema={"mode": {"type": "string", "enum": []}},
                    )
                ],
            )
        )
        result = TaxonomyNormalizer(taxonomy).normalize_offer(
            offer(
                "empty-enum",
                category_id="service",
                identity={"mode": "任意值"},
                variant={},
            )
        )
        self.assertNotIn("mode", result.normalized_identity)
        self.assertIn("identity:mode", result.normalization_failures)

    def test_enum_candidate_contains_input_and_taxonomy_order_wins(self) -> None:
        taxonomy = Taxonomy(
            TaxonomyFile(
                schema_version="1.0",
                taxonomy_version="test",
                categories=[
                    CategorySchema(
                        category_id="audio_service",
                        category_name="音频服务",
                        identity_attributes=["mode"],
                        attribute_schema={
                            "mode": {
                                "type": "string",
                                "enum": ["主动降噪", "降噪"],
                            }
                        },
                    )
                ],
            )
        )
        result = TaxonomyNormalizer(taxonomy).normalize_offer(
            offer(
                "enum-order",
                category_id="audio_service",
                identity={"mode": "降噪"},
                variant={},
            )
        )
        self.assertEqual(result.normalized_identity, {"mode": "主动降噪"})

    def test_dynamic_taxonomy_drives_category_brand_and_model_normalization(self) -> None:
        taxonomy = Taxonomy(
            TaxonomyFile(
                schema_version="1.0",
                taxonomy_version="test",
                categories=[
                    CategorySchema(
                        category_id="camera",
                        category_name="相机",
                        aliases=["数码相机"],
                        brand_aliases={"佳能": "Canon"},
                        model_normalization_rules=ModelNormalizationRules(uppercase=True),
                    )
                ],
            )
        )
        result = TaxonomyNormalizer(taxonomy).normalize_offer(
            offer(
                "dynamic-taxonomy",
                category_id="数码相机",
                brand="佳能",
                model="eos-r5",
                identity={},
                variant={},
            )
        )
        self.assertEqual(result.normalized_category_id, "camera")
        self.assertEqual(result.normalized_brand, "Canon")
        self.assertEqual(result.normalized_model, "EOS R5")

    def test_identity_and_variant_attributes_remain_separate(self) -> None:
        result = self.normalizer.normalize_offer(offer("a"))
        self.assertEqual(set(result.normalized_identity), {"connectivity", "wearing_style"})
        self.assertEqual(set(result.normalized_variant), {"color", "set_type"})

    def test_attribute_nfkc_whitespace_and_input_immutability(self) -> None:
        identity = {
            "custom": "  Ａ　Ｂ  ",
            "nfkc_created_leading_space": "\u00a8X",
        }
        original = dict(identity)
        result = self.normalizer.normalize_offer(offer("a", identity=identity))
        self.assertEqual(result.normalized_identity["custom"], "A B")
        self.assertEqual(
            result.normalized_identity["nfkc_created_leading_space"],
            "\u0308X",
        )
        self.assertEqual(identity, original)

    def test_empty_attributes_are_removed_and_recorded_as_failures(self) -> None:
        result = self.normalizer.normalize_offer(
            offer(
                "empty-attributes",
                identity={"empty_identity": ""},
                variant={"empty_variant": ""},
            )
        )
        self.assertEqual(result.normalized_identity, {})
        self.assertEqual(result.normalized_variant, {})
        self.assertEqual(
            result.normalization_failures,
            ["identity:empty_identity", "variant:empty_variant"],
        )

    def test_normalize_offer_does_not_mutate_offer_or_attribute_mappings(self) -> None:
        identity = {
            "connectivity": "量子连接",
            "custom_identity": "  Ａ　Ｂ  ",
        }
        variant = {
            "color": "黑色",
            "set_type": "礼盒",
            "custom_variant": "  Ｃ　Ｄ  ",
        }
        value = offer("immutable", identity=identity, variant=variant)
        original = replace(
            value,
            identity_attributes=dict(identity),
            variant_attributes=dict(variant),
        )

        self.normalizer.normalize_offer(value)

        self.assertEqual(value, original)
        self.assertEqual(identity, original.identity_attributes)
        self.assertEqual(variant, original.variant_attributes)

    def test_unit_conversion_matches_project_rules(self) -> None:
        backpack = self.normalizer.normalize_offer(
            offer(
                "a",
                category_id="backpack",
                brand="新秀丽",
                model="pro-20",
                identity={"capacity_liters": "500毫升", "material": "尼龙"},
                variant={"color": "黑色", "size": "M"},
            )
        )
        dryer = self.normalizer.normalize_offer(
            offer(
                "b",
                category_id="hair_dryer",
                brand="戴森",
                model="hd-15",
                identity={"power": "1.6kW", "ion_type": "负离子"},
                variant={"color": "灰色", "voltage_region": "国行220V", "set_type": "单机"},
            )
        )
        self.assertEqual(backpack.normalized_identity["capacity_liters"], "0.5L")
        self.assertEqual(dryer.normalized_identity["power"], "1600W")

    def test_all_declared_unit_aliases_are_normalized(self) -> None:
        cases = [
            ("backpack", "capacity_liters", "2L", "2L"),
            ("backpack", "capacity_liters", "2l", "2L"),
            ("backpack", "capacity_liters", "2升", "2L"),
            ("backpack", "capacity_liters", "500毫升", "0.5L"),
            ("backpack", "capacity_liters", "500ml", "0.5L"),
            ("backpack", "capacity_liters", "500ML", "0.5L"),
            ("hair_dryer", "power", "2W", "2W"),
            ("hair_dryer", "power", "2w", "2W"),
            ("hair_dryer", "power", "2瓦", "2W"),
            ("hair_dryer", "power", "2kW", "2000W"),
            ("hair_dryer", "power", "2kw", "2000W"),
            ("hair_dryer", "power", "2KW", "2000W"),
            ("hair_dryer", "power", "2千瓦", "2000W"),
            ("headphone", "battery_life", "2h", "2h"),
            ("headphone", "battery_life", "2H", "2h"),
            ("headphone", "battery_life", "2小时", "2h"),
        ]
        for category_id, attribute, raw, expected in cases:
            with self.subTest(raw=raw):
                result = self.normalizer.normalize_recognition(
                    category_id=category_id,
                    brand=None,
                    model=None,
                    attributes={attribute: raw},
                )
                self.assertEqual(result["attributes"], {attribute: expected})

    def test_recognition_normalization_uses_same_taxonomy(self) -> None:
        result = self.normalizer.normalize_recognition(
            category_id="耳机",
            brand="索尼",
            model="wh-1000xm5",
            attributes={"noise_cancellation": "主动降噪"},
        )
        self.assertEqual(result["category_id"], "headphone")
        self.assertEqual(result["category_name"], "耳机")
        self.assertEqual(result["brand"], "Sony")
        self.assertEqual(result["model"], "WH 1000XM5")

    def test_recognition_drops_unresolvable_values(self) -> None:
        result = self.normalizer.normalize_recognition(
            category_id="不存在的品类",
            brand="A",
            model="   ",
            attributes={"connectivity": "量子连接", "custom": "   "},
        )
        self.assertEqual(
            result,
            {
                "category_id": None,
                "category_name": None,
                "brand": None,
                "model": None,
                "attributes": {"connectivity": "量子连接"},
            },
        )

    def test_model_equivalence_preserves_adjacent_model_difference(self) -> None:
        self.assertTrue(self.normalizer.model_equivalent("wh_1000xm5", "WH-1000XM5"))
        self.assertFalse(self.normalizer.model_equivalent("WH-1000XM5", "WH-1000XM4"))

    def test_model_equivalence_normalizes_nfkc_all_separators_and_whitespace(self) -> None:
        self.assertTrue(
            self.normalizer.model_equivalent(
                "  ＷＨ／１０００·ＸＭ５  ",
                "wh   1000_xm5",
            )
        )
        self.assertTrue(self.normalizer.model_equivalent("\u00a8X", "\u0308X"))
        self.assertFalse(self.normalizer.model_equivalent("", ""))
        self.assertFalse(self.normalizer.model_equivalent("   ", "\t"))

    def test_title_token_similarity_is_deterministic(self) -> None:
        similar = self.normalizer.title_token_similarity(
            "Sony WH-1000XM5 无线 降噪 耳机",
            "Sony WH-1000XM5 降噪 无线 耳机",
        )
        self.assertEqual(similar, 1.0)
        self.assertAlmostEqual(
            self.normalizer.title_token_similarity("苹果 手机 Pro", "苹果 平板 Pro"),
            2 / 3,
        )
        self.assertEqual(self.normalizer.title_token_similarity("苹果 手机", "运动鞋 跑步"), 0.0)
        self.assertEqual(self.normalizer.title_token_similarity("a b", "a b"), 0.0)
        self.assertEqual(self.normalizer.title_token_similarity("𝐀x", "ax"), 1.0)


class SameItemMatcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.taxonomy = default_taxonomy()
        self.normalizer = TaxonomyNormalizer(self.taxonomy)
        self.matcher = SameItemMatcher(
            self.taxonomy,
            PairSimilarityProviders(title=lambda _left, _right: 0.95),
        )

    def normalize(self, value: Offer):
        return self.normalizer.normalize_offer(value)

    def test_authoritative_same_item_key_generates_candidate(self) -> None:
        left = self.normalize(offer("a", title="标题 A", model="M1", same_item_key="key"))
        right = self.normalize(offer("b", title="标题 B", model="M2", same_item_key="key"))
        self.assertEqual(self.matcher.generate_candidates([left, right]), [(0, 1)])

    def test_authoritative_key_precedes_brand_conflict_during_candidate_generation(self) -> None:
        left = self.normalize(offer("a", brand="Sony", same_item_key="key"))
        right = self.normalize(offer("b", brand="Bose", same_item_key="key"))
        self.assertEqual(self.matcher.generate_candidates([left, right]), [(0, 1)])

    def test_different_category_brand_or_model_is_rejected(self) -> None:
        base = self.normalize(offer("a"))
        cases = {
            "category": self.normalize(
                offer(
                    "b",
                    category_id="sneaker",
                    brand="耐克",
                    model="WH-1000XM5",
                    identity={"shoe_type": "跑步"},
                    variant={"size": "42", "color": "黑色"},
                )
            ),
            "brand": self.normalize(offer("c", brand="Bose")),
            "model": self.normalize(offer("d", model="WH-1000XM4")),
        }
        for label, candidate in cases.items():
            with self.subTest(label=label):
                self.assertEqual(self.matcher.generate_candidates([base, candidate]), [])

    def test_title_similarity_threshold_gates_candidates(self) -> None:
        left = self.normalize(offer("a", model=None))
        right = self.normalize(offer("b", model=None))
        cases = [(0.85, [(0, 1)]), (0.849999, [])]
        for similarity, expected in cases:
            with self.subTest(similarity=similarity):
                matcher = SameItemMatcher(
                    self.taxonomy,
                    PairSimilarityProviders(
                        title=lambda _left, _right, value=similarity: value
                    ),
                )
                self.assertEqual(matcher.generate_candidates([left, right]), expected)

    def test_category_conflict_precedes_authoritative_key(self) -> None:
        left = self.normalize(offer("a", same_item_key="key"))
        right = self.normalize(
            offer(
                "b",
                category_id="sneaker",
                brand="耐克",
                model="WH-1000XM5",
                same_item_key="key",
                identity={"shoe_type": "跑步"},
                variant={"size": "42", "color": "黑色"},
            )
        )
        self.assertEqual(self.matcher.generate_candidates([left, right]), [])

    def test_missing_brand_does_not_pair_with_present_brand(self) -> None:
        left = self.normalize(offer("a", model=None, brand="Sony"))
        right = self.normalize(offer("b", model=None, brand=None))
        self.assertEqual(self.matcher.generate_candidates([left, right]), [])

    def test_two_missing_brands_are_also_rejected_without_authoritative_key(self) -> None:
        left = self.normalize(offer("a", model=None, brand=None))
        right = self.normalize(offer("b", model=None, brand=None))
        self.assertEqual(self.matcher.generate_candidates([left, right]), [])

    def test_candidate_pairs_preserve_input_index_order(self) -> None:
        candidates = [
            self.normalize(offer("a", model=None)),
            self.normalize(offer("b", model=None)),
            self.normalize(offer("c", model=None)),
        ]
        self.assertEqual(
            self.matcher.generate_candidates(candidates),
            [(0, 1), (0, 2), (1, 2)],
        )

    def test_identity_conflict_is_hard_veto(self) -> None:
        left = self.normalize(offer("a", identity={"connectivity": "蓝牙"}))
        right = self.normalize(offer("b", identity={"connectivity": "有线"}))
        result = self.matcher.judge_pair(left, right)
        self.assertEqual(result.verdict, "different")
        self.assertEqual(result.score, 0.0)
        self.assertIn("identity:connectivity", result.hard_conflicts)

    def test_authoritative_key_does_not_override_pair_hard_conflict(self) -> None:
        left = self.normalize(offer("a", brand="Sony", same_item_key="key"))
        right = self.normalize(offer("b", brand="Bose", same_item_key="key"))
        result = self.matcher.judge_pair(left, right)
        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.verdict, "different")
        self.assertIn("brand", result.hard_conflicts)

    def test_similarity_providers_are_not_called_after_hard_conflict(self) -> None:
        title_provider = Mock(side_effect=AssertionError("title provider must not run"))
        image_provider = Mock(side_effect=AssertionError("image provider must not run"))
        matcher = SameItemMatcher(
            self.taxonomy,
            PairSimilarityProviders(title=title_provider, image=image_provider),
        )
        left = self.normalize(offer("a", brand="Sony"))
        right = self.normalize(offer("b", brand="Bose"))
        result = matcher.judge_pair(left, right)
        self.assertEqual(result.verdict, "different")
        title_provider.assert_not_called()
        image_provider.assert_not_called()

    def test_category_brand_and_model_conflicts_are_reported(self) -> None:
        base = self.normalize(offer("a"))
        cases = {
            "category": self.normalize(
                offer(
                    "b",
                    category_id="sneaker",
                    brand="Sony",
                    model="WH-1000XM5",
                    identity={},
                    variant={"size": "42", "color": "黑色"},
                )
            ),
            "brand": self.normalize(offer("c", brand="Bose")),
            "model": self.normalize(offer("d", model="WH-1000XM4")),
        }
        for conflict, candidate in cases.items():
            with self.subTest(conflict=conflict):
                result = self.matcher.judge_pair(base, candidate)
                self.assertEqual(result.verdict, "different")
                self.assertIn(conflict, result.hard_conflicts)

    def test_missing_dimensions_are_renormalized(self) -> None:
        matcher = SameItemMatcher(
            self.taxonomy,
            PairSimilarityProviders(title=lambda _left, _right: 1.0),
        )
        left = self.normalize(offer("a", model=None, identity={}))
        right = self.normalize(offer("b", model=None, identity={}))
        result = matcher.judge_pair(left, right)
        self.assertEqual(result.score, 1.0)
        self.assertEqual(result.verdict, "same")

    def test_review_threshold_is_distinct_from_acceptance(self) -> None:
        matcher = SameItemMatcher(
            self.taxonomy,
            PairSimilarityProviders(title=lambda _left, _right: 0.70),
        )
        left = self.normalize(offer("a", model=None, identity={}))
        right = self.normalize(offer("b", model=None, identity={}))
        self.assertEqual(matcher.judge_pair(left, right).verdict, "review")

    def test_identity_weight_is_applied_exactly(self) -> None:
        matcher = SameItemMatcher(
            self.taxonomy,
            PairSimilarityProviders(title=lambda _left, _right: 0.5),
        )
        left = self.normalize(offer("a", model=None))
        right = self.normalize(offer("b", model=None))
        result = matcher.judge_pair(left, right)
        self.assertAlmostEqual(result.score, (0.35 * 0.5 + 0.30) / 0.65)
        self.assertEqual(result.identity_overlap, 1.0)
        self.assertEqual(result.verdict, "review")

    def test_identity_overlap_uses_only_keys_shared_by_both_candidates(self) -> None:
        matcher = SameItemMatcher(
            self.taxonomy,
            PairSimilarityProviders(title=lambda _left, _right: 0.95),
        )
        left = self.normalize(
            offer(
                "a",
                model=None,
                identity={"shared": "same", "left_only": "left"},
            )
        )
        right = self.normalize(
            offer(
                "b",
                model=None,
                identity={"shared": "same", "right_only": "right"},
            )
        )
        result = matcher.judge_pair(left, right)
        self.assertEqual(result.identity_overlap, 1.0)
        self.assertAlmostEqual(result.score, (0.35 * 0.95 + 0.30) / 0.65)
        self.assertEqual(result.verdict, "same")

    def test_default_verdict_threshold_boundaries(self) -> None:
        left = self.normalize(offer("a", model=None, identity={}))
        right = self.normalize(offer("b", model=None, identity={}))
        cases = [
            (0.82, "same"),
            (0.819999, "review"),
            (0.68, "review"),
            (0.679999, "different"),
        ]
        for score, verdict in cases:
            with self.subTest(score=score):
                matcher = SameItemMatcher(
                    self.taxonomy,
                    PairSimilarityProviders(
                        title=lambda _left, _right, value=score: value
                    ),
                )
                self.assertEqual(matcher.judge_pair(left, right).verdict, verdict)

    def test_image_and_source_key_dimensions_are_included(self) -> None:
        matcher = SameItemMatcher(
            self.taxonomy,
            PairSimilarityProviders(
                title=lambda _left, _right: 0.7,
                image=lambda _left, _right: 1.0,
            ),
        )
        left = self.normalize(offer("a", model=None, identity={}, same_item_key="key"))
        right = self.normalize(offer("b", model=None, identity={}, same_item_key="key"))
        result = matcher.judge_pair(left, right)
        expected = (0.35 * 0.7 + 0.25 * 1.0 + 0.10 * 1.0) / 0.70
        self.assertAlmostEqual(result.score, expected)
        self.assertEqual(result.image_similarity, 1.0)
        self.assertEqual(result.source_key_signal, 1.0)
        self.assertEqual(result.verdict, "same")

    def test_image_provider_returning_none_is_a_missing_dimension(self) -> None:
        matcher = SameItemMatcher(
            self.taxonomy,
            PairSimilarityProviders(
                title=lambda _left, _right: 0.7,
                image=lambda _left, _right: None,
            ),
        )
        left = self.normalize(offer("a", model=None, identity={}))
        right = self.normalize(offer("b", model=None, identity={}))
        result = matcher.judge_pair(left, right)
        self.assertEqual(result.score, 0.7)
        self.assertIsNone(result.image_similarity)
        self.assertEqual(result.verdict, "review")

    def test_complete_link_blocks_transitive_merge(self) -> None:
        scores = {("a", "b"): 0.99, ("b", "c"): 0.99, ("a", "c"): 0.1}
        matcher = SameItemMatcher(
            self.taxonomy,
            PairSimilarityProviders(
                title=lambda left, right: scores.get((left, right), scores.get((right, left), 0.0))
            ),
        )
        candidates = [
            self.normalize(offer("a", title="a", model=None, identity={})),
            self.normalize(offer("b", title="b", model=None, identity={})),
            self.normalize(offer("c", title="c", model=None, identity={})),
        ]
        pairs = matcher.generate_candidates(candidates)
        self.assertEqual(matcher.cluster(candidates, pairs), [[0, 1], [2]])

    def test_authoritative_key_can_bridge_cluster(self) -> None:
        candidates = [
            self.normalize(offer("a", title="a", model=None, identity={}, same_item_key="key")),
            self.normalize(offer("b", title="b", model=None, identity={}, same_item_key="key")),
            self.normalize(offer("c", title="c", model=None, identity={}, same_item_key="key")),
        ]
        pairs = self.matcher.generate_candidates(candidates)
        self.assertEqual(self.matcher.cluster(candidates, pairs), [[0, 1, 2]])

    def test_authoritative_edge_does_not_bypass_other_complete_link_edges(self) -> None:
        scores = {("a", "b"): 0.1, ("a", "c"): 0.99, ("b", "c"): 0.1}
        matcher = SameItemMatcher(
            self.taxonomy,
            PairSimilarityProviders(
                title=lambda left, right: scores.get(
                    (left, right), scores.get((right, left), 0.0)
                )
            ),
        )
        candidates = [
            self.normalize(
                offer("a", title="a", model=None, identity={}, same_item_key="authority")
            ),
            self.normalize(
                offer("b", title="b", model=None, identity={}, same_item_key="authority")
            ),
            self.normalize(offer("c", title="c", model=None, identity={})),
        ]
        pairs = [(0, 1), (0, 2), (1, 2)]
        self.assertEqual(matcher.cluster(candidates, pairs), [[0, 1], [2]])

    def test_authoritative_and_similarity_edges_can_complete_one_cluster(self) -> None:
        scores = {("a", "b"): 0.1, ("a", "c"): 0.99, ("b", "c"): 0.99}
        matcher = SameItemMatcher(
            self.taxonomy,
            PairSimilarityProviders(
                title=lambda left, right: scores.get(
                    (left, right), scores.get((right, left), 0.0)
                )
            ),
        )
        candidates = [
            self.normalize(
                offer("a", title="a", model=None, identity={}, same_item_key="authority")
            ),
            self.normalize(
                offer("b", title="b", model=None, identity={}, same_item_key="authority")
            ),
            self.normalize(offer("c", title="c", model=None, identity={})),
        ]
        pairs = [(0, 1), (0, 2), (1, 2)]
        self.assertEqual(matcher.cluster(candidates, pairs), [[0, 1, 2]])


class SkuSplitterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.taxonomy = default_taxonomy()
        self.normalizer = TaxonomyNormalizer(self.taxonomy)
        self.splitter = SkuSplitter(self.taxonomy)

    def normalize(self, value: Offer, *, score: float = 1.0):
        return replace(self.normalizer.normalize_offer(value), recall_score=score)

    def test_variant_attributes_split_sku_groups(self) -> None:
        members = [
            self.normalize(offer("a", variant={"color": "黑色", "set_type": "单件"})),
            self.normalize(offer("b", variant={"color": "黑色", "set_type": "单件"})),
            self.normalize(offer("c", variant={"color": "白色", "set_type": "单件"})),
        ]
        groups = self.splitter.split_spu(members, "spu:test")
        by_signature = {group.sku_signature: group for group in groups}
        self.assertEqual(
            set(by_signature), {"color=黑色|set_type=单件", "color=白色|set_type=单件"}
        )
        self.assertEqual(by_signature["color=黑色|set_type=单件"].offer_count, 2)

    def test_missing_variant_attribute_stays_single_and_lowers_confidence(self) -> None:
        complete = self.normalize(offer("a"), score=0.8)
        incomplete = self.normalize(offer("b", variant={"color": "黑色"}), score=0.8)
        groups = self.splitter.split_spu([complete, incomplete], "spu:test")
        missing = [group for group in groups if group.missing_sku_attributes]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0].missing_sku_attributes, ["set_type"])
        self.assertEqual(missing[0].offer_count, 1)
        self.assertEqual(missing[0].match_confidence, 0.72)
        self.assertEqual(
            missing[0].risks,
            ["关键销售属性缺失，未与其他报价直接合并"],
        )

    def test_missing_variant_single_groups_have_distinct_stable_ids(self) -> None:
        members = [
            self.normalize(offer("missing-a", variant={"color": "黑色"})),
            self.normalize(offer("missing-b", variant={"color": "白色"})),
        ]
        groups = self.splitter.split_spu(members, "spu:test")
        self.assertEqual([group.sku_signature for group in groups], [None, None])
        self.assertEqual(
            [group.group_id for group in groups],
            ["spu:test:b639b5d9f6", "spu:test:e31600d508"],
        )

    def test_confidence_uses_member_average_rounding_and_bounds(self) -> None:
        averaged = [
            self.normalize(offer("average-a"), score=0.2),
            self.normalize(offer("average-b"), score=0.4),
        ]
        above_one = [
            self.normalize(offer("high-a"), score=1.5),
            self.normalize(offer("high-b"), score=2.5),
        ]
        below_zero = [
            self.normalize(offer("low-a"), score=-1.0),
            self.normalize(offer("low-b"), score=-2.0),
        ]
        self.assertEqual(self.splitter.split_spu(averaged, "spu:average")[0].match_confidence, 0.3)
        self.assertEqual(self.splitter.split_spu(above_one, "spu:high")[0].match_confidence, 1.0)
        self.assertEqual(self.splitter.split_spu(below_zero, "spu:low")[0].match_confidence, 0.0)

    def test_price_aggregation_uses_payable_price(self) -> None:
        members = [
            self.normalize(
                offer("a", platform="jd", price=100.0, coupon_amount=10.0, shipping_fee=5.0)
            ),
            self.normalize(offer("b", platform="taobao", price=120.0)),
        ]
        group = self.splitter.split_spu(members, "spu:test")[0]
        self.assertEqual(group.min_price, 95.0)
        self.assertEqual(group.max_price, 120.0)
        self.assertEqual(group.average_price, 107.5)
        self.assertEqual(group.min_price_offer_id, "a")
        self.assertEqual(group.platform_count, 2)

    def test_platform_count_excludes_offers_without_prices(self) -> None:
        members = [
            self.normalize(offer("priced", platform="jd", price=100.0)),
            self.normalize(offer("unpriced", platform="taobao", price=None)),
        ]
        group = self.splitter.split_spu(members, "spu:test")[0]
        self.assertEqual(group.offer_count, 2)
        self.assertEqual(group.platform_count, 1)

    def test_duplicate_source_offer_keeps_latest(self) -> None:
        members = [
            self.normalize(
                offer(
                    "old",
                    source_product_id="same",
                    source_updated_at="2026-08-01T00:00:00Z",
                    shop_id="shop",
                    price=100.0,
                )
            ),
            self.normalize(
                offer(
                    "new",
                    source_product_id="same",
                    source_updated_at="2026-08-10T00:00:00Z",
                    shop_id="shop",
                    price=90.0,
                )
            ),
        ]
        group = self.splitter.split_spu(members, "spu:test")[0]
        self.assertEqual(group.offer_count, 1)
        self.assertEqual(group.offers[0].offer_id, "new")

    def test_missing_source_product_id_deduplicates_using_empty_string_key(self) -> None:
        old = replace(
            offer(
                "missing-source-old",
                source_updated_at="2026-08-01T00:00:00Z",
                shop_id="shop",
                price=100.0,
            ),
            source_product_id=None,
        )
        new = replace(
            offer(
                "missing-source-new",
                source_updated_at="2026-08-10T00:00:00Z",
                shop_id="shop",
                price=90.0,
            ),
            source_product_id=None,
        )
        group = self.splitter.split_spu(
            [self.normalize(old), self.normalize(new)],
            "spu:test",
        )[0]
        self.assertEqual(group.offer_count, 1)
        self.assertEqual(group.offers[0].offer_id, "missing-source-new")

    def test_deduplication_uses_platform_shop_and_source_product_id(self) -> None:
        members = [
            self.normalize(
                offer(
                    "jd-shop-a",
                    platform="jd",
                    source_product_id="same-source",
                    shop_id="shop-a",
                    price=100.0,
                )
            ),
            self.normalize(
                offer(
                    "jd-shop-b",
                    platform="jd",
                    source_product_id="same-source",
                    shop_id="shop-b",
                    price=110.0,
                )
            ),
            self.normalize(
                offer(
                    "taobao-shop-a",
                    platform="taobao",
                    source_product_id="same-source",
                    shop_id="shop-a",
                    price=120.0,
                )
            ),
        ]
        group = self.splitter.split_spu(members, "spu:test")[0]
        self.assertEqual(group.offer_count, 3)
        self.assertEqual({item.offer_id for item in group.offers}, {
            "jd-shop-a",
            "jd-shop-b",
            "taobao-shop-a",
        })
        self.assertEqual(group.platform_count, 2)

    def test_empty_members_and_no_price_are_handled(self) -> None:
        self.assertEqual(self.splitter.split_spu([], "spu:test"), [])
        group = self.splitter.split_spu([self.normalize(offer("a", price=None))], "spu:test")[0]
        self.assertIsNone(group.min_price)
        self.assertIsNone(group.max_price)
        self.assertIsNone(group.average_price)
        self.assertIsNone(group.min_price_offer_id)
        self.assertEqual(group.platform_count, 0)

    def test_freshness_uses_valid_naive_utc_time_even_without_prices(self) -> None:
        members = [
            self.normalize(
                offer(
                    "valid",
                    source_updated_at="2026-08-01T00:00:00",
                    price=None,
                )
            ),
            self.normalize(
                offer("invalid", source_updated_at="not-a-time", price=None)
            ),
        ]
        with patch("product_matching.sku.datetime") as mocked_datetime:
            mocked_datetime.fromisoformat.side_effect = datetime.fromisoformat
            mocked_datetime.now.return_value = datetime(2026, 8, 16, tzinfo=UTC)
            group = self.splitter.split_spu(members, "spu:test")[0]
        self.assertIsNone(group.min_price)
        self.assertEqual(group.platform_count, 0)
        self.assertEqual(group.price_freshness, 0.5)

    def test_freshness_averages_valid_naive_aware_and_expired_times(self) -> None:
        members = [
            self.normalize(offer("recent", source_updated_at="2026-08-10T00:00:00", price=None)),
            self.normalize(
                offer("aware", source_updated_at="2026-08-16T08:00:00+08:00", price=None)
            ),
            self.normalize(offer("expired", source_updated_at="2026-06-01T00:00:00Z", price=None)),
            self.normalize(offer("invalid", source_updated_at="not-a-time", price=None)),
        ]
        with patch("product_matching.sku.datetime") as mocked_datetime:
            mocked_datetime.fromisoformat.side_effect = datetime.fromisoformat
            mocked_datetime.now.return_value = datetime(2026, 8, 16, tzinfo=UTC)
            group = self.splitter.split_spu(members, "spu:test")[0]
        self.assertEqual(group.price_freshness, 0.6)

    def test_future_timestamp_follows_unbounded_freshness_formula(self) -> None:
        member = self.normalize(
            offer(
                "future",
                source_updated_at="2026-08-31T00:00:00Z",
                price=None,
            )
        )
        with patch("product_matching.sku.datetime") as mocked_datetime:
            mocked_datetime.fromisoformat.side_effect = datetime.fromisoformat
            mocked_datetime.now.return_value = datetime(2026, 8, 16, tzinfo=UTC)
            group = self.splitter.split_spu([member], "spu:test")[0]
        self.assertEqual(group.price_freshness, 1.5)

    def test_category_without_variant_keys_forms_one_empty_signature_group(self) -> None:
        taxonomy = Taxonomy(
            TaxonomyFile(
                schema_version="1.0",
                taxonomy_version="test",
                categories=[
                    CategorySchema(
                        category_id="service",
                        category_name="服务",
                        aliases=["服务"],
                        variant_attributes=[],
                    ),
                ],
            )
        )
        normalizer = TaxonomyNormalizer(taxonomy)
        splitter = SkuSplitter(taxonomy)
        members = [
            replace(
                normalizer.normalize_offer(
                    offer("a", category_id="service", identity={}, variant={})
                ),
                recall_score=1.0,
            ),
            replace(
                normalizer.normalize_offer(
                    offer("b", category_id="service", identity={}, variant={})
                ),
                recall_score=1.0,
            ),
        ]
        groups = splitter.split_spu(members, "spu:service")
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].sku_signature, "")
        self.assertEqual(groups[0].offer_count, 2)

    def test_signature_sorts_custom_taxonomy_variant_attribute_names(self) -> None:
        taxonomy = Taxonomy(
            TaxonomyFile(
                schema_version="1.0",
                taxonomy_version="test",
                categories=[
                    CategorySchema(
                        category_id="custom",
                        category_name="自定义",
                        variant_attributes=["zeta", "alpha"],
                        attribute_schema={
                            "zeta": {"type": "string"},
                            "alpha": {"type": "string"},
                        },
                    )
                ],
            )
        )
        candidate = replace(
            TaxonomyNormalizer(taxonomy).normalize_offer(
                offer(
                    "custom-offer",
                    category_id="custom",
                    identity={},
                    variant={"zeta": "Z", "alpha": "A"},
                )
            ),
            recall_score=1.0,
        )
        group = SkuSplitter(taxonomy).split_spu([candidate], "spu:custom")[0]
        self.assertEqual(group.sku_signature, "alpha=A|zeta=Z")
        expected_suffix = hashlib.sha256("alpha=A|zeta=Z".encode()).hexdigest()[:10]
        self.assertEqual(group.group_id, f"spu:custom:{expected_suffix}")

    def test_spu_and_group_ids_are_stable(self) -> None:
        members = [self.normalize(offer("b")), self.normalize(offer("a"))]
        first_spu_id = spu_id_for(members)
        second_spu_id = spu_id_for(list(reversed(members)))
        first_group = self.splitter.split_spu(members, first_spu_id)[0]
        second_group = self.splitter.split_spu(members, first_spu_id)[0]
        self.assertEqual(first_spu_id, second_spu_id)
        self.assertEqual(first_spu_id, "spu:3554d2b8a1e3")
        self.assertEqual(first_group.group_id, second_group.group_id)
        self.assertEqual(first_group.group_id, "spu:3554d2b8a1e3:6d9aabbec9")

    def test_spu_id_formula_handles_dynamic_unicode_offer_ids(self) -> None:
        members = [
            self.normalize(offer("商品-丙")),
            self.normalize(offer("商品-甲")),
            self.normalize(offer("商品-乙")),
        ]
        sorted_ids = ["商品-丙", "商品-乙", "商品-甲"]
        expected_digest = hashlib.sha256(
            json.dumps(sorted_ids, ensure_ascii=False).encode()
        ).hexdigest()[:12]
        self.assertEqual(spu_id_for(members), f"spu:{expected_digest}")


if __name__ == "__main__":
    unittest.main()
