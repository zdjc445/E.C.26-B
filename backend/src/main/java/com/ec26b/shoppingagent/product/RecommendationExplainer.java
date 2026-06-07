package com.ec26b.shoppingagent.product;

import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;

/**
 * Pure rule-based explainer — computes decisionScore, signals,
 * evidence, risks, and per-product analyses. No AI.
 */
@Component
public class RecommendationExplainer {

    /**
     * Build a full explanation for the given search result and user context.
     */
    public RecommendationExplanation explain(ProductSearchResult result,
                                              UserPreference pref,
                                              String keyword) {
        List<ProductOffer> products = result.products();
        if (products.isEmpty()) {
            return new RecommendationExplanation(0, List.of(), List.of(),
                    List.of("当前 Mock 商品库为空。"), List.of());
        }

        // ── Signals ──────────────────────────────────────────
        int matchScore = computeMatchSignal(products, keyword);
        int priceScore = computePriceSignal(products, pref);
        int repScore = computeReputationSignal(products, pref);
        int channelScore = computeChannelSignal(products, pref);
        int riskScore = computeRiskSignal(products);

        int decisionScore = weightedScore(matchScore, priceScore, repScore, channelScore, riskScore);

        List<DecisionSignal> signals = List.of(
                new DecisionSignal("match", "意图匹配", matchScore,
                        "商品与搜索关键词「" + keyword + "」的相关程度。"),
                new DecisionSignal("price", "价格", priceScore,
                        pref.lowestPrice() ? "你偏好低价，价格越低分数越高。" : "价格符合当前预算范围。"),
                new DecisionSignal("reputation", "店铺信誉", repScore,
                        "综合评分和销量反映商品受欢迎程度。"),
                new DecisionSignal("channel", "渠道可信", channelScore,
                        pref.officialStore() ? "你偏好官方/自营渠道。" : "平台与店铺类型评估。"),
                new DecisionSignal("risk", "风险", riskScore,
                        "Mock 数据不可作为真实购物参考，风险评分保守。")
        );

        // ── Evidence ────────────────────────────────────────
        List<RecommendationEvidence> evidence = new ArrayList<>();
        if (pref.maxPrice() != null) {
            evidence.add(new RecommendationEvidence("price",
                    "你设置了预算上限 " + pref.maxPrice().intValue() + " 元。"));
        }
        if (pref.color() != null) {
            evidence.add(new RecommendationEvidence("color",
                    "你偏好「" + pref.color() + "」颜色。"));
        }
        if (pref.brand() != null) {
            evidence.add(new RecommendationEvidence("brand",
                    "你指定了品牌「" + pref.brand() + "」。"));
        }
        if (pref.platforms() != null && !pref.platforms().isEmpty()) {
            evidence.add(new RecommendationEvidence("platform",
                    "你只看以下平台：" + String.join("、", pref.platforms()) + "。"));
        }
        if (pref.minRating() != null) {
            evidence.add(new RecommendationEvidence("rating",
                    "你要求评分 ≥ " + pref.minRating() + " 星。"));
        }
        if (pref.sortBy() != null) {
            String sortLabel = switch (pref.sortBy()) {
                case "price_asc" -> "价格从低到高";
                case "price_desc" -> "价格从高到低";
                case "sales_desc" -> "销量优先";
                case "rating_desc" -> "好评率优先";
                default -> "综合推荐";
            };
            evidence.add(new RecommendationEvidence("sort",
                    "按「" + sortLabel + "」排序。"));
        }
        ProductOffer top = result.topPick();
        if (top != null) {
            String priceEvidence = pref.maxPrice() != null
                    ? "当前推荐价格 " + String.format("%.2f", top.price()) + " 元，符合预算。"
                    : "当前推荐价格 " + String.format("%.2f", top.price()) + " 元。";
            evidence.add(new RecommendationEvidence("price",
                    priceEvidence));
        }

        // ── Risks ───────────────────────────────────────────
        List<String> risks = new ArrayList<>();
        risks.add("当前为 Mock 商品数据，不代表真实平台库存与价格。");
        if (pref.fastDelivery()) {
            risks.add("配送时效为 Mock 估算，实际以平台显示为准。");
        }

        // ── Product analyses ────────────────────────────────
        List<ProductAnalysis> analyses = new ArrayList<>();
        for (int i = 0; i < Math.min(products.size(), 3); i++) {
            ProductOffer p = products.get(i);
            List<String> strengths = new ArrayList<>(p.reasons());
            List<String> weaknesses = new ArrayList<>();
            if (!p.tags().contains("官方") && !p.tags().contains("旗舰店") && !p.tags().contains("自营")) {
                weaknesses.add("非官方/自营渠道");
            }
            if (p.rating() < 4.5) weaknesses.add("评分偏低");
            int score = (int) Math.round(p.score() / 10.0 * 100);
            analyses.add(new ProductAnalysis(p.productId(), p.platform(), p.title(),
                    i + 1, Math.min(score, 100), strengths, weaknesses));
        }

        return new RecommendationExplanation(decisionScore, signals, evidence, risks, analyses);
    }

    private int computeMatchSignal(List<ProductOffer> products, String keyword) {
        long count = products.stream().filter(p ->
                p.title().contains(keyword) || p.tags().stream().anyMatch(t -> t.contains(keyword))).count();
        return products.isEmpty() ? 0 : (int) Math.round((double) count / products.size() * 60 + 25);
    }

    private int computePriceSignal(List<ProductOffer> products, UserPreference pref) {
        if (products.isEmpty()) return 50;
        double avg = products.stream().mapToDouble(ProductOffer::price).average().orElse(200);
        double best = products.stream().mapToDouble(ProductOffer::price).min().orElse(0);
        int score = 60;
        if (pref.lowestPrice() && best < avg * 0.8) score += 30;
        if (pref.maxPrice() != null && best <= pref.maxPrice()) score += 10;
        return Math.min(score, 100);
    }

    private int computeReputationSignal(List<ProductOffer> products, UserPreference pref) {
        double avgRating = products.stream().mapToDouble(ProductOffer::rating).average().orElse(4.0);
        int score = (int) Math.round(avgRating * 15);
        if (pref.highRating()) score += 15;
        if (pref.highSales()) score += 10;
        return Math.min(score, 100);
    }

    private int computeChannelSignal(List<ProductOffer> products, UserPreference pref) {
        long officialCount = products.stream().filter(p ->
                p.tags().contains("官方") || p.tags().contains("旗舰店") || p.tags().contains("自营")).count();
        int score = products.isEmpty() ? 0 : (int) Math.round((double) officialCount / products.size() * 60 + 20);
        if (pref.officialStore()) score += 20;
        return Math.min(score, 100);
    }

    private int computeRiskSignal(List<ProductOffer> products) {
        // Mock data is inherently risky — cap the score
        return 40;
    }

    private int weightedScore(int match, int price, int rep, int channel, int risk) {
        double s = match * 0.25 + price * 0.25 + rep * 0.20 + channel * 0.15 + risk * 0.15;
        return Math.min((int) Math.round(s), 100);
    }
}
