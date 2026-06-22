package com.ec26b.shoppingagent.product;

import org.springframework.stereotype.Component;

import java.util.*;

/**
 * Builds structured recommendation explanations from scored search results.
 *
 * <h3>Five decision signals (0–100):</h3>
 * <ol>
 *   <li><b>match (意图匹配)</b> — how well results align with the search keyword,
 *       using title/brand/tag hit rate across the candidate set</li>
 *   <li><b>price (价格优势)</b> — based on actual price distribution: within-budget
 *       ratio, below-median ratio, and price spread</li>
 *   <li><b>reputation (口碑信誉)</b> — composite of rating distribution and
 *       sales volume, weighted toward the top-ranked products</li>
 *   <li><b>channel (渠道可信)</b> — mix of platform quality and official-store
 *       availability in the result set</li>
 *   <li><b>risk (风险)</b> — dynamic: penalizes single-platform concentration,
 *       wide price spreads, absence of official stores, and low rating variance
 *       (which may indicate fabricated reviews)</li>
 * </ol>
 *
 * <p>Product analyses now use actual {@link ProductOffer#matchedPreferences()}
 * and {@link ProductOffer#score()} to generate concrete strengths/weaknesses
 * instead of generic boilerplate.
 */
@Component
public class RecommendationExplainer {

    /** Minimum products for meaningful statistics. */
    private static final int MIN_SAMPLE = 2;

    /**
     * Build a full explanation for the given search result and user context.
     */
    public RecommendationExplanation explain(ProductSearchResult result,
                                              UserPreference pref,
                                              String keyword) {
        List<ProductOffer> products = result.products();
        if (products.isEmpty()) {
            return new RecommendationExplanation(0, List.of(), List.of(),
                    List.of("当前商品库中没有匹配结果。"), List.of());
        }

        // ── Pre-compute set statistics ─────────────────────────
        Stats stats = computeStats(products, pref, keyword);

        // ── Signals (0–100 each) ──────────────────────────────
        int matchScore = computeMatchSignal(products, keyword);
        int priceScore = computePriceSignal(products, pref, stats);
        int repScore = computeReputationSignal(products, pref, stats);
        int channelScore = computeChannelSignal(products, pref, stats);
        int riskScore = computeRiskSignal(products, stats);

        int decisionScore = weightedScore(matchScore, priceScore, repScore,
                channelScore, riskScore);

        List<DecisionSignal> signals = new ArrayList<>();
        signals.add(new DecisionSignal("match", "意图匹配", matchScore,
                signalMatchExplanation(matchScore, keyword, stats.matchHitRate)));
        signals.add(new DecisionSignal("price", "价格", priceScore,
                signalPriceExplanation(priceScore, pref, stats)));
        signals.add(new DecisionSignal("reputation", "店铺信誉", repScore,
                signalRepExplanation(repScore, stats)));
        signals.add(new DecisionSignal("channel", "渠道可信", channelScore,
                signalChannelExplanation(channelScore, pref, stats)));
        signals.add(new DecisionSignal("risk", "风险", riskScore,
                signalRiskExplanation(riskScore, stats)));

        // ── Evidence ───────────────────────────────────────────
        List<RecommendationEvidence> evidence = buildEvidence(pref, stats);

        // ── Risks ──────────────────────────────────────────────
        List<String> risks = buildRisks(stats);

        // ── Product analyses ───────────────────────────────────
        List<ProductAnalysis> analyses = buildAnalyses(products);

        return new RecommendationExplanation(decisionScore, signals, evidence, risks, analyses);
    }

    // ── Statistics ────────────────────────────────────────────────

    private static class Stats {
        double avgPrice, priceMin, priceMax, priceMedian, priceSpread;
        double avgRating, ratingP75, ratingP25;
        double avgSales;
        double matchHitRate;
        double officialRatio;
        int platformCount;
        int productCount;
        long underBudgetCount;
        boolean hasPriceVolatility;
        boolean singlePlatform;
        boolean noOfficialStore;
        boolean lowRatingVariance;
    }

    private Stats computeStats(List<ProductOffer> products, UserPreference pref, String keyword) {
        Stats s = new Stats();
        s.productCount = products.size();

        double[] prices = products.stream().mapToDouble(ProductOffer::price).sorted().toArray();
        double[] ratings = products.stream().mapToDouble(ProductOffer::rating).sorted().toArray();

        s.avgPrice = Arrays.stream(prices).average().orElse(0);
        s.priceMin = prices.length > 0 ? prices[0] : 0;
        s.priceMax = prices.length > 0 ? prices[prices.length - 1] : 0;
        s.priceMedian = percentile(prices, 0.5);
        s.priceSpread = s.priceMax > 0 ? (s.priceMax - s.priceMin) / s.priceMax : 0;

        s.avgRating = Arrays.stream(ratings).average().orElse(0);
        s.ratingP75 = percentile(ratings, 0.75);
        s.ratingP25 = percentile(ratings, 0.25);
        s.lowRatingVariance = (s.ratingP75 - s.ratingP25) < 0.3;

        s.avgSales = products.stream().mapToInt(ProductOffer::sales).average().orElse(0);

        // Match hit rate
        if (keyword != null && !keyword.isBlank()) {
            long matches = products.stream()
                    .filter(p -> p.title().contains(keyword)
                            || (p.brand() != null && p.brand().contains(keyword)))
                    .count();
            s.matchHitRate = (double) matches / products.size();
        } else {
            s.matchHitRate = 0.8;
        }

        // Official store ratio
        long official = products.stream()
                .filter(p -> p.tags().stream().anyMatch(t ->
                        t.contains("官方") || t.contains("旗舰店") || t.contains("自营")
                                || t.contains("正品保障")))
                .count();
        s.officialRatio = (double) official / products.size();
        s.noOfficialStore = official == 0;

        // Platform diversity
        s.platformCount = (int) products.stream().map(ProductOffer::platform).distinct().count();
        s.singlePlatform = s.platformCount <= 1;

        // Budget
        if (pref != null && pref.maxPrice() != null) {
            double budget = pref.maxPrice();
            s.underBudgetCount = products.stream().filter(p -> p.price() <= budget).count();
        } else {
            s.underBudgetCount = products.size();
        }

        // Price volatility: if price range > 40% of max
        s.hasPriceVolatility = s.priceSpread > 0.4;

        return s;
    }

    // ── Signal computation ────────────────────────────────────────

    private int computeMatchSignal(List<ProductOffer> products, String keyword) {
        if (keyword == null || keyword.isBlank()) return 60;
        // Use ProductVectorIndex tokenization for better hit detection
        List<String> kwTokens = ProductVectorIndex.tokenize(keyword);
        if (kwTokens.isEmpty()) return 60;

        long hitCount = 0;
        for (ProductOffer p : products) {
            String haystack = (p.title() + " " + (p.brand() != null ? p.brand() : "")
                    + " " + String.join(" ", p.tags())).toLowerCase();
            boolean hit = false;
            for (String token : kwTokens) {
                if (haystack.contains(token)) { hit = true; break; }
            }
            if (hit) hitCount++;
        }
        double hitRate = products.isEmpty() ? 0 : (double) hitCount / products.size();
        // Scale: 30 base + 70 × hitRate² (convex — rewards high coverage)
        return (int) Math.round(30 + 70 * hitRate * hitRate);
    }

    private int computePriceSignal(List<ProductOffer> products, UserPreference pref, Stats s) {
        int score = 50;
        if (products.size() < MIN_SAMPLE) return score;

        // Budget fit
        if (pref != null && pref.maxPrice() != null && pref.maxPrice() > 0) {
            double budgetRatio = (double) s.underBudgetCount / products.size();
            score += (int) Math.round(budgetRatio * 30); // up to +30
        }

        // Price advantage: how many are below median
        long belowMedian = products.stream().filter(p -> p.price() <= s.priceMedian).count();
        double belowRatio = (double) belowMedian / products.size();
        score += (int) Math.round(belowRatio * 15); // up to +15

        // Price spread bonus: tight spread = consistent pricing
        if (s.priceSpread < 0.2) score += 10;
        else if (s.priceSpread < 0.35) score += 5;

        // Low price amplification per user preference
        if (pref != null && pref.lowestPrice() && s.priceMin < s.avgPrice * 0.75) {
            score += 10;
        }

        return clamp(score);
    }

    private int computeReputationSignal(List<ProductOffer> products, UserPreference pref, Stats s) {
        int score = (int) Math.round(s.avgRating * 15); // 0-75 base from 0-5 scale

        // Sales boost
        if (s.avgSales > 5000) score += 10;
        else if (s.avgSales > 2000) score += 5;

        // Top products weighted more heavily
        double top3AvgRating = products.stream()
                .limit(3)
                .mapToDouble(ProductOffer::rating)
                .average().orElse(s.avgRating);
        if (top3AvgRating > s.avgRating + 0.2) score += 5;

        // Rating reliability: wider spread = more genuine
        if (!s.lowRatingVariance) score += 5;
        else score -= 5;

        if (pref != null && pref.highRating()) score += 10;
        if (pref != null && pref.highSales()) score += 5;

        return clamp(score);
    }

    private int computeChannelSignal(List<ProductOffer> products, UserPreference pref, Stats s) {
        int score = 35;

        // Official store availability
        score += (int) Math.round(s.officialRatio * 45); // up to +45

        // Platform diversity
        score += Math.min(s.platformCount * 5, 15); // up to +15

        // Platform quality weighting
        double avgPlatformQuality = products.stream()
                .mapToDouble(p -> platformQualityScore(p.platform()))
                .average().orElse(0.5);
        score += (int) Math.round(avgPlatformQuality * 5); // up to +5

        if (pref != null && pref.officialStore()) {
            if (s.officialRatio > 0.5) score += 10;
            else if (s.noOfficialStore) score -= 20;
        }

        return clamp(score);
    }

    private int computeRiskSignal(List<ProductOffer> products, Stats s) {
        // Start at 80 (low risk), deduct for each concern
        int score = 80;

        if (s.singlePlatform && s.productCount > 1) score -= 20;
        if (s.noOfficialStore && s.productCount > 2) score -= 15;
        if (s.hasPriceVolatility) score -= 10;
        if (s.lowRatingVariance && s.productCount > 3) score -= 10; // suspicious uniformity
        if (s.avgRating < 4.2) score -= 10;
        if (s.productCount < 3) score -= 5; // too few options
        if (s.officialRatio < 0.25 && s.productCount > 4) score -= 5;

        return clamp(score);
    }

    // ── Signal explanations ───────────────────────────────────────

    private String signalMatchExplanation(int score, String keyword, double hitRate) {
        if (score >= 85) return "商品与「" + keyword + "」高度匹配，覆盖率高。";
        if (score >= 70) return "大部分商品与「" + keyword + "」相关。";
        if (score >= 50) return "部分商品与「" + keyword + "」匹配度一般。";
        return "搜索结果与「" + keyword + "」的匹配度较低，可尝试更换关键词。";
    }

    private String signalPriceExplanation(int score, UserPreference pref, Stats s) {
        StringBuilder sb = new StringBuilder();
        if (score >= 80) sb.append("价格分布合理，");
        else if (score >= 60) sb.append("价格适中，");
        else sb.append("价格偏高或分散，");

        if (pref != null && pref.maxPrice() != null) {
            sb.append(String.format("%d/%d 件在预算内。",
                    s.underBudgetCount, s.productCount));
        } else {
            sb.append(String.format("均价 ¥%.0f，范围 ¥%.0f–¥%.0f。",
                    s.avgPrice, s.priceMin, s.priceMax));
        }
        return sb.toString();
    }

    private String signalRepExplanation(int score, Stats s) {
        if (score >= 80) return String.format("均分 %.1f 星，口碑优秀。", s.avgRating);
        if (score >= 60) return String.format("均分 %.1f 星，口碑良好。", s.avgRating);
        return String.format("均分 %.1f 星，建议关注具体评价。", s.avgRating);
    }

    private String signalChannelExplanation(int score, UserPreference pref, Stats s) {
        StringBuilder sb = new StringBuilder();
        long officialPct = Math.round(s.officialRatio * 100);
        if (officialPct >= 50) sb.append("过半为官方/自营渠道，");
        else if (officialPct > 0) sb.append("含" + officialPct + "%官方渠道，");
        else sb.append("均为第三方店铺，");

        sb.append(s.platformCount).append(" 个平台");
        if (s.platformCount >= 3) sb.append("，选择多样");
        else if (s.platformCount == 2) sb.append("可比价");
        else sb.append("，平台单一");

        sb.append("。");
        return sb.toString();
    }

    private String signalRiskExplanation(int score, Stats s) {
        List<String> concerns = new ArrayList<>();
        if (s.singlePlatform && s.productCount > 1) concerns.add("单一平台货源");
        if (s.noOfficialStore) concerns.add("缺少官方渠道");
        if (s.hasPriceVolatility) concerns.add("价格波动较大");
        if (s.lowRatingVariance && s.productCount > 3) concerns.add("评分过于一致");

        if (concerns.isEmpty()) return "未发现明显风险因素，当前为 Mock 数据仅供参考。";
        return "关注点：" + String.join("、", concerns) + "。（Mock 数据仅供参考）";
    }

    // ── Evidence ──────────────────────────────────────────────────

    private List<RecommendationEvidence> buildEvidence(UserPreference pref, Stats s) {
        List<RecommendationEvidence> evidence = new ArrayList<>();

        if (pref != null) {
            if (pref.maxPrice() != null) {
                evidence.add(new RecommendationEvidence("price",
                        "预算上限 ¥" + String.format("%.0f", pref.maxPrice())
                                + "，" + s.underBudgetCount + "/" + s.productCount + " 件在预算内。"));
            }
            if (pref.color() != null) {
                evidence.add(new RecommendationEvidence("color", "已筛选颜色「" + pref.color() + "」。"));
            }
            if (pref.brand() != null && !pref.brand().isBlank()) {
                evidence.add(new RecommendationEvidence("brand", "已筛选品牌「" + pref.brand() + "」。"));
            }
            if (pref.platforms() != null && !pref.platforms().isEmpty()
                    && pref.platforms().size() < 4) {
                evidence.add(new RecommendationEvidence("platform",
                        "限定平台：" + String.join("、", pref.platforms()) + "。"));
            }
            if (pref.minRating() != null && pref.minRating() > 0) {
                evidence.add(new RecommendationEvidence("rating",
                        "评分要求 ≥ " + pref.minRating() + " 星。"));
            }
            if (pref.sortBy() != null) {
                String label = sortLabel(pref.sortBy());
                if (label != null) evidence.add(new RecommendationEvidence("sort", "按「" + label + "」排序。"));
            }
        }

        // Data-driven evidence
        evidence.add(new RecommendationEvidence("stats",
                String.format("共 %d 件商品，覆盖 %d 个平台，均价 ¥%.0f。",
                        s.productCount, s.platformCount, s.avgPrice)));

        return evidence;
    }

    // ── Risks ─────────────────────────────────────────────────────

    private List<String> buildRisks(Stats s) {
        List<String> risks = new ArrayList<>();
        risks.add("当前为公开样例商品数据，不代表真实平台库存与价格。");

        if (s.singlePlatform) {
            risks.add("仅覆盖 1 个平台，建议跨平台比价后再购买。");
        }
        if (s.noOfficialStore && s.productCount > 2) {
            risks.add("未找到官方/自营店铺，第三方购买需注意售后保障。");
        }
        if (s.hasPriceVolatility) {
            risks.add("同款商品价格差异较大，注意辨别低价陷阱。");
        }

        return risks;
    }

    // ── Product analyses ──────────────────────────────────────────

    private List<ProductAnalysis> buildAnalyses(List<ProductOffer> products) {
        List<ProductAnalysis> analyses = new ArrayList<>();
        int limit = Math.min(products.size(), 3);

        for (int i = 0; i < limit; i++) {
            ProductOffer p = products.get(i);

            List<String> strengths = new ArrayList<>();
            List<String> weaknesses = new ArrayList<>();

            // Use matched preferences from the scorer pipeline
            List<String> matched = p.matchedPreferences();
            if (matched != null) {
                for (String m : matched) {
                    switch (m) {
                        case "price_advantage" -> strengths.add("价格低于同类均价");
                        case "top_rated" -> strengths.add("评分在同类中领先");
                        case "hot_sales" -> strengths.add("销量高，市场验证充分");
                        case "brand_match" -> strengths.add("品牌匹配你的偏好");
                        case "official_store" -> strengths.add("官方/自营店铺");
                        default -> {} // skip unknown pref ids
                    }
                }
                if (matched.contains("over_budget")) {
                    weaknesses.add("超出你的预算范围");
                }
            }

            // Quality signals from the product data
            if (p.rating() >= 4.8) {
                if (!strengths.contains("评分在同类中领先")) strengths.add("高评分 (" + p.rating() + "星)");
            }
            if (p.sales() >= 5000) {
                if (!strengths.contains("销量高，市场验证充分")) strengths.add("销量 " + formatSales(p.sales()));
            }

            // Channel signals
            boolean isOfficial = p.tags().stream().anyMatch(t ->
                    t.contains("官方") || t.contains("旗舰店") || t.contains("自营")
                            || t.contains("正品保障"));
            if (isOfficial) {
                if (!strengths.contains("官方/自营店铺")) strengths.add("官方/自营渠道");
            } else {
                weaknesses.add("第三方店铺，注意售后");
            }

            // Price signals
            if (p.price() < 200) strengths.add("价格实惠");
            if (p.originalPrice() > p.price() * 1.2) strengths.add("有折扣优惠");

            // Rating concern
            if (p.rating() < 4.3) weaknesses.add("评分偏低 (" + p.rating() + "星)");

            // Ensure at least one strength
            if (strengths.isEmpty()) strengths.add("综合匹配度较高");

            int productScore = (int) Math.round(Math.min(p.score() / 10.0 * 100, 100));
            analyses.add(new ProductAnalysis(p.productId(), p.platform(), p.title(),
                    i + 1, productScore, strengths, weaknesses));
        }

        return analyses;
    }

    // ── Helpers ───────────────────────────────────────────────────

    private int weightedScore(int match, int price, int rep, int channel, int risk) {
        double s = match * 0.25 + price * 0.25 + rep * 0.20 + channel * 0.15 + risk * 0.15;
        return Math.min((int) Math.round(s), 100);
    }

    private int clamp(int score) {
        return Math.max(0, Math.min(100, score));
    }

    private double percentile(double[] sorted, double p) {
        if (sorted.length == 0) return 0;
        if (sorted.length == 1) return sorted[0];
        double idx = p * (sorted.length - 1);
        int lo = (int) Math.floor(idx);
        int hi = (int) Math.ceil(idx);
        if (lo == hi) return sorted[Math.min(lo, sorted.length - 1)];
        double frac = idx - lo;
        return sorted[Math.min(lo, sorted.length - 1)]
                + frac * (sorted[Math.min(hi, sorted.length - 1)] - sorted[Math.min(lo, sorted.length - 1)]);
    }

    private double platformQualityScore(String platform) {
        return switch (platform) {
            case "京东-mock" -> 0.95;
            case "天猫-mock" -> 0.90;
            case "淘宝-mock" -> 0.75;
            case "拼多多-mock" -> 0.70;
            default -> 0.50;
        };
    }

    private String sortLabel(String sortBy) {
        return switch (sortBy == null ? "" : sortBy) {
            case "price_asc" -> "价格从低到高";
            case "price_desc" -> "价格从高到低";
            case "sales_desc" -> "销量优先";
            case "rating_desc" -> "评分优先";
            default -> null;
        };
    }

    private String formatSales(int sales) {
        if (sales >= 10000) return String.format("%.1f万+", sales / 10000.0);
        if (sales >= 1000) return String.format("%dk+", sales / 1000);
        return sales + "+";
    }
}
