package com.ec26b.shoppingagent.favorite;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

@Component
@ConditionalOnProperty(name = "chat.history-store", havingValue = "memory", matchIfMissing = true)
public class InMemoryFavoriteRepository implements FavoriteRepository {

    private final ConcurrentHashMap<Long, List<Favorite>> byUser = new ConcurrentHashMap<>();
    private final AtomicLong sequence = new AtomicLong(1);

    @Override
    public Favorite add(long userId, FavoritePayload payload) {
        List<Favorite> list = byUser.computeIfAbsent(userId, k -> new ArrayList<>());
        synchronized (list) {
            list.removeIf(f -> f.productId().equals(payload.productId()));
            var fav = new Favorite(sequence.getAndIncrement(), userId,
                    payload.productId(), payload.title(), payload.platform(),
                    payload.price(), payload.shopName(), payload.brand(),
                    payload.imageUrl(), payload.productUrl(), OffsetDateTime.now());
            list.add(fav);
            return fav;
        }
    }

    @Override
    public List<Favorite> listByUser(long userId) {
        List<Favorite> list = byUser.getOrDefault(userId, List.of());
        synchronized (list) {
            return list.stream()
                    .sorted(Comparator.comparing(Favorite::createdAt).reversed())
                    .toList();
        }
    }

    @Override
    public Optional<Favorite> findByUserAndProduct(long userId, String productId) {
        return listByUser(userId).stream().filter(f -> f.productId().equals(productId)).findFirst();
    }

    @Override
    public boolean delete(long userId, String productId) {
        List<Favorite> list = byUser.getOrDefault(userId, List.of());
        synchronized (list) {
            return list.removeIf(f -> f.productId().equals(productId));
        }
    }
}
