package com.ec26b.shoppingagent.product;

import java.util.*;

/**
 * Multi-factor result re-ranker for shopping search.
 *
 * <p>Re-ranks product offers in three passes:
 * <ol>
 *   <li><b>Base quality scoring</b> — delegated to {@link RecommendationScorer}
 *       for dynamic, set-relative percentile-based pricing, rating, sales,
 *       brand, budget, platform, and trust evaluation</li>
 *   <li><b>Context scoring</b> — text relevance to the query + user profile
 *       matching (brand/platform/price-range preferences)</li>
 *   <li><b>MMR diversity</b> — Maximal Marginal Relevance that balances
 *       relevance against brand+platform redundancy, ensuring top results
 *       aren't dominated by a single brand or platform</li>
 * </ol>
 *
 * <p>Scores are additive; the final order is determined by MMR selection.
 * Search intent matching remains primary.
 */
public class ResultReRanker {

    private static final double TEXT_MATCH_WEIGHT = 3.0;
    private static final double BRAND_MATCH_WEIGHT = 1.5;
    private static final double PLATFORM_MATCH_WEIGHT = 0.5;
    private static final double PRICE_RANGE_MATCH_WEIGHT = 1.0;

    /** MMR tradeoff: 0.0 = pure diversity, 1.0 = pure relevance */
    private static final double MMR_LAMBDA = 0.75;

    private final RecommendationScorer scorer;

    /**
     * Create a re-ranker with a {@link RecommendationScorer} for base quality scoring.
     */
    public ResultReRanker(RecommendationScorer scorer) {
        this.scorer = scorer;
    }

    /**
     * Re-rank offers using query terms, user profile, and dynamic quality scoring.
     */
    public List<ProductOffer> rerank(List<ProductOffer> offers, String query,
                                      Map<String, Object> profile) {
        return rerank(offers, query, profile, null);
    }

    /**
     * Re-rank with full user preference context for the scorer.
     *
     * @param offers  the candidate product offers
     * @param query   the search query text
     * @param profile user behavior profile (may be null)
     * @param pref    user shopping preferences from intent parsing (may be null)
     */
    public List<ProductOffer> rerank(List<ProductOffer> offers, String query,
                                      Map<String, Object> profile,
                                      UserPreference pref) {
        if (offers == null || offers.isEmpty()) return List.of();
        if (query == null) query = "";

        final String q = query.toLowerCase();
        Set<String> queryTerms = extractTerms(q);

        // ── Pass 1: Base quality scoring via RecommendationScorer ──
        List<ProductOffer> baseScored = scorer.scoreProducts(offers, pref, q);
        Map<String, Double> baseScoreByProductId = new LinkedHashMap<>();
        for (ProductOffer o : baseScored) {
            baseScoreByProductId.put(o.productId(), o.score());
        }

        // ── Pass 2: Context scoring (text + profile) ──────────────
        List<ScoredOffer> scored = new ArrayList<>();
        for (ProductOffer o : offers) {
            double baseFromScorer = baseScoreByProductId.getOrDefault(o.productId(), o.score());
            double score = baseFromScorer;

            // Text relevance to query
            score += textRelevance(o, queryTerms) * TEXT_MATCH_WEIGHT;

            // Profile matching (if available)
            if (profile != null && !profile.isEmpty()) {
                score += profileMatch(o, profile);
            }

            scored.add(new ScoredOffer(o, score));
        }

        // ── Pass 3: MMR greedy selection ──────────────────────────
        return mmrSelect(scored, MMR_LAMBDA);
    }

    // ── MMR (Maximal Marginal Relevance) ──────────────────────────

    /**
     * Greedy MMR selection: at each step, pick the item that maximizes
     * {@code λ × relevance - (1-λ) × max_similarity(selected)}.
     *
     * <p>Similarity between two products considers:
     * <ul>
     *   <li>Brand overlap (0.6 weight) — same brand → 1.0, else 0.0</li>
     *   <li>Platform overlap (0.25 weight) — same platform → 1.0, else 0.0</li>
     *   <li>Category/price proximity (0.15 weight) — same sameItemKey → 1.0,
     *       else Gaussian on price ratio</li>
     * </ul>
     *
     * <p>This naturally prevents brand-stacking (the old DIVERSITY_PENALTY
     * approach) and also ensures platform diversity in top results.
     */
    private List<ProductOffer> mmrSelect(List<ScoredOffer> candidates, double lambda) {
        if (candidates.isEmpty()) return List.of();

        // Normalize relevance scores to [0,1] for stable MMR math
        double maxScore = candidates.stream()
                .mapToDouble(so -> so.score).max().orElse(1.0);
        double minScore = candidates.stream()
                .mapToDouble(so -> so.score).min().orElse(0.0);
        double scoreRange = Math.max(maxScore - minScore, 0.001);

        List<ScoredOffer> pool = new ArrayList<>(candidates);
        List<ProductOffer> selected = new ArrayList<>();
        List<ScoredOffer> selectedScored = new ArrayList<>();

        // First pick: highest relevance
        ScoredOffer first = pool.remove(0);
        selected.add(first.offer);
        selectedScored.add(first);

        while (!pool.isEmpty()) {
            double bestMMR = Double.NEGATIVE_INFINITY;
            int bestIdx = -1;

            for (int i = 0; i < pool.size(); i++) {
                ScoredOffer candidate = pool.get(i);

                // Normalized relevance
                double rel = (candidate.score - minScore) / scoreRange;

                // Max similarity to any already-selected item
                double maxSim = 0.0;
                for (ScoredOffer sel : selectedScored) {
                    double sim = similarity(candidate.offer, sel.offer);
                    maxSim = Math.max(maxSim, sim);
                }

                double mmr = lambda * rel - (1 - lambda) * maxSim;

                if (mmr > bestMMR) {
                    bestMMR = mmr;
                    bestIdx = i;
                }
            }

            if (bestIdx >= 0) {
                ScoredOffer chosen = pool.remove(bestIdx);
                selected.add(chosen.offer);
                selectedScored.add(chosen);
            } else {
                break; // shouldn't happen
            }
        }

        return selected;
    }

    /**
     * Compute pairwise similarity between two product offers.
     * Returns a value in [0, 1] where 1 = identical for diversity purposes.
     */
    private double similarity(ProductOffer a, ProductOffer b) {
        double sim = 0.0;

        // Brand similarity (dominant factor — same brand = less diversity)
        if (a.brand() != null && b.brand() != null) {
            if (a.brand().equalsIgnoreCase(b.brand())) {
                sim += 0.6;
            }
        }

        // Platform similarity
        if (a.platform() != null && a.platform().equals(b.platform())) {
            sim += 0.25;
        }

        // Same-item similarity (same product on different platforms = still same item)
        if (a.sameItemKey() != null && a.sameItemKey().equals(b.sameItemKey())) {
            sim += 0.15;
        } else {
            // Price proximity for different items: Gaussian on log-price ratio
            double priceRatio = Math.min(a.price(), b.price())
                    / Math.max(Math.max(a.price(), b.price()), 1.0);
            // priceRatio close to 1 → similar price → slight similarity
            sim += 0.05 * priceRatio;
        }

        return Math.min(1.0, sim);
    }

    // ── Text relevance ───────────────────────────────────────────

    private double textRelevance(ProductOffer offer, Set<String> queryTerms) {
        if (queryTerms.isEmpty()) return 0;
        String haystack = (offer.title() + " " + offer.brand() + " "
                + String.join(" ", offer.tags())).toLowerCase();
        int hits = 0;
        for (String term : queryTerms) {
            if (haystack.contains(term)) hits++;
        }
        return queryTerms.isEmpty() ? 0 : (double) hits / queryTerms.size();
    }

    private Set<String> extractTerms(String query) {
        Set<String> terms = new LinkedHashSet<>();
        for (String token : ProductVectorIndex.tokenize(query)) {
            if (token.length() >= 2 || token.matches("[一-龥]")) {
                terms.add(token);
            }
        }
        for (String word : query.split("[\\s,，]+")) {
            if (word.length() >= 2) terms.add(word.toLowerCase());
        }
        return terms;
    }

    // ── Profile match ────────────────────────────────────────────

    @SuppressWarnings("unchecked")
    private double profileMatch(ProductOffer offer, Map<String, Object> profile) {
        double score = 0;

        List<String> preferredPlatforms = (List<String>) profile.get("preferredPlatforms");
        if (preferredPlatforms != null && platformLabel(offer.platform()) != null
                && preferredPlatforms.contains(platformLabel(offer.platform()))) {
            score += PLATFORM_MATCH_WEIGHT;
        }

        List<String> inferredBrands = (List<String>) profile.get("inferredBrands");
        if (inferredBrands != null && offer.brand() != null
                && inferredBrands.contains(offer.brand())) {
            score += BRAND_MATCH_WEIGHT;
        }

        Object priceMin = profile.get("inferredPriceMin");
        Object priceMax = profile.get("inferredPriceMax");
        if (priceMin instanceof Number && priceMax instanceof Number) {
            double min = ((Number) priceMin).doubleValue();
            double max = ((Number) priceMax).doubleValue();
            if (offer.price() >= min && offer.price() <= max) {
                score += PRICE_RANGE_MATCH_WEIGHT;
            }
        }

        List<String> dislikes = (List<String>) profile.get("dislikes");
        if (dislikes != null) {
            if (dislikes.contains("non_official") && offer.tags().stream()
                    .noneMatch(t -> t.contains("自营") || t.contains("官方") || t.contains("旗舰"))) {
                score -= 1.0;
            }
        }

        return score;
    }

    private static String platformLabel(String platform) {
        return switch (platform) {
            case "京东-mock" -> "京东";
            case "拼多多-mock" -> "拼多多";
            case "淘宝-mock" -> "淘宝";
            case "天猫-mock" -> "天猫";
            default -> null;
        };
    }

    // ── DTO ──────────────────────────────────────────────────────

    private record ScoredOffer(ProductOffer offer, double score) {}
}
