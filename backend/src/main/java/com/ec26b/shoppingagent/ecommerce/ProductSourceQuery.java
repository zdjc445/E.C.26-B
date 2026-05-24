package com.ec26b.shoppingagent.ecommerce;

import java.util.List;
import java.util.Map;

public record ProductSourceQuery(
        String keyword,
        String category,
        String brand,
        String model,
        Map<String, Object> filters,
        List<String> platforms,
        String sortBy,
        int pageSize
) {
}
