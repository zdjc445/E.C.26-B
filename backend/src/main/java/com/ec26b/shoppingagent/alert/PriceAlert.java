package com.ec26b.shoppingagent.alert;

import java.time.OffsetDateTime;

public record PriceAlert(
        long id,
        long userId,
        String productId,
        String title,
        String platform,
        double targetPrice,
        boolean triggered,
        Double lastObservedPrice,
        String note,
        OffsetDateTime createdAt
) {}
