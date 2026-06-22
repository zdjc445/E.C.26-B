package com.ec26b.shoppingagent.product;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CompositeProductSourceProviderTest {

    @Test
    void shouldReturnDomesticPlatformsOnlyByDefault() {
        CompositeProductSourceProvider provider = newProvider();

        ProductSearchResult result = provider.search(new ProductSearchQuery("运动鞋", List.of(), null));

        assertFalse(result.products().isEmpty(), "Should have products");
        Set<String> platforms = result.products().stream()
                .map(ProductOffer::platform)
                .collect(Collectors.toSet());
        for (String platform : platforms) {
            assertTrue(CompositeProductSourceProvider.DOMESTIC_PLATFORMS.contains(platform),
                    "Platform should be domestic but was: " + platform);
        }
        assertFalse(platforms.contains(PublicDatasetProductSourceProvider.PLATFORM));
    }

    @Test
    void shouldGenerateMultiplePlatformsPerProduct() {
        CompositeProductSourceProvider provider = newProvider();

        ProductSearchResult result = provider.search(new ProductSearchQuery("耳机", List.of(), null));

        assertFalse(result.products().isEmpty());
        long distinctKeys = result.products().stream()
                .map(ProductOffer::sameItemKey)
                .distinct()
                .count();
        assertEquals(75, distinctKeys);
        assertEquals(distinctKeys * CompositeProductSourceProvider.DOMESTIC_PLATFORMS.size(),
                result.products().size());
    }

    @Test
    void shouldFilterByPlatform() {
        CompositeProductSourceProvider provider = newProvider();

        ProductSearchResult result = provider.search(new ProductSearchQuery(
                "运动鞋", List.of(), null, null, null,
                List.of("京东-mock"), null, null));

        assertFalse(result.products().isEmpty());
        for (ProductOffer product : result.products()) {
            assertEquals("京东-mock", product.platform());
        }
    }

    @Test
    void shouldFilterByMinRating() {
        CompositeProductSourceProvider provider = newProvider();

        ProductSearchResult result = provider.search(new ProductSearchQuery(
                "运动鞋", List.of(), null, null, null,
                List.of(), null, 4.5));

        for (ProductOffer product : result.products()) {
            assertTrue(product.rating() >= 4.5,
                    "Rating should be >= 4.5 but was " + product.rating());
        }
    }

    @Test
    void shouldSortByPriceAsc() {
        CompositeProductSourceProvider provider = newProvider();

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
        CompositeProductSourceProvider provider = newProvider(
                CompositeProductSourceProvider.MODE_PUBLIC_DATASET_ONLY);

        ProductSearchResult result = provider.search(new ProductSearchQuery("耳机", List.of(), null));

        assertFalse(result.products().isEmpty());
        assertEquals("public-dataset", provider.sourceName());
        for (ProductOffer product : result.products()) {
            assertEquals(PublicDatasetProductSourceProvider.PLATFORM, product.platform());
            assertTrue(product.imageUrl().startsWith("http"));
        }
    }

    @Test
    void shouldUsePublicDatasetWithGeneratedPlatforms() {
        CompositeProductSourceProvider provider = newProvider(
                CompositeProductSourceProvider.MODE_PUBLIC_DATASET_PLATFORMS);

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

    @Test
    void shouldFallbackUnknownModeToGeneratedPlatforms() {
        CompositeProductSourceProvider provider = newProvider("public-dataset");

        ProductSearchResult result = provider.search(new ProductSearchQuery("耳机", List.of(), null));
        Set<String> platforms = result.products().stream()
                .map(ProductOffer::platform)
                .collect(Collectors.toSet());

        assertEquals("public-dataset-platforms", provider.sourceName());
        assertTrue(platforms.contains("京东-mock"));
        assertFalse(platforms.contains(PublicDatasetProductSourceProvider.PLATFORM));
    }

    private CompositeProductSourceProvider newProvider() {
        return newProvider(CompositeProductSourceProvider.MODE_PUBLIC_DATASET_PLATFORMS);
    }

    private CompositeProductSourceProvider newProvider(String mode) {
        ObjectMapper objectMapper = new ObjectMapper();
        RecommendationScorer scorer = new RecommendationScorer();
        PublicDatasetProductSourceProvider publicDataset =
                new PublicDatasetProductSourceProvider(
                        scorer, objectMapper, "data/public-product-offers.json");
        return new CompositeProductSourceProvider(publicDataset, mode);
    }
}
