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
    private MockProductSourceProvider source;

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
    void shouldFilterByBrand() {
        var sr = source.search(new ProductSearchQuery(
                "运动鞋", List.of(), null, null, "耐克", List.of(), null, null));
        assertFalse(sr.products().isEmpty());
        for (var p : sr.products()) {
            assertTrue(p.title().contains("耐克") || "耐克".equals(p.brand()),
                    "expected 耐克 in title or brand, got: " + p.title());
        }
    }

    @Test
    void shouldFilterByPlatform() {
        var sr = source.search(new ProductSearchQuery(
                "耳机", List.of(), null, null, null, List.of("京东-mock"), null, null));
        assertFalse(sr.products().isEmpty());
        for (var p : sr.products()) {
            assertEquals("京东-mock", p.platform());
        }
    }

    @Test
    void shouldFilterByMinRating() {
        var sr = source.search(new ProductSearchQuery(
                "耳机", List.of(), null, null, null, List.of(), null, 4.7));
        assertFalse(sr.products().isEmpty());
        for (var p : sr.products()) {
            assertTrue(p.rating() >= 4.7,
                    "rating should be >= 4.7, got: " + p.rating());
        }
    }

    @Test
    void shouldSortByPriceAsc() {
        var sr = source.search(new ProductSearchQuery(
                "耳机", List.of(), null, null, null, List.of(), "price_asc", null));
        assertFalse(sr.products().isEmpty());
        for (int i = 1; i < sr.products().size(); i++) {
            assertTrue(sr.products().get(i).price() >= sr.products().get(i - 1).price(),
                    "products should be sorted by price ascending");
        }
    }

    @Test
    void shouldSortBySalesDesc() {
        var sr = source.search(new ProductSearchQuery(
                "运动鞋", List.of(), null, null, null, List.of(), "sales_desc", null));
        for (int i = 1; i < sr.products().size(); i++) {
            assertTrue(sr.products().get(i).sales() <= sr.products().get(i - 1).sales(),
                    "products should be sorted by sales descending");
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
        assertEquals(12, sr.products().size());
        for (var p : sr.products()) {
            assertTrue(p.title().contains("背包") || p.title().contains("双肩")
                    || p.title().contains("背"),
                    "should be backpack: " + p.title());
        }
    }

    @Test
    void shouldRecognizeSmartwatchCategory() {
        assertEquals("智能手表",
                RuleBasedShoppingIntentParser.parseExplicitKeyword("智能手表"));
        var sr = source.search(new ProductSearchQuery("智能手表", List.of(), null));
        assertEquals(12, sr.products().size());
        for (var p : sr.products()) {
            assertTrue(p.title().contains("手表"),
                    "should be smartwatch: " + p.title());
        }
    }

    // ── Product brand metadata ──────────────────────────────

    @Test
    void productOfferShouldExposeBrandWhenSet() {
        var sr = source.search(new ProductSearchQuery("运动鞋", List.of(), null));
        boolean foundBranded = false;
        for (var p : sr.products()) {
            if (p.brand() != null && !p.brand().isBlank()) {
                foundBranded = true;
                break;
            }
        }
        assertTrue(foundBranded, "expected at least one product to expose brand metadata");
    }

    @Test
    void productOfferShouldExposePriceHistory() {
        var sr = source.search(new ProductSearchQuery("耳机", List.of(), null));
        for (var p : sr.products()) {
            assertFalse(p.priceHistory().isEmpty(),
                    "price history should be non-empty for product " + p.productId());
            assertTrue(p.priceHistory().size() >= 2,
                    "price history should have at least 2 points");
            assertEquals(p.price(), p.priceHistory().get(p.priceHistory().size() - 1),
                    0.1, "last price history point should equal current price");
        }
    }

    @Test
    void scoredProductShouldExposeMatchedPreferences() {
        var sr = source.search(new ProductSearchQuery(
                "耳机", List.of("lowest_price", "official_store"), 300.0,
                null, null, List.of(), null, null));
        assertFalse(sr.products().isEmpty());
        boolean anyMatched = sr.products().stream()
                .anyMatch(p -> !p.matchedPreferences().isEmpty());
        assertTrue(anyMatched, "at least one scored product should expose matchedPreferences");
    }

    // ── Combined filters ────────────────────────────────────

    @Test
    void shouldCombineBrandAndBudget() {
        var sr = source.search(new ProductSearchQuery(
                "运动鞋", List.of(), 400.0, null, "耐克", List.of(), null, null));
        for (var p : sr.products()) {
            assertTrue(p.title().contains("耐克"),
                    "should contain 耐克: " + p.title());
            assertTrue(p.price() <= 400.0,
                    "should respect budget: " + p.price());
        }
    }

    @Test
    void shouldCombinePlatformAndSort() {
        var sr = source.search(new ProductSearchQuery(
                "耳机", List.of(), null, null, null,
                List.of("京东-mock", "淘宝-mock"), "price_asc", null));
        for (var p : sr.products()) {
            assertTrue(p.platform().equals("京东-mock") || p.platform().equals("淘宝-mock"),
                    "platform should be in selected set");
        }
        for (int i = 1; i < sr.products().size(); i++) {
            assertTrue(sr.products().get(i).price() >= sr.products().get(i - 1).price());
        }
    }

    @Test
    void platformStatsShouldExposeAveragePrice() {
        var sr = source.search(new ProductSearchQuery("运动鞋", List.of(), null));
        assertFalse(sr.platformStats().isEmpty());
        for (var entry : sr.platformStats().entrySet()) {
            assertTrue(entry.getValue().averagePrice() > 0,
                    "averagePrice should be positive for " + entry.getKey());
            assertTrue(entry.getValue().averagePrice() >= entry.getValue().lowestPrice(),
                    "averagePrice should be >= lowestPrice");
        }
    }
}
