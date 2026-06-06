package com.ec26b.shoppingagent.product;

import java.util.List;

public record RecommendationExplanation(
        int decisionScore,
        List<DecisionSignal> decisionSignals,
        List<RecommendationEvidence> evidence,
        List<String> risks,
        List<ProductAnalysis> productAnalyses
) {}
