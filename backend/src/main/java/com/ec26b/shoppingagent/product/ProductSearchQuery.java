package com.ec26b.shoppingagent.product;

import java.util.List;

public record ProductSearchQuery(
        String keyword,
        List<String> preferences,
        Double maxPrice
) {}
