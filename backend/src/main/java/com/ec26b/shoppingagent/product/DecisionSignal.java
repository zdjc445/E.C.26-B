package com.ec26b.shoppingagent.product;

public record DecisionSignal(
        String key,
        String label,
        int score,
        String explanation
) {}
