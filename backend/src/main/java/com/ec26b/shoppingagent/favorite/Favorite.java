package com.ec26b.shoppingagent.favorite;

import java.time.OffsetDateTime;

public record Favorite(
        long id,
        long userId,
        String productId,
        String title,
        String platform,
        double price,
        String shopName,
        String brand,
        String imageUrl,
        String productUrl,
        OffsetDateTime createdAt
) {}
