package com.ec26b.shoppingagent.product;

import com.ec26b.shoppingagent.ai.ArkClient;
import com.fasterxml.jackson.databind.JsonNode;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Decomposes natural language shopping queries into structured search parameters.
 *
 * <p>Uses Ark LLM with rule-based fallback when Ark is unavailable.
 * Output: category, expanded keywords, price range, color, brand, platforms,
 * sort preference, and decision factors.
 */
public class ArkQueryDecomposer {

    private final ArkClient arkClient;
    private final QueryRewriter ruleRewriter;
    private final boolean enabled;

    public ArkQueryDecomposer(ArkClient arkClient) {
        this.arkClient = arkClient;
        this.ruleRewriter = new QueryRewriter();
        this.enabled = arkClient != null && arkClient.isEnabled();
    }

    public DecomposedQuery decompose(String text) {
        if (text == null || text.isBlank()) {
            return DecomposedQuery.EMPTY;
        }

        // Try Ark LLM first
        if (enabled) {
            try {
                return decomposeWithArk(text);
            } catch (Exception e) {
                // Fall through to rule-based
            }
        }

        // Rule-based fallback
        return decomposeWithRules(text);
    }

    private DecomposedQuery decomposeWithArk(String text) {
        String categories = String.join("/", CategoryResolver.defaultResolver().supportedCategoryNames());
        List<Map<String, Object>> messages = List.of(
                Map.of("role", "system", "content",
                        "你是购物查询理解器。将用户的自然语言拆解为结构化搜索参数。只输出 JSON。" +
                        "字段：category(从[" + categories + "]中选择)," +
                        "expandedKeywords(字符串数组,同义词和变体)," +
                        "priceMin(数字),priceMax(数字),color(字符串)," +
                        "brand(字符串),platforms(字符串数组,可选京东/拼多多/淘宝/天猫)," +
                        "sortBy(price_asc/price_desc/rating_desc/sales_desc/recommended)," +
                        "factors(字符串数组,可选low_price/official_store/fast_delivery/high_rating/brand_match)," +
                        "dislikes(字符串数组,可选non_official/high_price/no_brand)。不要输出Markdown。"),
                Map.of("role", "user", "content", "分析购物意图：" + text)
        );

        JsonNode json = arkClient.chatJson(messages);

        String cat = json.path("category").asText(null);
        String category = cat != null ? CategoryResolver.defaultResolver().resolveName(cat) : null;

        List<String> keywords = new ArrayList<>();
        if (json.path("expandedKeywords").isArray()) {
            json.path("expandedKeywords").forEach(k -> keywords.add(k.asText()));
        }
        // Also add rule-based expansions
        QueryRewriter.RewrittenQuery rq = ruleRewriter.rewrite(text);
        if (rq.hasExpansions()) keywords.addAll(rq.expandedTerms());

        Double priceMin = json.path("priceMin").isNumber() ? json.path("priceMin").asDouble() : null;
        Double priceMax = json.path("priceMax").isNumber() ? json.path("priceMax").asDouble() : null;
        String color = json.path("color").isNull() ? null : json.path("color").asText(null);
        String brand = json.path("brand").isNull() ? null : json.path("brand").asText(null);

        List<String> platforms = new ArrayList<>();
        if (json.path("platforms").isArray()) {
            json.path("platforms").forEach(p -> {
                String pv = p.asText("");
                if (Set.of("京东", "拼多多", "淘宝", "天猫").contains(pv)) platforms.add(pv + "-mock");
            });
        }

        String sortBy = rq.sortHint() != null ? rq.sortHint() : json.path("sortBy").asText("recommended");

        List<String> factors = new ArrayList<>();
        if (json.path("factors").isArray()) {
            json.path("factors").forEach(f -> factors.add(f.asText()));
        }
        if (rq.ratingHint() != null && !factors.contains(rq.ratingHint())) {
            factors.add(rq.ratingHint());
        }

        List<String> dislikes = new ArrayList<>();
        if (json.path("dislikes").isArray()) {
            json.path("dislikes").forEach(d -> dislikes.add(d.asText()));
        }

        return new DecomposedQuery(text, category, keywords, priceMin, priceMax,
                color, brand, platforms, sortBy, factors, dislikes);
    }

    private DecomposedQuery decomposeWithRules(String text) {
        QueryRewriter.RewrittenQuery rq = ruleRewriter.rewrite(text);
        String category = CategoryResolver.defaultResolver().resolveName(text);
        String sortBy = rq.sortHint() != null ? rq.sortHint() : "recommended";
        List<String> factors = rq.ratingHint() != null ? List.of(rq.ratingHint()) : List.of();

        return new DecomposedQuery(text, category, new ArrayList<>(rq.expandedTerms()),
                null, null, null, null, List.of(), sortBy, factors, List.of());
    }

    // ── Output ─────────────────────────────────────────────────

    public record DecomposedQuery(
            String originalText,
            String category,
            List<String> expandedKeywords,
            Double priceMin,
            Double priceMax,
            String color,
            String brand,
            List<String> platforms,
            String sortBy,
            List<String> decisionFactors,
            List<String> dislikes
    ) {
        static final DecomposedQuery EMPTY = new DecomposedQuery(
                "", null, List.of(), null, null, null, null,
                List.of(), "recommended", List.of(), List.of());

        public boolean hasCategory() { return category != null && !category.isBlank(); }
        public boolean hasExpansions() { return expandedKeywords != null && !expandedKeywords.isEmpty(); }
        public boolean hasPriceRange() { return priceMin != null || priceMax != null; }
    }
}
