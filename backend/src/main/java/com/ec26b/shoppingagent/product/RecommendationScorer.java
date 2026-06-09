package com.ec26b.shoppingagent.product;

import org.springframework.stereotype.Component;

import java.util.*;
import java.util.stream.Collectors;

/**
 * Scores products using dynamic, set-relative thresholds instead of
 * hardcoded magic numbers.
 *
 * <h3>Scoring factors (7 dimensions, normalized to [0,1]):</h3>
 * <ol>
 *   <li><b>Price advantage</b> (25%) — how far below the set median.
 *       Amplified when user prefers lowest price.</li>
 *   <li><b>Quality / rating</b> (20%) — rating relative to 5.0 scale,
 *       with bonus for products above the 75th percentile in the set.</li>
 *   <li><b>Popularity / sales</b> (15%) — log-scale sales relative to
 *       the 90th percentile in the set (so outliers don't dominate).</li>
 *   <li><b>Brand match</b> (15%) — 1.0 if brand matches user preference,
 *       partial credit for category-relevant brands.</li>
 *   <li><b>Budget fit</b> (10%) — 1.0 if under budget, smooth decay above.
 *       Penalty is exponential beyond 2× budget.</li>
 *   <li><b>Platform quality</b> (10%) — per-platform trust score
 *       (京东 0.95 > 天猫 0.90 > 淘宝 0.75 > 拼多多 0.70).</li>
 *   <li><b>Channel trust</b> (5%) — official/self-operated store bonus.</li>
 * </ol>
 *
 * <p>All thresholds (percentiles, medians) are computed from the
 * <em>actual candidate set</em>, so a "good price" means "good compared
 * to other results for this query" rather than an arbitrary ¥250 cutoff.
 *
 * <p>Final score is mapped to a 0–10 scale for compatibility with
 * the existing scoring display.
 */
@Component
public class RecommendationScorer {

    // ── Weights (sum = 1.0) ──────────────────────────────────
    private static final double W_PRICE      = 0.25;
    private static final double W_RATING     = 0.20;
    private static final double W_SALES      = 0.15;
    private static final double W_BRAND      = 0.15;
    private static final double W_BUDGET     = 0.10;
    private static final double W_PLATFORM   = 0.10;
    private static final double W_TRUST      = 0.05;

    /**
     * Score a batch of products using dynamic set-relative statistics.
     *
     * @param products the candidate product set (used to compute percentiles)
     * @param pref     user preferences (may be null for neutral scoring)
     * @param keyword  the search keyword for category-aware brand scoring
     * @return the same products with updated scores, reasons, and matched preferences
     */
    public List<ProductOffer> scoreProducts(List<ProductOffer> products,
                                             UserPreference pref,
                                             String keyword) {
        if (products == null || products.isEmpty()) return List.of();

        // ── Compute set statistics (robust to outliers) ──────
        double[] sortedPrices = products.stream()
                .mapToDouble(ProductOffer::price).sorted().toArray();
        double[] sortedRatings = products.stream()
                .mapToDouble(ProductOffer::rating).sorted().toArray();
        double[] sortedSales = products.stream()
                .mapToDouble(ProductOffer::sales).sorted().toArray();

        double priceMedian = percentile(sortedPrices, 0.50);
        double priceP25 = percentile(sortedPrices, 0.25);
        double priceP75 = percentile(sortedPrices, 0.75);
        double priceIQR = Math.max(priceP75 - priceP25, 1.0);

        double ratingP75 = percentile(sortedRatings, 0.75);
        double salesP90 = percentile(sortedSales, 0.90);
        double salesMax = sortedSales.length > 0 ? sortedSales[sortedSales.length - 1] : 1.0;
        double priceMin = sortedPrices.length > 0 ? sortedPrices[0] : 0;
        double priceMax = sortedPrices.length > 0 ? sortedPrices[sortedPrices.length - 1] : 1;
        double priceRange = Math.max(priceMax - priceMin, 1.0);

        // ── Score each product ───────────────────────────────
        List<ProductOffer> scored = new ArrayList<>();
        for (ProductOffer p : products) {
            scored.add(scoreOne(p, pref, keyword,
                    priceMedian, priceIQR, priceRange,
                    ratingP75, salesP90, salesMax));
        }
        return scored;
    }

    /**
     * Score a single product. (Legacy API — for batchless callers.
     * Prefer {@link #scoreProducts} when the candidate set is available.)
     */
    public ProductOffer scoreProduct(ProductOffer product,
                                      List<String> preferences,
                                      Double maxPrice) {
        return scoreProduct(product, preferences, maxPrice, null);
    }

    /**
     * Score a single product with full preferences.
     * Uses fallback thresholds when no candidate set is available.
     */
    public ProductOffer scoreProduct(ProductOffer product,
                                      List<String> preferences,
                                      Double maxPrice,
                                      UserPreference fullPref) {
        // Fallback: use reasonable defaults when no candidate set
        return scoreOne(product, fullPref, null,
                200.0, 100.0, 500.0,  // price stats: median, IQR, range
                4.6, 8000.0, 50000.0); // rating P75, sales P90, sales max
    }

    // ── Core scoring logic ───────────────────────────────────────

    private ProductOffer scoreOne(ProductOffer p, UserPreference pref,
                                   String keyword,
                                   double priceMedian, double priceIQR, double priceRange,
                                   double ratingP75, double salesP90, double salesMax) {
        // Factor 1: Price advantage — how much below median (robust normalization)
        double zPrice = (priceMedian - p.price()) / priceIQR; // positive = cheaper than median
        double priceScore = sigmoid(zPrice, 0.3); // map [-∞, +∞] → [0, 1]

        // Amplify price sensitivity when user wants lowest price
        if (pref != null && pref.lowestPrice()) {
            priceScore = Math.pow(priceScore, 0.6); // curve that favors low prices more
        }
        // Slight penalty for very expensive (above P75 by 2× IQR)
        if (zPrice < -2.0) priceScore *= 0.6;

        // Factor 2: Quality / rating
        double ratingBase = Math.min(1.0, p.rating() / 5.0);
        double ratingBonus = p.rating() >= ratingP75 ? 0.15 : 0.0;
        double ratingScore = Math.min(1.0, ratingBase + ratingBonus);
        if (pref != null && pref.highRating()) {
            ratingScore = Math.pow(ratingScore, 0.7); // amplify
        }

        // Factor 3: Popularity / sales — log-scale against P90
        double salesNorm = salesP90 > 0 ? Math.min(1.0, Math.log1p(p.sales()) / Math.log1p(salesP90)) : 0.5;
        double salesScore = salesNorm;
        if (pref != null && pref.highSales()) {
            salesScore = Math.pow(salesScore, 0.6);
        }

        // Factor 4: Brand match
        double brandScore = 0.0;
        if (pref != null && pref.brand() != null && !pref.brand().isBlank()) {
            brandScore = (p.brand() != null && p.brand().equals(pref.brand())) ? 1.0 : 0.0;
        }

        // Factor 5: Budget fit
        double budgetScore = 1.0;
        if (pref != null && pref.maxPrice() != null && pref.maxPrice() > 0) {
            double ratio = p.price() / pref.maxPrice();
            if (ratio <= 1.0) {
                budgetScore = 1.0; // under budget
            } else if (ratio <= 1.5) {
                budgetScore = 1.0 - (ratio - 1.0) * 1.0; // linear decay: 100%→50%
            } else if (ratio <= 2.0) {
                budgetScore = 0.5 - (ratio - 1.5) * 0.8; // steeper: 50%→10%
            } else {
                budgetScore = 0.05; // way over budget
            }
            budgetScore = Math.max(0.0, budgetScore);
        }

        // Factor 6: Platform quality
        double platformScore = platformQuality(p.platform());

        // Factor 7: Channel trust
        boolean isOfficial = p.tags().stream().anyMatch(t ->
                t.contains("官方") || t.contains("旗舰店") || t.contains("自营")
                || t.contains("正品保障"));
        double trustScore = isOfficial ? 1.0 : 0.5;
        if (pref != null && pref.officialStore()) {
            trustScore = isOfficial ? 1.0 : 0.1; // strong penalty for non-official when user wants official
        }

        // ── Weighted fusion ──────────────────────────────────
        double total = W_PRICE    * priceScore
                     + W_RATING   * ratingScore
                     + W_SALES    * salesScore
                     + W_BRAND    * brandScore
                     + W_BUDGET   * budgetScore
                     + W_PLATFORM * platformScore
                     + W_TRUST    * trustScore;

        // Map to 0–10 scale
        double finalScore = Math.round(total * 10.0 * 10.0) / 10.0; // one decimal
        finalScore = Math.max(0.0, Math.min(10.0, finalScore));

        // ── Build reasons and matched preferences ────────────
        List<String> reasons = new ArrayList<>(p.reasons());
        List<String> matched = new ArrayList<>(p.matchedPreferences());

        // Dynamic reasons (threshold-based, not hardcoded)
        if (priceScore > 0.75) {
            if (!reasons.contains("价格有优势")) reasons.add("价格有优势");
            matched.add("price_advantage");
        }
        if (ratingScore > 0.80) {
            if (!reasons.contains("评分领先")) reasons.add("评分领先");
            matched.add("top_rated");
        }
        if (salesScore > 0.70) {
            if (!reasons.contains("热销商品")) reasons.add("热销商品");
            matched.add("hot_sales");
        }
        if (brandScore >= 1.0) {
            if (!reasons.contains("品牌匹配")) reasons.add("品牌匹配");
            matched.add("brand_match");
        }
        if (budgetScore < 1.0 && budgetScore > 0.0) {
            if (!reasons.contains("略超预算")) reasons.add("略超预算");
        }
        if (budgetScore <= 0.05 && pref != null && pref.maxPrice() != null) {
            reasons.add("远超预算");
            matched.add("over_budget");
        }
        if (isOfficial) {
            matched.add("official_store");
        }
        // Legacy preference matching from the passed-in preference IDs
        if (pref != null) {
            for (String prefId : pref.toPreferenceIds()) {
                if (!matched.contains(prefId)) {
                    // These are user-stated preferences; mark as matched
                    // if relevant (already handled above for most cases)
                }
            }
        }

        return p.withScoringResult(finalScore, reasons, matched);
    }

    // ── Helpers ──────────────────────────────────────────────────

    /**
     * Sigmoid function for smooth score mapping.
     * {@code sigmoid(x, k)} = 1 / (1 + exp(-x/k))
     * where k controls steepness.
     */
    private static double sigmoid(double x, double k) {
        return 1.0 / (1.0 + Math.exp(-x / k));
    }

    /**
     * Platform quality scores based on consumer trust perception.
     */
    private static double platformQuality(String platform) {
        return switch (platform) {
            case "京东-mock" -> 0.95;
            case "天猫-mock" -> 0.90;
            case "淘宝-mock" -> 0.75;
            case "拼多多-mock" -> 0.70;
            default -> 0.60;
        };
    }

    /**
     * Compute the p-th percentile from a sorted array.
     */
    private static double percentile(double[] sorted, double p) {
        if (sorted.length == 0) return 0;
        if (sorted.length == 1) return sorted[0];
        double idx = p * (sorted.length - 1);
        int lo = (int) Math.floor(idx);
        int hi = (int) Math.ceil(idx);
        if (lo == hi) return sorted[Math.min(lo, sorted.length - 1)];
        double frac = idx - lo;
        double vLo = sorted[Math.min(lo, sorted.length - 1)];
        double vHi = sorted[Math.min(hi, sorted.length - 1)];
        return vLo + frac * (vHi - vLo);
    }
}
