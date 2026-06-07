package com.ec26b.shoppingagent.favorite;

import java.util.List;
import java.util.Optional;

public interface FavoriteRepository {

    Favorite add(long userId, FavoritePayload payload);

    List<Favorite> listByUser(long userId);

    Optional<Favorite> findByUserAndProduct(long userId, String productId);

    boolean delete(long userId, String productId);

    record FavoritePayload(
            String productId,
            String title,
            String platform,
            double price,
            String shopName,
            String brand,
            String imageUrl,
            String productUrl
    ) {}
}
