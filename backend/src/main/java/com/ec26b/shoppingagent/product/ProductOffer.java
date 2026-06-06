package com.ec26b.shoppingagent.product;

import java.util.List;

public record ProductOffer(
        String productId,
        String title,
        String platform,
        double price,
        double originalPrice,
        String shopName,
        String imageUrl,
        String productUrl,
        double rating,
        int sales,
        List<String> tags,
        List<String> reasons,
        double score
) {}
