package com.ec26b.shoppingagent.alert;

import java.util.List;
import java.util.Optional;

public interface PriceAlertRepository {

    PriceAlert create(long userId, PriceAlertPayload payload);

    List<PriceAlert> listByUser(long userId);

    Optional<PriceAlert> findById(long userId, long alertId);

    Optional<PriceAlert> markObserved(long userId, long alertId, double observedPrice, boolean triggered);

    boolean delete(long userId, long alertId);

    record PriceAlertPayload(
            String productId,
            String title,
            String platform,
            double targetPrice,
            String note
    ) {}
}
