package com.ec26b.shoppingagent.product;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class PreferenceExtensionTests {

    @Autowired
    private UserPreferenceParser preferenceParser;

    @Autowired
    private RuleBasedShoppingIntentParser ruleParser;

    @Autowired
    private ProductSourceProvider source;

    // ── Brand parsing ───────────────────────────────────────

    @Test
    void shouldExtractBrandFromChineseName() {
        assertEquals("耐克", preferenceParser.parse("我想买耐克运动鞋").brand());
        assertEquals("阿迪达斯", preferenceParser.parse("阿迪达斯的运动鞋").brand());
        assertEquals("索尼", preferenceParser.parse("索尼降噪耳机").brand());
        assertEquals("戴森", preferenceParser.parse("戴森吹风机").brand());
        assertEquals("小米", preferenceParser.parse("小米的智能手表").brand());
    }

    @Test
    void shouldExtractBrandFromEnglishName() {
        assertEquals("耐克", preferenceParser.parse("Nike运动鞋推荐").brand());
        assertEquals("阿迪达斯", preferenceParser.parse("adidas tracksuit").brand());
        assertEquals("苹果", preferenceParser.parse("Apple Watch").brand());
    }

    @Test
    void shouldReturnNullBrandWhenAbsent() {
        assertNull(preferenceParser.parse("普通运动鞋").brand());
    }

    // ── Platform parsing ────────────────────────────────────

    @Test
    void shouldExtractJdPlatform() {
        var p = preferenceParser.parse("只看京东的耳机");
        assertEquals(List.of("京东-mock"), p.platforms());
    }

    @Test
    void shouldExtractMultiplePlatforms() {
        var p = preferenceParser.parse("京东和淘宝的耳机");
        assertTrue(p.platforms().contains("京东-mock"));
        assertTrue(p.platforms().contains("淘宝-mock"));
    }

    // ── Sort parsing ────────────────────────────────────────

    @Test
    void shouldExtractSortByPriceAsc() {
        assertEquals("price_asc",
                preferenceParser.parse("耳机按价格从低到高").sortBy());
    }

    @Test
    void shouldExtractSortBySalesDesc() {
        assertEquals("sales_desc",
                preferenceParser.parse("销量优先的运动鞋").sortBy());
    }

    @Test
    void shouldExtractSortByRatingDesc() {
        assertEquals("rating_desc",
                preferenceParser.parse("好评率最高的耳机").sortBy());
    }

    // ── Min rating parsing ──────────────────────────────────

    @Test
    void shouldExtractMinRating() {
        assertEquals(4.8, preferenceParser.parse("评分4.8以上的运动鞋").minRating());
        assertEquals(4.5, preferenceParser.parse("评分4.5分以上的耳机").minRating());
    }

    @Test
    void shouldExtractMinRatingFromStars() {
        assertEquals(4.5, preferenceParser.parse("4.5星以上的吹风机").minRating());
    }

    @Test
    void shouldClampRatingToFive() {
        assertNull(preferenceParser.parse("评分9999以上").minRating());
    }

    // ── Search filtering ────────────────────────────────────

    @Test
    void shouldSearchByCategory() {
        var sr = source.search(new ProductSearchQuery(
                "运动鞋", List.of(), null, null, null, List.of(), null, null));
        assertFalse(sr.products().isEmpty());
    }

    @Test
    void shouldSearchByCategoryHeadphones() {
        var sr = source.search(new ProductSearchQuery(
                "耳机", List.of(), null, null, null, List.of(), null, null));
        assertFalse(sr.products().isEmpty());
    }

    @Test
    void shouldFilterByPlatform() {
        var sr = source.search(new ProductSearchQuery(
                "耳机", List.of(), null, null, null,
                List.of("京东-mock"), null, null));
        assertFalse(sr.products().isEmpty());
        for (var p : sr.products()) {
            assertEquals("京东-mock", p.platform());
        }
    }

    @Test
    void shouldFilterByMinRating() {
        var sr = source.search(new ProductSearchQuery(
                "耳机", List.of(), null, null, null, List.of(), null, 4.0));
        for (var p : sr.products()) {
            assertTrue(p.rating() >= 4.0,
                    "rating should be >= 4.0, got: " + p.rating());
        }
    }

    @Test
    void shouldFilterByBudget() {
        var sr = source.search(new ProductSearchQuery(
                "耳机", List.of(), 500.0, null, null, List.of(), null, null));
        for (var p : sr.products()) {
            assertTrue(p.price() <= 500.0,
                    "should respect budget, got: " + p.price());
        }
    }

    @Test
    void shouldSortByPriceAsc() {
        var sr = source.search(new ProductSearchQuery(
                "耳机", List.of(), null, null, null, List.of(), "price_asc", null));
        for (int i = 1; i < sr.products().size(); i++) {
            assertTrue(sr.products().get(i).price() >= sr.products().get(i - 1).price(),
                    "products should be sorted by price ascending");
        }
    }

    @Test
    void shouldSortByRatingDesc() {
        var sr = source.search(new ProductSearchQuery(
                "运动鞋", List.of(), null, null, null, List.of(), "rating_desc", null));
        for (int i = 1; i < sr.products().size(); i++) {
            assertTrue(sr.products().get(i).rating() <= sr.products().get(i - 1).rating(),
                    "products should be sorted by rating descending");
        }
    }

    // ── New categories ──────────────────────────────────────

    @Test
    void shouldRecognizeBackpackCategory() {
        assertEquals("背包", RuleBasedShoppingIntentParser.parseExplicitKeyword("我想买背包"));
        assertEquals("背包", RuleBasedShoppingIntentParser.parseExplicitKeyword("双肩包"));
        var sr = source.search(new ProductSearchQuery("背包", List.of(), null));
        assertFalse(sr.products().isEmpty());
    }

    @Test
    void shouldRecognizeSmartwatchCategory() {
        assertEquals("智能手表",
                RuleBasedShoppingIntentParser.parseExplicitKeyword("智能手表"));
    }

    // ── Product metadata ────────────────────────────────────

    @Test
    void productOfferShouldExposePriceHistory() {
        var sr = source.search(new ProductSearchQuery("耳机", List.of(), null));
        assertFalse(sr.products().isEmpty());
        for (var p : sr.products()) {
            assertFalse(p.priceHistory().isEmpty(),
                    "price history should be non-empty for product " + p.productId());
        }
    }

    @Test
    void scoredProductShouldExposeMatchedPreferences() {
        var sr = source.search(new ProductSearchQuery(
                "耳机", List.of("lowest_price", "official_store"), 300.0,
                null, null, List.of(), null, null));
        assertFalse(sr.products().isEmpty());
    }
}
