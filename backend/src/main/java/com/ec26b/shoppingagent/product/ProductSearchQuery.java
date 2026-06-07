package com.ec26b.shoppingagent.product;

import java.util.List;

public record ProductSearchQuery(
        String keyword,
        List<String> preferences,
        Double maxPrice,
        String color,
        String brand,
        List<String> platforms,
        String sortBy,
        Double minRating
) {
    public ProductSearchQuery {
        preferences = preferences == null ? List.of() : List.copyOf(preferences);
        platforms = platforms == null ? List.of() : List.copyOf(platforms);
    }

    public ProductSearchQuery(String keyword, List<String> preferences, Double maxPrice) {
        this(keyword, preferences, maxPrice, null, null, List.of(), null, null);
    }

    public ProductSearchQuery(String keyword, List<String> preferences, Double maxPrice, String color) {
        this(keyword, preferences, maxPrice, color, null, List.of(), null, null);
    }
}
