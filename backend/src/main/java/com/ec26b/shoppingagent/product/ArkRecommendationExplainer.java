package com.ec26b.shoppingagent.product;

import com.ec26b.shoppingagent.ai.ArkClient;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Takes a rule-generated RecommendationExplanation and rewrites
 * human-facing text via Ark. Never modifies product ID, platform, price,
 * product name, sort order, or numeric scores.
 */
public class ArkRecommendationExplainer {

    private final ArkClient arkClient;
    private final ObjectMapper objectMapper;

    public ArkRecommendationExplainer(ArkClient arkClient, ObjectMapper objectMapper) {
        this.arkClient = arkClient;
        this.objectMapper = objectMapper;
    }

    /**
     * Attempts to rewrite explanation text with Ark.
     * On failure, returns the original explanation with fallback notices.
     */
    public RecommendationExplanation explain(RecommendationExplanation ruleResult,
                                              ShoppingIntent intent,
                                              ProductSearchResult searchResult) {
        try {
            String contextJson;
            try {
                contextJson = objectMapper.writeValueAsString(
                        buildContext(ruleResult, intent, searchResult));
            } catch (com.fasterxml.jackson.core.JsonProcessingException e) {
                return ruleResult.withFallbackNotices(
                        List.of("Ark 推荐解释生成失败（序列化异常），已回退规则解释。"));
            }
            List<Map<String, Object>> messages = List.of(
                    Map.of("role", "system", "content",
                            "你是电商推荐顾问。只输出 JSON，字段固定为 summaryReason(string), signals(array of {key,label,explanation}), evidence(array of {type,content}), risks(array of string), analyses(array of {productId,strengths(array),weaknesses(array)})。不要修改 productId、platform、price、productName、score、decisionScore。不要输出 Markdown。"),
                    Map.of("role", "user", "content",
                            "基于以下结构化推荐结果，生成自然语言解释：\n" + contextJson)
            );
            JsonNode json = arkClient.chatJson(messages);

            String summaryReason = json.path("summaryReason").asText(ruleResult.summaryReason());
            List<DecisionSignal> signals = rewriteSignals(json, ruleResult);
            List<RecommendationEvidence> evidence = rewriteEvidence(json, ruleResult);
            List<String> risks = rewriteRisks(json, ruleResult);
            List<ProductAnalysis> analyses = rewriteAnalyses(json, ruleResult);

            return new RecommendationExplanation(
                    ruleResult.decisionScore(), signals, evidence, risks, analyses,
                    summaryReason, "ark", false, List.of());
        } catch (RuntimeException ex) {
            return ruleResult.withFallbackNotices(
                    List.of("Ark 推荐解释生成失败，已回退规则解释。"));
        }
    }

    private Map<String, Object> buildContext(RecommendationExplanation exp,
                                              ShoppingIntent intent,
                                              ProductSearchResult sr) {
        Map<String, Object> ctx = new LinkedHashMap<>();
        ctx.put("decisionScore", exp.decisionScore());
        ctx.put("keyword", intent.keyword());
        ctx.put("maxPrice", intent.maxPrice());
        ctx.put("color", intent.color());
        ctx.put("preferences", intent.toPreferenceIds());

        List<Map<String, Object>> sigList = new ArrayList<>();
        for (var s : exp.decisionSignals()) {
            Map<String, Object> sm = new LinkedHashMap<>();
            sm.put("key", s.key()); sm.put("label", s.label()); sm.put("score", s.score());
            sigList.add(sm);
        }
        ctx.put("signals", sigList);

        List<Map<String, Object>> prodList = new ArrayList<>();
        for (var p : exp.productAnalyses()) {
            Map<String, Object> pm = new LinkedHashMap<>();
            pm.put("productId", p.productId()); pm.put("platform", p.platform());
            pm.put("title", p.title()); pm.put("rank", p.rank()); pm.put("score", p.score());
            prodList.add(pm);
        }
        ctx.put("products", prodList);
        return ctx;
    }

    private List<DecisionSignal> rewriteSignals(JsonNode json, RecommendationExplanation rule) {
        if (!json.has("signals") || !json.path("signals").isArray()) return rule.decisionSignals();
        List<DecisionSignal> out = new ArrayList<>();
        var origSignals = rule.decisionSignals();
        var arr = json.path("signals");
        for (int i = 0; i < arr.size() && i < origSignals.size(); i++) {
            JsonNode s = arr.get(i);
            String expl = s.path("explanation").asText(origSignals.get(i).explanation());
            out.add(new DecisionSignal(origSignals.get(i).key(), origSignals.get(i).label(),
                    origSignals.get(i).score(), expl));
        }
        return out;
    }

    private List<RecommendationEvidence> rewriteEvidence(JsonNode json, RecommendationExplanation rule) {
        if (!json.has("evidence") || !json.path("evidence").isArray()) return rule.evidence();
        List<RecommendationEvidence> out = new ArrayList<>();
        for (var e : json.path("evidence")) {
            out.add(new RecommendationEvidence(
                    e.path("type").asText("info"),
                    e.path("content").asText("")));
        }
        return out;
    }

    private List<String> rewriteRisks(JsonNode json, RecommendationExplanation rule) {
        if (!json.has("risks") || !json.path("risks").isArray()) return rule.risks();
        List<String> out = new ArrayList<>();
        for (var r : json.path("risks")) out.add(r.asText());
        return out;
    }

    private List<ProductAnalysis> rewriteAnalyses(JsonNode json, RecommendationExplanation rule) {
        if (!json.has("analyses") || !json.path("analyses").isArray()) return rule.productAnalyses();
        List<ProductAnalysis> out = new ArrayList<>();
        var orig = rule.productAnalyses();
        var arr = json.path("analyses");
        for (int i = 0; i < arr.size() && i < orig.size(); i++) {
            JsonNode a = arr.get(i);
            // Never use Ark's productId — always keep the original
            String pid = orig.get(i).productId();
            List<String> strengths = collectJsonArray(a, "strengths", orig.get(i).strengths());
            List<String> weaknesses = collectJsonArray(a, "weaknesses", orig.get(i).weaknesses());
            out.add(new ProductAnalysis(pid, orig.get(i).platform(), orig.get(i).title(),
                    orig.get(i).rank(), orig.get(i).score(), strengths, weaknesses));
        }
        return out;
    }

    private static List<String> collectJsonArray(JsonNode node, String field, List<String> fallback) {
        if (!node.has(field) || !node.path(field).isArray()) return fallback;
        List<String> result = new ArrayList<>();
        node.path(field).forEach(v -> result.add(v.asText()));
        return result.isEmpty() ? fallback : result;
    }
}
