package com.ec26b.shoppingagent.product;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertTrue;

class CompositeProductSourceProviderTest {

    @Test
    void shouldMergePublicDatasetAndMockProducts() {
        MockProductSourceProvider mock = new MockProductSourceProvider(new RecommendationScorer());
        PublicDatasetProductSourceProvider publicDataset = new PublicDatasetProductSourceProvider(
                new RecommendationScorer(), new ObjectMapper(), "data/public-product-offers.json");
        CompositeProductSourceProvider composite = new CompositeProductSourceProvider(
                mock, publicDataset, "public-dataset");

        ProductSearchResult result = composite.search(new ProductSearchQuery("耳机", List.of(), null));

        assertTrue(result.products().stream()
                .anyMatch(p -> PublicDatasetProductSourceProvider.PLATFORM.equals(p.platform())
                        && !p.imageUrl().isBlank()));
        assertTrue(result.products().stream()
                .anyMatch(p -> "京东-mock".equals(p.platform())));
        assertTrue(result.platformStats().containsKey(PublicDatasetProductSourceProvider.PLATFORM));
        assertTrue(result.platformStats().containsKey("京东-mock"));
    }
}
