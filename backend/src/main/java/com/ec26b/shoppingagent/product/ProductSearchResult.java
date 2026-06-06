package com.ec26b.shoppingagent.product;

import java.util.List;
import java.util.Map;

public record ProductSearchResult(
        List<ProductOffer> products,
        Map<String, PlatformStats> platformStats,
        ProductOffer topPick
) {

    public record PlatformStats(
            String platform,
            double lowestPrice,
            int productCount,
            String highlight
    ) {}
}
