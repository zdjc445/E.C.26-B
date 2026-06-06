package com.ec26b.shoppingagent.chat;

import com.ec26b.shoppingagent.ai.RecognitionResult;
import com.ec26b.shoppingagent.product.MockProductSourceProvider;
import com.ec26b.shoppingagent.product.ProductOffer;
import com.ec26b.shoppingagent.product.ProductSearchQuery;
import com.ec26b.shoppingagent.product.ProductSearchResult;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Component
public class MockAgent {

    private final MockProductSourceProvider productSource;
    private static final Pattern SHOPPING_WORDS = Pattern.compile(
            "买|想买|想要|推荐|帮我找|找.*商品|多少钱|价格|便宜|优惠|性价比|官方|自营|旗舰|配送|物流|评价|评分|销量|预算|以内|不超过|以下");

    public MockAgent(MockProductSourceProvider productSource) {
        this.productSource = productSource;
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
        if (hasImages) {
            return buildRecognitionReply(imageIds);
        }
        if (isShoppingIntent(text)) {
            return buildProductRecommendation(List.of(), text);
        }
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

    /** Walk session messages backwards to find the most recent user text. */
    private String findLastUserText(ChatStore.ChatSession session) {
        var msgs = session.messages();
        for (int i = msgs.size() - 1; i >= 0; i--) {
            var m = msgs.get(i);
            if ("user".equals(m.role()) && m.text() != null && !m.text().isBlank()) {
                return m.text();
            }
        }
        return "";
    }

    /** Walk session messages backwards to find the most recent recognition category. */
    private String findRecognitionCategory(ChatStore.ChatSession session) {
        var msgs = session.messages();
        for (int i = msgs.size() - 1; i >= 0; i--) {
            var m = msgs.get(i);
            if ("assistant".equals(m.role()) && m.agentReply() != null) {
                for (Card card : m.agentReply().cards()) {
                    if ("recognition".equals(card.cardType()) && card.category() != null) {
                        return card.category();
                    }
                }
            }
        }
        return null;
    }

    private boolean isShoppingIntent(String text) {
        if (text == null || text.isBlank()) return false;
        return SHOPPING_WORDS.matcher(text).find();
    }

    String extractKeyword(String text) {
        if (text == null) return "运动鞋";
        if (text.contains("运动鞋")) return "运动鞋";
        if (text.contains("耳机")) return "耳机";
        if (text.contains("吹风机")) return "吹风机";
        return "运动鞋";
    }

    private Double parseMaxPrice(String text) {
        if (text == null) return null;
        // Try multi-pattern: pattern1 = "300以内/以下/不超过", pattern2 = "不超过300", pattern3 = "预算300"
        Matcher m = Pattern.compile("(\\d+)\\s*(元|块)?\\s*(以内|以下|不超过|内)").matcher(text);
        if (m.find()) {
            try { return Double.parseDouble(m.group(1)); } catch (NumberFormatException e) {}
        }
        m = Pattern.compile("不超过\\s*(\\d+)").matcher(text);
        if (m.find()) {
            try { return Double.parseDouble(m.group(1)); } catch (NumberFormatException e) {}
        }
        m = Pattern.compile("预算\\s*(\\d+)").matcher(text);
        if (m.find()) {
            try { return Double.parseDouble(m.group(1)); } catch (NumberFormatException e) {}
        }
        return null;
    }

    // ── Product recommendation ───────────────────────────────

    private AgentReply buildProductRecommendation(List<String> prefs, String text) {
        return buildProductRecommendation(prefs, text, null);
    }

    private AgentReply buildProductRecommendation(List<String> prefs, String text, String category) {
        // Keyword: use category>text extraction>default
        String keyword = category != null && !category.isBlank()
                ? category
                : extractKeyword(text);

        Double maxPrice = parseMaxPrice(text);

        ProductSearchResult sr = productSource.search(
                new ProductSearchQuery(keyword, prefs, maxPrice));
        List<Card> cards = new ArrayList<>();

        cards.add(Card.productList("多平台商品结果", sr.products()));
        cards.add(Card.comparison("平台比价", sr.platformStats()));

        if (sr.products().isEmpty()) {
            String budgetNote = maxPrice != null
                    ? "当前预算下（≤" + maxPrice.intValue() + "元）暂无合适的 Mock 商品，请调整预算或偏好。"
                    : "暂无合适的 Mock 商品。";
            return new AgentReply(UUID.randomUUID().toString(),
                    "product_recommendation", budgetNote, cards);
        }

        if (sr.topPick() != null) {
            ProductOffer t = sr.topPick();
            cards.add(Card.recommendation("推荐购买", t.title(), t.platform(),
                    t.price(), String.join("；",
                            t.reasons().isEmpty() ? List.of("综合评分较高") : t.reasons())));
        }

        return new AgentReply(UUID.randomUUID().toString(),
                "product_recommendation", "我按你的偏好整理了几个平台的选择。", cards);
    }

    // ── Recognition ──────────────────────────────────────────

    private AgentReply buildRecognitionReply(List<String> imageIds) {
        Card recCard = Card.recognition(imageIds.get(0), "运动鞋", "Mock 品牌", "Mock 型号",
                List.of("运动鞋", "白色", "跑步鞋"),
                Map.of("color", "白色", "style", "通勤运动鞋"),
                0.82, "mock", false, "当前为演示识别结果。", null);
        Card clarCard = Card.clarification("你更看重哪一点？");
        return new AgentReply(UUID.randomUUID().toString(), "recognition",
                "我已经识别了你的商品图片。你更看重哪一点？", List.of(recCard, clarCard));
    }

    private AgentReply buildRecognitionReplyWithResult(RecognitionResult rec) {
        Card recCard = Card.recognition(rec.getImageId(), rec.getCategory(),
                rec.getBrand(), rec.getModel(), rec.getKeywords(),
                rec.getAttributes(), rec.getConfidence(), rec.getAiProvider(),
                rec.isFallbackUsed(), rec.getExplanation(), rec.getRecognitionId());
        Card clarCard = Card.clarification("你更看重哪一点？");
        return new AgentReply(UUID.randomUUID().toString(), "recognition",
                "我已经识别了你的商品图片。你更看重哪一点？", List.of(recCard, clarCard));
    }

    // ── Clarification ────────────────────────────────────────

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
            Map<String, ProductSearchResult.PlatformStats> platformStats) {

        public static Card clarification(String title) {
            return new Card("clarification", title, null, null, null, null,
                    List.of(new Option("lowest_price", "价格最低"),
                            new Option("official_store", "官方店铺"),
                            new Option("fast_delivery", "配送更快")),
                    null, null, null, null, null, null,
                    0.0, null, false, null, null, null, null);
        }

        public static Card recommendation(String title, String productName,
                                          String platform, Double price, String reason) {
            return new Card("recommendation", title, productName, platform, price, reason,
                    null, null, null, null, null, null, null,
                    0.0, null, false, null, null, null, null);
        }

        public static Card recognition(String imageId, String category, String brand,
                                       String model, List<String> keywords,
                                       Map<String, Object> attributes, double confidence,
                                       String aiProvider, boolean fallbackUsed,
                                       String explanation, String recognitionId) {
            return new Card("recognition", "识别结果", null, null, null, null, null,
                    imageId, category, brand, model, keywords, attributes,
                    confidence, aiProvider, fallbackUsed, explanation, recognitionId,
                    null, null);
        }

        public static Card productList(String title, List<ProductOffer> products) {
            return new Card("product_list", title, null, null, null, null, null,
                    null, null, null, null, null, null,
                    0.0, null, false, null, null, products, null);
        }

        public static Card comparison(String title,
                                      Map<String, ProductSearchResult.PlatformStats> stats) {
            return new Card("comparison", title, null, null, null, null, null,
                    null, null, null, null, null, null,
                    0.0, null, false, null, null, null, stats);
        }
    }

    public record Option(String optionId, String label) {}
}
