package com.ec26b.shoppingagent.chat;

import com.ec26b.shoppingagent.ai.RecognitionResult;
import com.ec26b.shoppingagent.product.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Pattern;

@Component
public class MockAgent {

    private final MockProductSourceProvider productSource;
    private final ShoppingIntentParser intentParser;
    private final RecommendationExplainer ruleExplainer;
    private final ArkRecommendationExplainer arkExplainer;
    private final UserPreferenceParser preferenceParser;
    private final boolean useArk;

    private static final Pattern SHOPPING_WORDS = Pattern.compile(
            "买|想买|想要|推荐|帮我找|找.*商品|多少钱|价格|便宜|优惠|性价比|官方|自营|旗舰|配送|物流|评价|评分|销量|预算|以内|不超过|以下");

    public MockAgent(MockProductSourceProvider productSource,
                     ShoppingIntentParser intentParser,
                     RecommendationExplainer ruleExplainer,
                     ArkRecommendationExplainer arkExplainer,
                     UserPreferenceParser preferenceParser,
                     @Value("${app.ai.provider:mock}") String aiProvider) {
        this.productSource = productSource;
        this.intentParser = intentParser;
        this.ruleExplainer = ruleExplainer;
        this.arkExplainer = arkExplainer;
        this.preferenceParser = preferenceParser;
        this.useArk = "ark".equalsIgnoreCase(aiProvider);
    }

    public AgentReply process(ChatStore.ChatSession session, String text,
                              List<String> imageIds, List<String> selectedOptionIds) {
        boolean hasOptions = selectedOptionIds != null && !selectedOptionIds.isEmpty();
        boolean hasImages = imageIds != null && !imageIds.isEmpty();

        if (hasOptions || hasImages) {
            if (hasOptions) {
                MergedContext ctx = mergeContext(session, text);
                List<String> mergedPrefs = mergePreferenceIds(ctx.preferenceIds(), selectedOptionIds);
                return buildProductRecommendation(mergedPrefs,
                        coalesce(text, ctx.effectiveText()),
                        ctx.effectiveCategory(), ctx.color(), ctx.maxPrice(),
                        ctx.brand(), ctx.platforms(), ctx.sortBy(), ctx.minRating(),
                        selectedOptionIds);
            }
            return buildRecognitionReply(imageIds);
        }

        boolean isRefinement = isRefinementText(text);
        boolean isShopping = isShoppingIntent(text);
        if (isShopping || isRefinement) {
            MergedContext ctx = mergeContext(session, text);
            return buildProductRecommendation(ctx.preferenceIds(), ctx.effectiveText(),
                    ctx.effectiveCategory(), ctx.color(), ctx.maxPrice(),
                    ctx.brand(), ctx.platforms(), ctx.sortBy(), ctx.minRating(),
                    List.of());
        }
        return buildClarification(null);
    }

    public AgentReply processWithRecognition(ChatStore.ChatSession session, String text,
                                             List<String> imageIds, List<String> selectedOptionIds,
                                             RecognitionResult recResult) {
        if (selectedOptionIds != null && !selectedOptionIds.isEmpty()) {
            MergedContext ctx = mergeContext(session, text);
            List<String> mergedPrefs = mergePreferenceIds(ctx.preferenceIds(), selectedOptionIds);
            return buildProductRecommendation(mergedPrefs,
                    coalesce(text, ctx.effectiveText()),
                    recResult.getCategory(), ctx.color(), ctx.maxPrice(),
                    ctx.brand(), ctx.platforms(), ctx.sortBy(), ctx.minRating(),
                    selectedOptionIds);
        }
        return buildRecognitionReplyWithResult(recResult);
    }

    // ── Helpers ──────────────────────────────────────────────

    private String coalesce(String a, String b) {
        if (a != null && !a.isBlank()) return a;
        return b != null ? b : "";
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

    private boolean isRefinementText(String text) {
        if (text == null || text.isBlank()) return false;
        String t = text.trim();
        if (t.matches(".*\\d+\\s*(元|块)?\\s*(以内|以下|不超过|内).*")) return true;
        if (t.matches(".*不超过\\s*\\d+.*")) return true;
        if (t.matches(".*预算\\s*\\d+.*")) return true;
        if (t.contains("色") || t.contains("款")) return true;
        if (t.contains("官方") || t.contains("自营") || t.contains("旗舰")) return true;
        if (t.contains("评分高") || t.contains("好评") || t.contains("分以上") || t.contains("星以上")) return true;
        if (t.contains("销量高") || t.contains("爆款")) return true;
        if (t.contains("低价") || t.contains("便宜") || t.contains("配送快")) return true;
        if (t.contains("只看") || t.contains("只要")) return true;
        if (t.contains("京东") || t.contains("拼多多") || t.contains("淘宝") || t.contains("天猫")) return true;
        if (t.contains("排序") || t.contains("价格从") || t.contains("价格升序") || t.contains("价格降序")) return true;
        return false;
    }

    private List<String> mergePreferenceIds(List<String> a, List<String> b) {
        Set<String> set = new LinkedHashSet<>();
        if (a != null) set.addAll(a);
        if (b != null) set.addAll(b);
        return new ArrayList<>(set);
    }

    private record MergedContext(
            String effectiveText,
            String effectiveCategory,
            String color,
            List<String> preferenceIds,
            Double maxPrice,
            String brand,
            List<String> platforms,
            String sortBy,
            Double minRating
    ) {}

    private MergedContext mergeContext(ChatStore.ChatSession session, String currentText) {
        String currentExplicitKeyword = RuleBasedShoppingIntentParser.parseExplicitKeyword(currentText);
        UserPreference currentPref = preferenceParser.parse(currentText);

        String histKeyword = null;
        String histRecCategory = findRecognitionCategory(session);
        Double histMaxPrice = null;
        String histColor = null;
        String histBrand = null;
        List<String> histPlatforms = new ArrayList<>();
        String histSortBy = null;
        Double histMinRating = null;
        boolean histOfficial = false, histFast = false, histLow = false, histRating = false, histSales = false;

        var msgs = session.messages();
        for (var m : msgs) {
            if ("user".equals(m.role()) && m.text() != null && !m.text().isBlank()) {
                String ek = RuleBasedShoppingIntentParser.parseExplicitKeyword(m.text());
                if (ek != null) histKeyword = ek;
                UserPreference p = preferenceParser.parse(m.text());
                if (p.maxPrice() != null) histMaxPrice = p.maxPrice();
                if (p.color() != null) histColor = p.color();
                if (p.brand() != null) histBrand = p.brand();
                if (!p.platforms().isEmpty()) histPlatforms = new ArrayList<>(p.platforms());
                if (p.sortBy() != null) histSortBy = p.sortBy();
                if (p.minRating() != null) histMinRating = p.minRating();
                histOfficial = histOfficial || p.officialStore();
                histFast = histFast || p.fastDelivery();
                histLow = histLow || p.lowestPrice();
                histRating = histRating || p.highRating();
                histSales = histSales || p.highSales();
            }
        }

        String effectiveCategory;
        String normalizedRecognitionCategory = RuleBasedShoppingIntentParser.parseExplicitKeyword(histRecCategory);
        if (currentExplicitKeyword != null) {
            effectiveCategory = currentExplicitKeyword;
        } else if (histKeyword != null) {
            effectiveCategory = histKeyword;
        } else if (RuleBasedShoppingIntentParser.isSupportedCategory(histRecCategory)) {
            effectiveCategory = histRecCategory;
        } else if (normalizedRecognitionCategory != null) {
            effectiveCategory = normalizedRecognitionCategory;
        } else {
            effectiveCategory = "运动鞋";
        }

        Double effectiveMaxPrice = currentPref.maxPrice() != null ? currentPref.maxPrice() : histMaxPrice;
        String effectiveColor = currentPref.color() != null ? currentPref.color() : histColor;
        String effectiveBrand = currentPref.brand() != null ? currentPref.brand() : histBrand;
        List<String> effectivePlatforms = !currentPref.platforms().isEmpty() ? currentPref.platforms() : histPlatforms;
        String effectiveSortBy = currentPref.sortBy() != null ? currentPref.sortBy() : histSortBy;
        Double effectiveMinRating = currentPref.minRating() != null ? currentPref.minRating() : histMinRating;

        boolean official = currentPref.officialStore() || histOfficial;
        boolean fast = currentPref.fastDelivery() || histFast;
        boolean low = currentPref.lowestPrice() || histLow;
        boolean rating = currentPref.highRating() || histRating;
        boolean sales = currentPref.highSales() || histSales;

        UserPreference merged = new UserPreference(effectiveMaxPrice, effectiveColor,
                official, fast, low, rating, sales,
                effectiveBrand, effectivePlatforms, effectiveSortBy, effectiveMinRating);

        return new MergedContext(currentText, effectiveCategory, effectiveColor,
                merged.toPreferenceIds(), effectiveMaxPrice,
                effectiveBrand, effectivePlatforms, effectiveSortBy, effectiveMinRating);
    }

    // ── Product recommendation ───────────────────────────────

    private AgentReply buildProductRecommendation(List<String> prefs, String text,
                                                   String category, String overrideColor,
                                                   Double overrideMaxPrice,
                                                   String overrideBrand,
                                                   List<String> overridePlatforms,
                                                   String overrideSortBy,
                                                   Double overrideMinRating,
                                                   List<String> selectedOptionIds) {
        ShoppingIntent intent = intentParser.parse(text);
        boolean hasLowest = prefs != null && prefs.contains("lowest_price");
        boolean hasOfficial = prefs != null && prefs.contains("official_store");
        boolean hasFast = prefs != null && prefs.contains("fast_delivery");
        boolean hasHighRating = prefs != null && prefs.contains("high_rating");
        boolean hasHighSales = prefs != null && prefs.contains("high_sales");
        if (hasLowest || hasOfficial || hasFast || hasHighRating || hasHighSales) {
            intent = new ShoppingIntent(intent.keyword(), intent.maxPrice(), intent.color(),
                    intent.officialStore() || hasOfficial,
                    intent.fastDelivery() || hasFast,
                    intent.lowestPrice() || hasLowest,
                    intent.highRating() || hasHighRating,
                    intent.highSales() || hasHighSales,
                    intent.brand(), intent.platforms(), intent.sortBy(), intent.minRating(),
                    intent.needsClarification(), intent.clarificationQuestion(),
                    intent.intentProvider(), intent.intentFallbackUsed(), intent.notices());
        }
        List<String> effectivePrefs = intent.toPreferenceIds();
        String effectiveColor = overrideColor != null ? overrideColor : intent.color();
        Double effectiveMaxPrice = overrideMaxPrice != null ? overrideMaxPrice : intent.maxPrice();
        String effectiveBrand = overrideBrand != null ? overrideBrand : intent.brand();
        List<String> effectivePlatforms = overridePlatforms != null && !overridePlatforms.isEmpty()
                ? overridePlatforms : intent.platforms();
        String effectiveSortBy = overrideSortBy != null ? overrideSortBy : intent.sortBy();
        Double effectiveMinRating = overrideMinRating != null ? overrideMinRating : intent.minRating();

        // Option-driven sort override for explicit click on "lowest_price"
        if (selectedOptionIds != null && selectedOptionIds.contains("lowest_price")
                && effectiveSortBy == null) {
            effectiveSortBy = "price_asc";
        }

        String keyword = RuleBasedShoppingIntentParser.resolveKeyword(category, intent.keyword());
        ShoppingIntent fullIntent = new ShoppingIntent(keyword, effectiveMaxPrice, effectiveColor,
                intent.officialStore(), intent.fastDelivery(), intent.lowestPrice(),
                intent.highRating(), intent.highSales(),
                effectiveBrand, effectivePlatforms, effectiveSortBy, effectiveMinRating,
                intent.needsClarification(), intent.clarificationQuestion(),
                intent.intentProvider(), intent.intentFallbackUsed(), intent.notices());
        List<String> filterSummary = buildFilterSummary(fullIntent);

        ProductSearchResult sr = productSource.search(
                new ProductSearchQuery(keyword, effectivePrefs, effectiveMaxPrice, effectiveColor,
                        effectiveBrand, effectivePlatforms, effectiveSortBy, effectiveMinRating));
        List<Card> cards = new ArrayList<>();

        cards.add(Card.productList("多平台商品结果", sr.products(), filterSummary));
        cards.add(Card.comparison("平台比价", sr.platformStats()));

        if (sr.products().isEmpty()) {
            String note = noEmptyNote(effectiveMaxPrice, effectiveBrand, effectiveColor, effectiveMinRating);
            return new AgentReply(UUID.randomUUID().toString(), "product_recommendation", note, cards);
        }

        RecommendationExplanation ruleExp = ruleExplainer.explain(sr, fullIntent.toUserPreference(), keyword);
        RecommendationExplanation exp;
        if (useArk) {
            exp = arkExplainer.explain(ruleExp, fullIntent, sr);
        } else {
            exp = ruleExp;
        }

        if (sr.topPick() != null) {
            ProductOffer t = sr.topPick();
            List<String> allNotices = new ArrayList<>(fullIntent.notices());
            allNotices.addAll(exp.notices());
            cards.add(Card.recommendation("推荐购买", t.title(), t.platform(), t.price(),
                    exp.summaryReason(),
                    exp.decisionScore(), exp.decisionSignals(), exp.evidence(),
                    exp.risks(), exp.productAnalyses(),
                    fullIntent.intentProvider(), fullIntent.intentFallbackUsed(),
                    exp.explanationProvider(), exp.explanationFallbackUsed(),
                    allNotices));
        }

        return new AgentReply(UUID.randomUUID().toString(),
                "product_recommendation", "我按你的偏好整理了几个平台的选择。", cards);
    }

    private String noEmptyNote(Double maxPrice, String brand, String color, Double minRating) {
        List<String> hints = new ArrayList<>();
        if (maxPrice != null) hints.add("预算 ≤ " + maxPrice.intValue() + " 元");
        if (brand != null) hints.add("品牌 " + brand);
        if (color != null) hints.add("颜色 " + color);
        if (minRating != null) hints.add("评分 ≥ " + minRating + " 星");
        if (hints.isEmpty()) return "暂无合适的 Mock 商品。";
        return "当前筛选（" + String.join("、", hints) + "）下暂无合适的 Mock 商品，请放宽条件。";
    }

    private List<String> buildFilterSummary(ShoppingIntent intent) {
        List<String> parts = new ArrayList<>();
        if (intent.keyword() != null && !intent.keyword().isBlank()) {
            parts.add("品类：" + intent.keyword());
        }
        if (intent.maxPrice() != null) {
            parts.add("预算≤" + formatNumber(intent.maxPrice()) + "元");
        }
        if (intent.color() != null && !intent.color().isBlank()) {
            parts.add("颜色：" + intent.color());
        }
        if (intent.brand() != null && !intent.brand().isBlank()) {
            parts.add("品牌：" + intent.brand());
        }
        if (intent.platforms() != null && !intent.platforms().isEmpty()) {
            List<String> labels = new ArrayList<>();
            for (String platform : intent.platforms()) {
                labels.add(platformLabel(platform));
            }
            parts.add("平台：" + String.join("、", labels));
        }
        if (intent.minRating() != null) {
            parts.add("评分≥" + formatNumber(intent.minRating()));
        }
        String sort = sortLabel(intent.sortBy());
        if (sort != null) {
            parts.add("排序：" + sort);
        }
        List<String> preferenceLabels = new ArrayList<>();
        if (intent.officialStore()) preferenceLabels.add("官方/自营");
        if (intent.fastDelivery()) preferenceLabels.add("配送更快");
        if (intent.lowestPrice() && !"price_asc".equals(intent.sortBy())) preferenceLabels.add("低价优先");
        if (intent.highRating()) preferenceLabels.add("高评分");
        if (intent.highSales()) preferenceLabels.add("高销量");
        if (!preferenceLabels.isEmpty()) {
            parts.add("偏好：" + String.join("、", preferenceLabels));
        }
        return parts;
    }

    private String platformLabel(String platform) {
        return switch (platform) {
            case "京东-mock" -> "京东";
            case "拼多多-mock" -> "拼多多";
            case "淘宝-mock" -> "淘宝";
            default -> platform;
        };
    }

    private String sortLabel(String sortBy) {
        return switch (sortBy == null ? "" : sortBy) {
            case "price_asc" -> "价格从低到高";
            case "price_desc" -> "价格从高到低";
            case "sales_desc" -> "销量优先";
            case "rating_desc" -> "评分优先";
            case "recommended" -> "综合推荐";
            default -> null;
        };
    }

    private String formatNumber(Double value) {
        return BigDecimal.valueOf(value).stripTrailingZeros().toPlainString();
    }

    // ── Recognition ──────────────────────────────────────────

    private AgentReply buildRecognitionReply(List<String> imageIds) {
        Card rec = Card.recognition(imageIds.get(0), "运动鞋", "Mock 品牌", "Mock 型号",
                List.of("运动鞋", "白色", "跑步鞋"), Map.of("color", "白色", "style", "通勤运动鞋"),
                0.82, "mock", false, "当前为演示识别结果。", null);
        return new AgentReply(UUID.randomUUID().toString(), "recognition",
                "我已经识别了你的商品图片。你更看重哪一点？",
                List.of(rec, buildSuggestionCard("运动鞋", null)));
    }

    private AgentReply buildRecognitionReplyWithResult(RecognitionResult rec) {
        Card recCard = Card.recognition(rec.getImageId(), rec.getCategory(),
                rec.getBrand(), rec.getModel(), rec.getKeywords(), rec.getAttributes(),
                rec.getConfidence(), rec.getAiProvider(), rec.isFallbackUsed(),
                rec.getExplanation(), rec.getRecognitionId());
        return new AgentReply(UUID.randomUUID().toString(), "recognition",
                "我已经识别了你的商品图片。你更看重哪一点？",
                List.of(recCard, buildSuggestionCard(rec.getCategory(), rec.getBrand())));
    }

    private AgentReply buildClarification(String category) {
        return new AgentReply(UUID.randomUUID().toString(), "clarification",
                "我已经收到你的需求。你更看重哪一点？",
                List.of(buildSuggestionCard(category, null)));
    }

    /**
     * Build a dynamic suggestion card whose options vary by recognized category and brand.
     */
    private Card buildSuggestionCard(String category, String brand) {
        List<Option> options = new ArrayList<>();
        options.add(new Option("lowest_price", "查看同款低价"));
        options.add(new Option("official_store", "只看官方旗舰店"));
        options.add(new Option("fast_delivery", "配送更快"));

        if (RuleBasedShoppingIntentParser.isSupportedCategory(category)) {
            switch (category) {
                case "运动鞋" -> {
                    options.add(new Option("style_similar", "相似风格推荐"));
                    options.add(new Option("filter_color", "筛选颜色/品牌/尺码"));
                }
                case "耳机" -> {
                    options.add(new Option("noise_cancel", "降噪款优先"));
                    options.add(new Option("high_rating", "好评率优先"));
                }
                case "吹风机" -> {
                    options.add(new Option("high_power", "大功率优先"));
                    options.add(new Option("portable", "便携折叠款"));
                }
                case "背包" -> {
                    options.add(new Option("large_capacity", "大容量款"));
                    options.add(new Option("business", "商务款"));
                }
                case "智能手表" -> {
                    options.add(new Option("long_battery", "长续航款"));
                    options.add(new Option("sports", "运动款"));
                }
            }
        }
        if (brand != null && !brand.isBlank()) {
            options.add(new Option("filter_same_brand", "只看 " + brand));
        }
        options.add(new Option("price_history", "查看历史价格走势"));

        String title = category != null && !category.isBlank()
                ? "你更想看哪类「" + category + "」推荐？"
                : "你更看重哪一点？";
        return new Card("clarification", title, null, null, null, null,
                options,
                null, null, null, null, null, null,
                0.0, null, false, null, null, null, null,
                null, null, null, null, null,
                null, null, null, null, null,
                null);
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
            Integer decisionScore,
            List<DecisionSignal> decisionSignals,
            List<RecommendationEvidence> evidence,
            List<String> risks,
            List<ProductAnalysis> productAnalyses,
            String intentProvider,
            Boolean intentFallbackUsed,
            String explanationProvider,
            Boolean explanationFallbackUsed,
            List<String> notices,
            List<String> filterSummary) {

        public static Card clarification(String title) {
            return new Card("clarification", title, null, null, null, null,
                    List.of(new Option("lowest_price", "价格最低"),
                            new Option("official_store", "官方店铺"),
                            new Option("fast_delivery", "配送更快")),
                    null, null, null, null, null, null,
                    0.0, null, false, null, null, null, null,
                    null, null, null, null, null,
                    null, null, null, null, null,
                    null);
        }

        public static Card recommendation(String title, String productName,
                                          String platform, Double price, String reason,
                                          Integer decisionScore,
                                          List<DecisionSignal> signals,
                                          List<RecommendationEvidence> evidence,
                                          List<String> risks,
                                          List<ProductAnalysis> analyses,
                                          String intentProvider, Boolean intentFallback,
                                          String explProvider, Boolean explFallback,
                                          List<String> notices) {
            return new Card("recommendation", title, productName, platform, price, reason,
                    null, null, null, null, null, null, null,
                    0.0, null, false, null, null, null, null,
                    decisionScore, signals, evidence, risks, analyses,
                    intentProvider, intentFallback, explProvider, explFallback, notices,
                    null);
        }

        public static Card recognition(String imageId, String category, String brand,
                                       String model, List<String> keywords,
                                       Map<String, Object> attributes, double conf,
                                       String aiProvider, boolean fallback,
                                       String explanation, String recognitionId) {
            return new Card("recognition", "识别结果", null, null, null, null, null,
                    imageId, category, brand, model, keywords, attributes,
                    conf, aiProvider, fallback, explanation, recognitionId,
                    null, null, null, null, null, null, null,
                    null, null, null, null, null,
                    null);
        }

        public static Card productList(String title, List<ProductOffer> products,
                                       List<String> filterSummary) {
            return new Card("product_list", title, null, null, null, null, null,
                    null, null, null, null, null, null,
                    0.0, null, false, null, null, products, null,
                    null, null, null, null, null,
                    null, null, null, null, null,
                    filterSummary);
        }

        public static Card comparison(String title,
                                      Map<String, ProductSearchResult.PlatformStats> stats) {
            return new Card("comparison", title, null, null, null, null, null,
                    null, null, null, null, null, null,
                    0.0, null, false, null, null, null, stats,
                    null, null, null, null, null,
                    null, null, null, null, null,
                    null);
        }
    }

    public record Option(String optionId, String label) {}
}
