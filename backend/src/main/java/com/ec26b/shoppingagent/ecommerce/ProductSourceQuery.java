package com.ec26b.shoppingagent.ecommerce;

import java.util.Map;

public record ProductSourceQuery(
        String keyword,
        String category,
        String brand,
        String model,
        Map<String, Object> filters,
        String sortBy,
        int pageSize
) {
}
