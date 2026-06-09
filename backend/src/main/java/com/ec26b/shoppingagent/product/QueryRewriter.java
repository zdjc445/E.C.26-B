package com.ec26b.shoppingagent.product;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Lightweight query rewriter for shopping search.
 *
 * <p>Expands user queries with:
 * <ul>
 *   <li>Category synonyms (e.g. "跑鞋" → "运动鞋")</li>
 *   <li>Attribute keyword variations (e.g. "便宜" → price_asc)</li>
 *   <li>Implicit platform detection</li>
 * </ul>
 *
 * This is a rule-based RAG query expansion stage — no embedding/vector search.
 */
public class QueryRewriter {

    private static final Map<String, List<String>> SYNONYMS = Map.ofEntries(
            Map.entry("跑鞋", List.of("运动鞋", "跑步鞋")),
            Map.entry("跑步鞋", List.of("运动鞋", "跑鞋")),
            Map.entry("篮球鞋", List.of("运动鞋")),
            Map.entry("板鞋", List.of("运动鞋", "休闲鞋")),
            Map.entry("蓝牙耳机", List.of("耳机", "无线耳机")),
            Map.entry("降噪耳机", List.of("耳机")),
            Map.entry("入耳式", List.of("耳机", "耳塞")),
            Map.entry("头戴式", List.of("耳机")),
            Map.entry("吹风", List.of("吹风机", "电吹风")),
            Map.entry("双肩包", List.of("背包", "书包")),
            Map.entry("电脑包", List.of("背包")),
            Map.entry("便宜", List.of("低价", "价格低")),
            Map.entry("实惠", List.of("低价", "性价比高")),
            Map.entry("性价比", List.of("实惠", "低价")),
            Map.entry("质量好", List.of("高评分", "好评")),
            Map.entry("耐用", List.of("质量好", "好评"))
    );

    private static final Set<String> PRICE_ASC_HINTS = Set.of(
            "便宜", "低价", "从低到高", "价格低", "实惠", "省钱", "划算", "低价优先");
    private static final Set<String> PRICE_DESC_HINTS = Set.of(
            "贵的", "高端", "旗舰", "从高到低", "价格高");
    private static final Set<String> RATING_HINTS = Set.of(
            "好评", "评分高", "评价好", "口碑好", "质量好");
    private static final Set<String> SALES_HINTS = Set.of(
            "销量高", "爆款", "热门", "大家都在买", "畅销");

    /**
     * Rewrite a user query into expanded search terms.
     */
    public RewrittenQuery rewrite(String text) {
        if (text == null || text.isBlank()) {
            return new RewrittenQuery(text, List.of(), null, null);
        }

        List<String> expandedTerms = new ArrayList<>();
        String sortHint = null;
        String ratingHint = null;

        // Extract keywords from text and add synonyms
        for (var entry : SYNONYMS.entrySet()) {
            if (text.contains(entry.getKey())) {
                for (String syn : entry.getValue()) {
                    if (!expandedTerms.contains(syn)) {
                        expandedTerms.add(syn);
                    }
                }
            }
        }

        // Detect sort hints
        for (String hint : PRICE_ASC_HINTS) {
            if (text.contains(hint)) { sortHint = "price_asc"; break; }
        }
        if (sortHint == null) {
            for (String hint : PRICE_DESC_HINTS) {
                if (text.contains(hint)) { sortHint = "price_desc"; break; }
            }
        }

        // Detect quality hints
        for (String hint : RATING_HINTS) {
            if (text.contains(hint)) { ratingHint = "high_rating"; break; }
        }
        if (ratingHint == null) {
            for (String hint : SALES_HINTS) {
                if (text.contains(hint)) { ratingHint = "high_sales"; break; }
            }
        }

        return new RewrittenQuery(text, expandedTerms, sortHint, ratingHint);
    }

    public record RewrittenQuery(
            String original,
            List<String> expandedTerms,
            String sortHint,
            String ratingHint
    ) {
        public boolean hasExpansions() {
            return expandedTerms != null && !expandedTerms.isEmpty();
        }
    }
}
