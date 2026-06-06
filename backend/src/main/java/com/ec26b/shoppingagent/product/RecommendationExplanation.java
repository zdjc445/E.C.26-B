package com.ec26b.shoppingagent.product;

import java.util.List;

public record RecommendationExplanation(
        int decisionScore,
        List<DecisionSignal> decisionSignals,
        List<RecommendationEvidence> evidence,
        List<String> risks,
        List<ProductAnalysis> productAnalyses,
        String summaryReason,
        String explanationProvider,
        boolean explanationFallbackUsed,
        List<String> notices
) {
    public RecommendationExplanation(int decisionScore, List<DecisionSignal> signals,
                                      List<RecommendationEvidence> evidence, List<String> risks,
                                      List<ProductAnalysis> analyses) {
        this(decisionScore, signals, evidence, risks, analyses,
                buildDefaultReason(analyses),
                "rule", false, List.of());
    }

    private static String buildDefaultReason(List<ProductAnalysis> analyses) {
        if (analyses == null || analyses.isEmpty()) return "综合评分较高";
        return analyses.get(0).title() + " 综合评分较高，推荐购买。";
    }

    public RecommendationExplanation withArkRewrite(
            String newSummaryReason,
            List<DecisionSignal> newSignals,
            List<RecommendationEvidence> newEvidence,
            List<String> newRisks,
            List<ProductAnalysis> newAnalyses) {
        return new RecommendationExplanation(
                this.decisionScore, newSignals, newEvidence, newRisks, newAnalyses,
                newSummaryReason, "ark", false, List.of());
    }

    public RecommendationExplanation withFallbackNotices(List<String> extraNotices) {
        var merged = new java.util.ArrayList<>(this.notices);
        merged.addAll(extraNotices);
        return new RecommendationExplanation(
                this.decisionScore, this.decisionSignals, this.evidence,
                this.risks, this.productAnalyses,
                this.summaryReason, "rule", true, merged);
    }
}
