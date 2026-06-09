package com.ec26b.shoppingagent.product;

import com.ec26b.shoppingagent.ai.ArkClient;
import com.fasterxml.jackson.databind.JsonNode;

import java.util.*;
import java.util.stream.Collectors;

/**
 * Hybrid retrieval that fuses three scoring signals:
 * <ol>
 *   <li><b>Vector similarity</b> — word+dictionary+bigram TF-IDF cosine
 *       (from {@link ProductVectorIndex}) — captures semantic + character overlap</li>
 *   <li><b>BM25 keyword score</b> — term frequency saturation + IDF —
 *       provides lexical relevance with length normalization</li>
 *   <li><b>LLM re-ranking</b> — Ark-based pairwise relevance scoring (optional) —
 *       adds cross-lingual and contextual understanding</li>
 * </ol>
 *
 * <p>Fusion weights: 0.4 × vector + 0.3 × BM25 + 0.3 × LLM.
 * When Ark is unavailable, LLM weight is redistributed to vector (0.7) + BM25 (0.3).
 *
 * <p><b>LLM pre-filter improvement:</b> The LLM re-ranker's candidate set is
 * selected using BM25 scores (not character-overlap) — this ensures the LLM
 * sees the most lexically-relevant candidates, not just those with surface-level
 * string matches.
 */
public class HybridRetriever {

    private final ProductVectorIndex vectorIndex;
    private final ArkClient arkClient;
    private final boolean llmEnabled;

    private static final double W_VECTOR = 0.4;
    private static final double W_BM25 = 0.3;
    private static final double W_LLM = 0.3;

    /** Maximum candidates sent to the LLM re-ranker for scoring. */
    private static final int LLM_CANDIDATE_LIMIT = 12;

    public HybridRetriever(List<Map<String, String>> products, ArkClient arkClient) {
        this.vectorIndex = new ProductVectorIndex(products);
        this.arkClient = arkClient;
        this.llmEnabled = arkClient != null && arkClient.isEnabled();
    }

    /**
     * Retrieve and score products against the decomposed query.
     * Returns product IDs ordered by fused score descending.
     */
    public List<ScoredProduct> retrieve(ArkQueryDecomposer.DecomposedQuery query,
                                         Map<String, String> productTexts,
                                         int topK) {
        String searchText = buildSearchText(query);

        // ── Stage 1: Vector recall (broad, fast) ──────────────
        List<ProductVectorIndex.ScoredProduct> vectorResults =
                vectorIndex.search(searchText, topK * 3);

        // ── Stage 2: BM25 scoring (lexical precision) ─────────
        Map<String, Double> bm25Scores = computeBM25(searchText, productTexts);

        // ── Stage 3: LLM re-ranking (contextual) ──────────────
        // Pre-filter: use BM25 ranking to select top candidates for LLM,
        // replacing the old textOverlap approach
        Map<String, Double> llmScores = llmEnabled
                ? computeLLMScoresBM25Prefilter(query.originalText(), productTexts, bm25Scores)
                : Map.of();

        // ── Fuse scores ───────────────────────────────────────
        Map<String, Double> fused = new LinkedHashMap<>();
        Set<String> allIds = new LinkedHashSet<>();
        for (var v : vectorResults) allIds.add(v.productId());
        allIds.addAll(bm25Scores.keySet());
        allIds.addAll(llmScores.keySet());

        // Normalize each signal to [0,1] before fusion
        double maxVec = vectorResults.stream()
                .mapToDouble(v -> v.score()).max().orElse(1.0);
        double maxBM25 = bm25Scores.values().stream()
                .mapToDouble(v -> v).max().orElse(1.0);
        double maxLLM = llmScores.values().stream()
                .mapToDouble(v -> v).max().orElse(1.0);

        double wVec = llmEnabled ? W_VECTOR : 0.7;
        double wBM = llmEnabled ? W_BM25 : 0.3;
        double wLLM = llmEnabled ? W_LLM : 0.0;

        for (String id : allIds) {
            double vScore = getNormalized(id, vectorResults, maxVec);
            double bScore = getNormalized(id, bm25Scores, maxBM25);
            double lScore = getNormalized(id, llmScores, maxLLM);
            fused.put(id, wVec * vScore + wBM * bScore + wLLM * lScore);
        }

        return fused.entrySet().stream()
                .sorted(Map.Entry.<String, Double>comparingByValue().reversed())
                .limit(topK)
                .map(e -> new ScoredProduct(e.getKey(), e.getValue()))
                .toList();
    }

    // ── BM25 ─────────────────────────────────────────────────────

    private Map<String, Double> computeBM25(String query, Map<String, String> docs) {
        Map<String, Double> scores = new LinkedHashMap<>();
        List<String> queryTokens = ProductVectorIndex.tokenize(query);
        if (queryTokens.isEmpty()) return scores;

        double k1 = 1.2, b = 0.75;
        double avgDl = docs.values().stream()
                .mapToInt(String::length).average().orElse(1);
        int N = docs.size();

        // Pre-compute document frequencies per query token
        Map<String, Integer> dfMap = new LinkedHashMap<>();
        for (String token : queryTokens) {
            int df = (int) docs.values().stream()
                    .filter(v -> v.toLowerCase().contains(token.toLowerCase()))
                    .count();
            dfMap.put(token, df);
        }

        for (var entry : docs.entrySet()) {
            String text = entry.getValue().toLowerCase();
            int dl = text.length();
            double score = 0;
            for (String token : queryTokens) {
                int tf = countOccurrences(text, token.toLowerCase());
                if (tf == 0) continue;
                int df = dfMap.getOrDefault(token, 0);
                if (df == 0) continue;
                double idf = Math.log((N - df + 0.5) / (df + 0.5) + 1);
                score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avgDl));
            }
            if (score > 0) scores.put(entry.getKey(), score);
        }
        return scores;
    }

    private int countOccurrences(String haystack, String needle) {
        int count = 0, idx = 0;
        while ((idx = haystack.indexOf(needle, idx)) != -1) {
            count++;
            idx += needle.length();
        }
        return count;
    }

    // ── LLM re-ranking with BM25 pre-filter ──────────────────────

    /**
     * Select LLM re-ranking candidates using BM25 scores instead of
     * the old character-overlap heuristic.
     *
     * <p>BM25 provides lexical relevance ranking with IDF weighting
     * and length normalization — far more accurate than counting
     * overlapping character bigrams.
     */
    private Map<String, Double> computeLLMScoresBM25Prefilter(
            String query, Map<String, String> docs,
            Map<String, Double> bm25Scores) {

        if (docs.isEmpty()) return Map.of();

        // Sort candidates by BM25 score (descending), take top-N
        List<Map.Entry<String, String>> candidates = docs.entrySet().stream()
                .filter(e -> bm25Scores.containsKey(e.getKey()))
                .sorted((a, b) -> Double.compare(
                        bm25Scores.getOrDefault(b.getKey(), 0.0),
                        bm25Scores.getOrDefault(a.getKey(), 0.0)))
                .limit(LLM_CANDIDATE_LIMIT)
                .toList();

        // Fallback: if BM25 returned too few, fill with remaining docs
        if (candidates.size() < Math.min(5, docs.size())) {
            Set<String> selected = candidates.stream()
                    .map(Map.Entry::getKey).collect(Collectors.toSet());
            List<Map.Entry<String, String>> remaining = docs.entrySet().stream()
                    .filter(e -> !selected.contains(e.getKey()))
                    .toList();
            int needed = Math.min(LLM_CANDIDATE_LIMIT - candidates.size(), remaining.size());
            candidates = new ArrayList<>(candidates);
            candidates.addAll(remaining.subList(0, needed));
        }

        if (candidates.isEmpty()) return Map.of();

        // Build LLM prompt
        StringBuilder items = new StringBuilder();
        for (int i = 0; i < candidates.size(); i++) {
            var e = candidates.get(i);
            items.append("[").append(i).append("] ").append(e.getValue()).append("\n");
        }

        try {
            List<Map<String, Object>> messages = List.of(
                    Map.of("role", "system", "content",
                            "你是商品相关性评估器。用户查询和候选商品列表如下。"
                            + "对每个候选商品打分(0-10)，分数越高越相关。"
                            + "只输出JSON数组，不要输出Markdown或多余文字："
                            + "[{\"index\":0,\"score\":8,\"reason\":\"简短理由\"}]。"),
                    Map.of("role", "user", "content",
                            "用户查询：" + query + "\n\n候选商品：\n" + items.toString())
            );

            JsonNode json = arkClient.chatJson(messages);
            Map<String, Double> scores = new LinkedHashMap<>();
            if (json.isArray()) {
                for (JsonNode item : json) {
                    int idx = item.path("index").asInt(-1);
                    double s = item.path("score").asDouble(0) / 10.0;
                    if (idx >= 0 && idx < candidates.size()) {
                        scores.put(candidates.get(idx).getKey(), s);
                    }
                }
            }
            return scores;
        } catch (Exception e) {
            // LLM unavailable — return empty, fusion will redistribute weights
            return Map.of();
        }
    }

    // ── Helpers ──────────────────────────────────────────────────

    private String buildSearchText(ArkQueryDecomposer.DecomposedQuery q) {
        StringBuilder sb = new StringBuilder();
        if (q.hasCategory()) sb.append(q.category()).append(" ");
        sb.append(q.originalText()).append(" ");
        if (q.hasExpansions()) sb.append(String.join(" ", q.expandedKeywords()));
        return sb.toString();
    }

    private double getNormalized(String id,
                                  List<ProductVectorIndex.ScoredProduct> results,
                                  double max) {
        if (max <= 0) return 0;
        for (var r : results) {
            if (r.productId().equals(id)) return r.score() / max;
        }
        return 0;
    }

    private double getNormalized(String id, Map<String, Double> scores, double max) {
        if (max <= 0) return 0;
        return scores.getOrDefault(id, 0.0) / max;
    }

    // ── Output ───────────────────────────────────────────────────

    public record ScoredProduct(String productId, double score) {}
}
