package com.ec26b.shoppingagent.product;

import java.util.List;

public record ProductSearchQuery(
        String keyword,
        List<String> preferences,
        Double maxPrice,
        String color
) {
    public ProductSearchQuery(String keyword, List<String> preferences, Double maxPrice) {
        this(keyword, preferences, maxPrice, null);
    }
}
