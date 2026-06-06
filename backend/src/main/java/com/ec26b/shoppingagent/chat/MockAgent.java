package com.ec26b.shoppingagent.chat;

import com.ec26b.shoppingagent.ai.RecognitionResult;
import com.ec26b.shoppingagent.product.*;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.regex.Pattern;

@Component
public class MockAgent {

    private final MockProductSourceProvider productSource;
    private final UserPreferenceParser preferenceParser;
    private final RecommendationExplainer explainer;

    private static final Pattern SHOPPING_WORDS = Pattern.compile(
            "买|想买|想要|推荐|帮我找|找.*商品|多少钱|价格|便宜|优惠|性价比|官方|自营|旗舰|配送|物流|评价|评分|销量|预算|以内|不超过|以下");

    public MockAgent(MockProductSourceProvider productSource,
                     UserPreferenceParser preferenceParser,
                     RecommendationExplainer explainer) {
        this.productSource = productSource;
        this.preferenceParser = preferenceParser;
        this.explainer = explainer;
    }

    public AgentReply process(ChatStore.ChatSession session, String text,
                              List<String> imageIds, List<String> selectedOptionIds) {
        boolean hasOptions = selectedOptionIds != null && !selectedOptionIds.isEmpty();
        boolean hasImages = imageIds != null && !imageIds.isEmpty();

        if (hasOptions) {
            String lastUserText = findLastUserText(session);
            String recCategory = findRecognitionCategory(session);
            return buildProductRecommendation(selectedOptionIds,
                    coalesce(text, lastUserText), recCategory);
        }
        if (hasImages) return buildRecognitionReply(imageIds);
        if (isShoppingIntent(text)) return buildProductRecommendation(List.of(), text);
        return buildClarification();
    }

    public AgentReply processWithRecognition(ChatStore.ChatSession session, String text,
                                             List<String> imageIds, List<String> selectedOptionIds,
                                             RecognitionResult recResult) {
        if (selectedOptionIds != null && !selectedOptionIds.isEmpty()) {
            String lastUserText = findLastUserText(session);
            return buildProductRecommendation(selectedOptionIds,
                    coalesce(text, lastUserText), recResult.getCategory());
        }
        return buildRecognitionReplyWithResult(recResult);
    }

    // ── Helpers ──────────────────────────────────────────────

    private String coalesce(String a, String b) {
        if (a != null && !a.isBlank()) return a;
        return b != null ? b : "";
    }

    private String findLastUserText(ChatStore.ChatSession session) {
        var msgs = session.messages();
        for (int i = msgs.size() - 1; i >= 0; i--) {
            var m = msgs.get(i);
            if ("user".equals(m.role()) && m.text() != null && !m.text().isBlank()) return m.text();
        }
        return "";
    }

    private String findRecognitionCategory(ChatStore.ChatSession session) {
        var msgs = session.messages();
        for (int i = msgs.size() - 1; i >= 0; i--) {
            var m = msgs.get(i);
            if ("assistant".equals(m.role()) && m.agentReply() != null) {
                for (Card card : m.agentReply().cards()) {
                    if ("recognition".equals(card.cardType()) && card.category() != null)
                        return card.category();
                }
            }
        }
        return null;
    }

    private boolean isShoppingIntent(String text) {
        return text != null && !text.isBlank() && SHOPPING_WORDS.matcher(text).find();
    }

    String extractKeyword(String text) {
        if (text == null) return "运动鞋";
        if (text.contains("运动鞋")) return "运动鞋";
        if (text.contains("耳机")) return "耳机";
        if (text.contains("吹风机")) return "吹风机";
        return "运动鞋";
    }

    // ── Product recommendation ───────────────────────────────

    private AgentReply buildProductRecommendation(List<String> prefs, String text) {
        return buildProductRecommendation(prefs, text, null);
    }

    private AgentReply buildProductRecommendation(List<String> prefs, String text, String category) {
        // Parse preferences from text
        UserPreference pref = preferenceParser.parse(text);
        // Merge explicit option prefs
        if (prefs != null && !prefs.isEmpty()) {
            boolean hasLowest = prefs.contains("lowest_price");
            boolean hasOfficial = prefs.contains("official_store");
            boolean hasFast = prefs.contains("fast_delivery");
            pref = new UserPreference(pref.maxPrice(), pref.color(),
                    pref.officialStore() || hasOfficial,
                    pref.fastDelivery() || hasFast,
                    pref.lowestPrice() || hasLowest,
                    pref.highRating(), pref.highSales());
        }
        List<String> effectivePrefs = pref.toPreferenceIds();

        String keyword = category != null && !category.isBlank() ? category : extractKeyword(text);
        ProductSearchResult sr = productSource.search(
                new ProductSearchQuery(keyword, effectivePrefs, pref.maxPrice()));
        List<Card> cards = new ArrayList<>();

        cards.add(Card.productList("多平台商品结果", sr.products()));
        cards.add(Card.comparison("平台比价", sr.platformStats()));

        if (sr.products().isEmpty()) {
            String note = pref.maxPrice() != null
                    ? "当前预算下（≤" + pref.maxPrice().intValue() + "元）暂无合适的 Mock 商品，请调整预算或偏好。"
                    : "暂无合适的 Mock 商品。";
            return new AgentReply(UUID.randomUUID().toString(), "product_recommendation", note, cards);
        }

        // Build explanation
        RecommendationExplanation exp = explainer.explain(sr, pref, keyword);

        if (sr.topPick() != null) {
            ProductOffer t = sr.topPick();
            cards.add(Card.recommendation("推荐购买", t.title(), t.platform(), t.price(),
                    String.join("；", t.reasons().isEmpty() ? List.of("综合评分较高") : t.reasons()),
                    exp.decisionScore(), exp.decisionSignals(), exp.evidence(),
                    exp.risks(), exp.productAnalyses()));
        }

        return new AgentReply(UUID.randomUUID().toString(),
                "product_recommendation", "我按你的偏好整理了几个平台的选择。", cards);
    }

    // ── Recognition ──────────────────────────────────────────

    private AgentReply buildRecognitionReply(List<String> imageIds) {
        Card rec = Card.recognition(imageIds.get(0), "运动鞋", "Mock 品牌", "Mock 型号",
                List.of("运动鞋", "白色", "跑步鞋"), Map.of("color", "白色", "style", "通勤运动鞋"),
                0.82, "mock", false, "当前为演示识别结果。", null);
        return new AgentReply(UUID.randomUUID().toString(), "recognition",
                "我已经识别了你的商品图片。你更看重哪一点？", List.of(rec, Card.clarification("你更看重哪一点？")));
    }

    private AgentReply buildRecognitionReplyWithResult(RecognitionResult rec) {
        Card recCard = Card.recognition(rec.getImageId(), rec.getCategory(),
                rec.getBrand(), rec.getModel(), rec.getKeywords(), rec.getAttributes(),
                rec.getConfidence(), rec.getAiProvider(), rec.isFallbackUsed(),
                rec.getExplanation(), rec.getRecognitionId());
        return new AgentReply(UUID.randomUUID().toString(), "recognition",
                "我已经识别了你的商品图片。你更看重哪一点？", List.of(recCard, Card.clarification("你更看重哪一点？")));
    }

    private AgentReply buildClarification() {
        return new AgentReply(UUID.randomUUID().toString(), "clarification",
                "我已经收到你的需求。你更看重哪一点？",
                List.of(Card.clarification("你更看重哪一点？")));
    }

    // ── DTOs ─────────────────────────────────────────────────

    public record AgentReply(String replyId, String replyType, String text, List<Card> cards) {}

    public record Card(
            String cardType, String title,
            String productName, String platform, Double price, String reason,
            List<Option> options,
            String imageId, String category, String brand, String model,
            List<String> keywords, Map<String, Object> attributes,
            double confidence, String aiProvider, boolean fallbackUsed,
            String explanation, String recognitionId,
            List<ProductOffer> products,
            Map<String, ProductSearchResult.PlatformStats> platformStats,
            // explanation fields
            Integer decisionScore,
            List<DecisionSignal> decisionSignals,
            List<RecommendationEvidence> evidence,
            List<String> risks,
            List<ProductAnalysis> productAnalyses) {

        public static Card clarification(String title) {
            return new Card("clarification", title, null, null, null, null,
                    List.of(new Option("lowest_price", "价格最低"),
                            new Option("official_store", "官方店铺"),
                            new Option("fast_delivery", "配送更快")),
                    null, null, null, null, null, null,
                    0.0, null, false, null, null, null, null,
                    null, null, null, null, null);
        }

        public static Card recommendation(String title, String productName,
                                          String platform, Double price, String reason,
                                          Integer decisionScore,
                                          List<DecisionSignal> signals,
                                          List<RecommendationEvidence> evidence,
                                          List<String> risks,
                                          List<ProductAnalysis> analyses) {
            return new Card("recommendation", title, productName, platform, price, reason,
                    null, null, null, null, null, null, null,
                    0.0, null, false, null, null, null, null,
                    decisionScore, signals, evidence, risks, analyses);
        }

        public static Card recognition(String imageId, String category, String brand,
                                       String model, List<String> keywords,
                                       Map<String, Object> attributes, double conf,
                                       String aiProvider, boolean fallback,
                                       String explanation, String recognitionId) {
            return new Card("recognition", "识别结果", null, null, null, null, null,
                    imageId, category, brand, model, keywords, attributes,
                    conf, aiProvider, fallback, explanation, recognitionId,
                    null, null, null, null, null, null, null);
        }

        public static Card productList(String title, List<ProductOffer> products) {
            return new Card("product_list", title, null, null, null, null, null,
                    null, null, null, null, null, null,
                    0.0, null, false, null, null, products, null,
                    null, null, null, null, null);
        }

        public static Card comparison(String title,
                                      Map<String, ProductSearchResult.PlatformStats> stats) {
            return new Card("comparison", title, null, null, null, null, null,
                    null, null, null, null, null, null,
                    0.0, null, false, null, null, null, stats,
                    null, null, null, null, null);
        }
    }

    public record Option(String optionId, String label) {}
}
