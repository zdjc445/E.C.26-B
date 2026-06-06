package com.ec26b.shoppingagent.product;

import java.util.List;

public record ProductAnalysis(
        String productId,
        String platform,
        String title,
        int rank,
        int score,
        List<String> strengths,
        List<String> weaknesses
) {}
