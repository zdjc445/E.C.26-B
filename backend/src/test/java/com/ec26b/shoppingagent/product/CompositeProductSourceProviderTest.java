package com.ec26b.shoppingagent.product;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;

class CompositeProductSourceProviderTest {

    @Test
    void shouldReturnDomesticPlatformsOnly() {
        CompositeProductSourceProvider provider = new CompositeProductSourceProvider(
                new ObjectMapper(), "../mock-data/mock-data.json", null, new RecommendationScorer());

        ProductSearchResult result = provider.search(new ProductSearchQuery("运动鞋", List.of(), null));

        assertFalse(result.products().isEmpty(), "Should have products");
        // All platforms should be domestic, no Flipkart
        Set<String> platforms = result.products().stream()
                .map(ProductOffer::platform)
                .collect(Collectors.toSet());
        for (String p : platforms) {
            assertTrue(CompositeProductSourceProvider.DOMESTIC_PLATFORMS.contains(p),
                    "Platform should be domestic but was: " + p);
        }
        assertFalse(platforms.contains("Flipkart-sample"), "Should not contain Flipkart");
    }

    @Test
    void shouldGenerateMultiplePlatformsPerProduct() {
        CompositeProductSourceProvider provider = new CompositeProductSourceProvider(
                new ObjectMapper(), "../mock-data/mock-data.json", null, new RecommendationScorer());

        ProductSearchResult result = provider.search(new ProductSearchQuery("耳机", List.of(), null));

        assertFalse(result.products().isEmpty());
        // Each product (sameItemKey) should have 4 offers (one per domestic platform)
        long distinctKeys = result.products().stream()
                .map(ProductOffer::sameItemKey)
                .distinct()
                .count();
        assertTrue(distinctKeys >= 2, "Should have multiple product groups");
        assertTrue(result.products().size() >= distinctKeys * 4,
                "Each product should have 4 platform offers");
    }

    @Test
    void shouldFilterByPlatform() {
        CompositeProductSourceProvider provider = new CompositeProductSourceProvider(
                new ObjectMapper(), "../mock-data/mock-data.json", null, new RecommendationScorer());

        ProductSearchResult result = provider.search(new ProductSearchQuery(
                "运动鞋", List.of(), null, null, null,
                List.of("京东-mock"), null, null));

        assertFalse(result.products().isEmpty());
        for (ProductOffer p : result.products()) {
            assertEquals("京东-mock", p.platform());
        }
    }

    @Test
    void shouldFilterByMinRating() {
        CompositeProductSourceProvider provider = new CompositeProductSourceProvider(
                new ObjectMapper(), "../mock-data/mock-data.json", null, new RecommendationScorer());

        ProductSearchResult result = provider.search(new ProductSearchQuery(
                "运动鞋", List.of(), null, null, null,
                List.of(), null, 4.5));

        for (ProductOffer p : result.products()) {
            assertTrue(p.rating() >= 4.5,
                    "Rating should be >= 4.5 but was " + p.rating());
        }
    }

    @Test
    void shouldSortByPriceAsc() {
        CompositeProductSourceProvider provider = new CompositeProductSourceProvider(
                new ObjectMapper(), "../mock-data/mock-data.json", null, new RecommendationScorer());

        ProductSearchResult result = provider.search(new ProductSearchQuery(
                "运动鞋", List.of(), null, null, null,
                List.of(), "price_asc", null));

        for (int i = 1; i < result.products().size(); i++) {
            assertTrue(result.products().get(i).price() >= result.products().get(i - 1).price(),
                    "Products should be sorted by price ascending");
        }
    }

    @Test
    void shouldSwitchToPublicDatasetOnly() {
        CompositeProductSourceProvider provider = new CompositeProductSourceProvider(
                new ObjectMapper(), "../mock-data/mock-data.json",
                "data/public-product-offers.json", "public-dataset-only",
                null, new RecommendationScorer());

        ProductSearchResult result = provider.search(new ProductSearchQuery("耳机", List.of(), null));

        assertFalse(result.products().isEmpty());
        assertEquals("public-dataset", provider.sourceName());
        for (ProductOffer p : result.products()) {
            assertEquals(PublicDatasetProductSourceProvider.PLATFORM, p.platform());
            assertTrue(p.imageUrl().startsWith("http"));
        }
    }

    @Test
    void shouldMergePublicDatasetAndMockData() {
        CompositeProductSourceProvider provider = new CompositeProductSourceProvider(
                new ObjectMapper(), "../mock-data/mock-data.json",
                "data/public-product-offers.json", "public-dataset",
                null, new RecommendationScorer());

        ProductSearchResult result = provider.search(new ProductSearchQuery("耳机", List.of(), null));
        Set<String> platforms = result.products().stream()
                .map(ProductOffer::platform)
                .collect(Collectors.toSet());

        assertEquals("public-dataset+mock-data", provider.sourceName());
        assertTrue(platforms.contains(PublicDatasetProductSourceProvider.PLATFORM));
        assertTrue(platforms.contains("京东-mock"));
    }

    @Test
    void shouldUsePublicDatasetWithGeneratedPlatforms() {
        CompositeProductSourceProvider provider = new CompositeProductSourceProvider(
                new ObjectMapper(), "../mock-data/mock-data.json",
                "data/public-product-offers.json", "public-dataset-platforms",
                null, new RecommendationScorer());

        ProductSearchResult result = provider.search(new ProductSearchQuery("耳机", List.of(), null));
        Set<String> platforms = result.products().stream()
                .map(ProductOffer::platform)
                .collect(Collectors.toSet());

        assertEquals("public-dataset-platforms", provider.sourceName());
        assertTrue(platforms.contains("京东-mock"));
        assertTrue(platforms.contains("拼多多-mock"));
        assertFalse(platforms.contains(PublicDatasetProductSourceProvider.PLATFORM));
        assertTrue(result.products().stream().allMatch(p -> p.imageUrl().startsWith("http")));
    }
}
