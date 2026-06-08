package com.ec26b.shoppingagent.product;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PublicDatasetProductSourceProviderTest {

    @Test
    void shouldLoadPublicProductsWithImages() {
        PublicDatasetProductSourceProvider source = new PublicDatasetProductSourceProvider(
                new RecommendationScorer(), new ObjectMapper(), "data/public-product-offers.json");

        ProductSearchResult result = source.search(new ProductSearchQuery("耳机", List.of(), null));

        assertFalse(result.products().isEmpty());
        for (ProductOffer product : result.products()) {
            assertEquals(PublicDatasetProductSourceProvider.PLATFORM, product.platform());
            assertTrue(product.imageUrl().startsWith("http://")
                    || product.imageUrl().startsWith("https://"));
            assertFalse(product.productUrl().isBlank());
        }
        assertTrue(result.platformStats().containsKey(PublicDatasetProductSourceProvider.PLATFORM));
    }

    @Test
    void shouldApplyBudgetAndSortToPublicProducts() {
        PublicDatasetProductSourceProvider source = new PublicDatasetProductSourceProvider(
                new RecommendationScorer(), new ObjectMapper(), "data/public-product-offers.json");

        ProductSearchResult result = source.search(new ProductSearchQuery(
                "背包", List.of(), 800.0, null, null, List.of(), "price_asc", null));

        assertFalse(result.products().isEmpty());
        for (ProductOffer product : result.products()) {
            assertTrue(product.price() <= 800.0);
        }
        for (int i = 1; i < result.products().size(); i++) {
            assertTrue(result.products().get(i).price() >= result.products().get(i - 1).price());
        }
    }
}
