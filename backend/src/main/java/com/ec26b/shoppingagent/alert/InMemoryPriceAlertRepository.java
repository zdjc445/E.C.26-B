package com.ec26b.shoppingagent.alert;

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
public class InMemoryPriceAlertRepository implements PriceAlertRepository {

    private final ConcurrentHashMap<Long, List<PriceAlert>> byUser = new ConcurrentHashMap<>();
    private final AtomicLong sequence = new AtomicLong(1);

    @Override
    public PriceAlert create(long userId, PriceAlertPayload payload) {
        var list = byUser.computeIfAbsent(userId, k -> new ArrayList<>());
        synchronized (list) {
            var alert = new PriceAlert(sequence.getAndIncrement(), userId,
                    payload.productId(), payload.title(), payload.platform(),
                    payload.targetPrice(), false, null, payload.note(), OffsetDateTime.now());
            list.add(alert);
            return alert;
        }
    }

    @Override
    public List<PriceAlert> listByUser(long userId) {
        var list = byUser.getOrDefault(userId, List.of());
        synchronized (list) {
            return list.stream()
                    .sorted(Comparator.comparing(PriceAlert::createdAt).reversed())
                    .toList();
        }
    }

    @Override
    public Optional<PriceAlert> findById(long userId, long alertId) {
        return listByUser(userId).stream().filter(a -> a.id() == alertId).findFirst();
    }

    @Override
    public Optional<PriceAlert> markObserved(long userId, long alertId, double observedPrice, boolean triggered) {
        var list = byUser.getOrDefault(userId, List.of());
        synchronized (list) {
            for (int i = 0; i < list.size(); i++) {
                var a = list.get(i);
                if (a.id() == alertId) {
                    var updated = new PriceAlert(a.id(), a.userId(), a.productId(), a.title(),
                            a.platform(), a.targetPrice(), triggered, observedPrice,
                            a.note(), a.createdAt());
                    list.set(i, updated);
                    return Optional.of(updated);
                }
            }
        }
        return Optional.empty();
    }

    @Override
    public boolean delete(long userId, long alertId) {
        var list = byUser.getOrDefault(userId, List.of());
        synchronized (list) {
            return list.removeIf(a -> a.id() == alertId);
        }
    }
}
