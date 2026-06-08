package com.ec26b.shoppingagent.chat;

import com.ec26b.shoppingagent.ai.RecognitionResult;
import com.ec26b.shoppingagent.product.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Pattern;

@Component
public class MockAgent {

    private final ProductSourceProvider productSource;
    private final ShoppingIntentParser intentParser;
    private final RecommendationExplainer ruleExplainer;
    private final ArkRecommendationExplainer arkExplainer;
    private final UserPreferenceParser preferenceParser;
    private final boolean useArk;

    private static final Pattern SHOPPING_WORDS = Pattern.compile(
            "买|想买|想要|推荐|帮我找|找.*商品|多少钱|价格|便宜|优惠|性价比|官方|自营|旗舰|配送|物流|评价|评分|销量|预算|以内|不超过|以下");
    private static final Set<String> DEFAULT_PLATFORM_SET = Set.of("京东-mock", "拼多多-mock", "淘宝-mock");

    public MockAgent(ProductSourceProvider productSource,
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
                    // Check recognition cards (legacy) and product_group_list cards
                    // that carry recognition metadata (new format)
                    if (card.category() != null &&
                            ("recognition".equals(card.cardType())
                                    || "product_group_list".equals(card.cardType())))
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
        String currentExplicitKeyword = CategoryResolver.defaultResolver().resolveName(currentText);
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
                String ek = CategoryResolver.defaultResolver().resolveName(m.text());
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
        String normalizedRecognitionCategory = CategoryResolver.defaultResolver().resolveName(histRecCategory);
        if (currentExplicitKeyword != null) {
            effectiveCategory = currentExplicitKeyword;
        } else if (histKeyword != null) {
            effectiveCategory = histKeyword;
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
                new ProductSearchQuery(keyword, fullIntent.toPreferenceIds(), effectiveMaxPrice,
                        effectiveColor, effectiveBrand, effectivePlatforms,
                        effectiveSortBy, effectiveMinRating));
        List<Card> cards = new ArrayList<>();

        // Build product groups from search results.
        // Wrap in mutable list — groupProducts may return immutable List.of() when empty.
        List<ProductGroup> groups = new ArrayList<>(
                groupProducts(sr.products(), fullIntent, sr));

        // If strict filtering left us with fewer than 3 groups, try a relaxed search.
        // This handles both "no products at all" (e.g., very tight budget) and
        // "some products but fewer than 3 groups after grouping".
        if (groups.size() < 3) {
            int needed = 3 - groups.size();
            List<ProductOffer> relaxed = findRelaxedProducts(sr.products(), fullIntent, needed);
            for (ProductOffer p : relaxed) {
                mergeRelaxedProduct(groups, p, keyword);
            }
            // Re-sort after merging
            sortGroupsByCompositeScore(groups, fullIntent);
        }

        String emptyReason = null;
        if (groups.isEmpty()) {
            emptyReason = noEmptyNote(effectiveMaxPrice, effectiveBrand, effectiveColor, effectiveMinRating);
        }

        // Always emit product_group_list + clarification
        cards.add(Card.productGroupList("匹配商品", groups, filterSummary, emptyReason));
        cards.add(buildSuggestionCard(keyword, effectiveBrand));

        String replyText;
        if (groups.isEmpty()) {
            replyText = emptyReason != null ? emptyReason : "暂无合适的商品。";
        } else if (groups.size() == 1) {
            replyText = "找到 1 组匹配商品，你更看重哪一点？";
        } else {
            replyText = "找到 " + groups.size() + " 组匹配商品，你更看重哪一点？";
        }

        return new AgentReply(UUID.randomUUID().toString(),
                "product_recommendation", replyText, cards);
    }

    /**
     * Group products by {@code sameItemKey}.
     * <ul>
     *   <li>Same {@code sameItemKey} (non-null, non-blank) → same group</li>
     *   <li>Null/blank {@code sameItemKey} → one group per product (groupId = productId)</li>
     *   <li>Target 3–6 groups from strict matches</li>
     *   <li>If fewer than 3 strict groups, relax non-category constraints to reach 3</li>
     *   <li>Relaxed groups are marked {@code matchLevel = "relaxed"}</li>
     *   <li>Max 6 groups total</li>
     *   <li>Groups are sorted by composite match strength, not by price</li>
     * </ul>
     */
    private List<ProductGroup> groupProducts(List<ProductOffer> products,
                                              ShoppingIntent intent,
                                              ProductSearchResult sr) {
        if (products.isEmpty()) return List.of();

        String effectiveCategory = intent.keyword();

        // Phase 1: group by sameItemKey (non-null, non-blank)
        Map<String, List<ProductOffer>> keyGroups = new LinkedHashMap<>();
        List<ProductOffer> unkeyed = new ArrayList<>();

        for (ProductOffer p : products) {
            String key = p.sameItemKey();
            if (key != null && !key.isBlank()) {
                keyGroups.computeIfAbsent(key, k -> new ArrayList<>()).add(p);
            } else {
                unkeyed.add(p);
            }
        }

        List<ProductGroup> groups = new ArrayList<>();

        // Build groups from sameItemKey clusters
        for (var entry : keyGroups.entrySet()) {
            groups.add(buildGroup(entry.getKey(), entry.getValue(), "strict", effectiveCategory));
        }

        // Build individual groups for unkeyed products
        for (ProductOffer p : unkeyed) {
            groups.add(buildGroup(p.productId(), List.of(p), "strict", effectiveCategory));
        }

        // Phase 2: sort by composite match strength (strict → highest score/rating/sales → best price)
        sortGroupsByCompositeScore(groups, intent);

        // Select top groups first (strict), then relax if under target
        int targetMin = 3;
        int targetMax = 6;

        List<ProductGroup> strictGroups = groups.stream()
                .filter(g -> "strict".equals(g.matchLevel()))
                .toList();

        List<ProductGroup> result = new ArrayList<>();

        if (strictGroups.size() >= targetMin) {
            // Enough strict groups — take top N
            result.addAll(strictGroups.subList(0, Math.min(strictGroups.size(), targetMax)));
        } else {
            // Not enough strict — take all strict, then relax
            result.addAll(strictGroups);

            // Relax: expand non-category constraints (color, rating, platform, brand)
            int needed = targetMin - result.size();
            List<ProductOffer> relaxed = findRelaxedProducts(products, intent, needed);
            for (ProductOffer p : relaxed) {
                mergeRelaxedProduct(result, p, effectiveCategory);
            }
            // Re-sort after merging relaxed products
            sortGroupsByCompositeScore(result, intent);
        }

        // Trim to max
        if (result.size() > targetMax) {
            result = new ArrayList<>(result.subList(0, targetMax));
        }

        return result;
    }

    /**
     * Sort groups by composite match strength:
     *  1. Strict before relaxed
     *  2. Highest max score in group
     *  3. Highest max rating
     *  4. Highest max sales
     *  5. Lowest price as tiebreaker
     *
     * When intent requests explicit price sort, price ordering takes precedence.
     */
    private void sortGroupsByCompositeScore(List<ProductGroup> groups, ShoppingIntent intent) {
        boolean explicitPriceSort = "price_asc".equals(intent.sortBy())
                || "price_desc".equals(intent.sortBy());
        if (explicitPriceSort) {
            if ("price_asc".equals(intent.sortBy())) {
                groups.sort(Comparator.comparingDouble(ProductGroup::bestPrice));
            } else {
                groups.sort(Comparator.comparingDouble(ProductGroup::bestPrice).reversed());
            }
        } else {
            groups.sort(Comparator
                    .comparingInt((ProductGroup g) -> "strict".equals(g.matchLevel()) ? 0 : 1)
                    .thenComparingDouble((ProductGroup g) -> -g.platforms().stream()
                            .mapToDouble(PlatformOfferSummary::score).max().orElse(0))
                    .thenComparingDouble((ProductGroup g) -> -g.platforms().stream()
                            .mapToDouble(PlatformOfferSummary::rating).max().orElse(0))
                    .thenComparingInt((ProductGroup g) -> -g.platforms().stream()
                            .mapToInt(PlatformOfferSummary::sales).max().orElse(0))
                    .thenComparingDouble(ProductGroup::bestPrice));
        }
    }

    /**
     * Merge a relaxed product into the result list, respecting {@code sameItemKey} so that
     * products belonging to the same item end up in one group (one card), never split across two.
     */
    private void mergeRelaxedProduct(List<ProductGroup> groups, ProductOffer p,
                                     String effectiveCategory) {
        // Check if product already exists in any group
        for (ProductGroup g : groups) {
            boolean alreadyPresent = g.platforms().stream()
                    .anyMatch(plat -> plat.productId().equals(p.productId()));
            if (alreadyPresent) return;
        }

        // If product has a sameItemKey, try to merge into an existing group with the same key
        String key = p.sameItemKey();
        if (key != null && !key.isBlank()) {
            for (int i = 0; i < groups.size(); i++) {
                ProductGroup g = groups.get(i);
                if (key.equals(g.sameItemKey())) {
                    // Merge into existing group: add the new platform to the existing group
                    List<PlatformOfferSummary> mergedPlatforms = new ArrayList<>(g.platforms());
                    String cat = resolveCategory(effectiveCategory, p);
                    mergedPlatforms.add(new PlatformOfferSummary(
                            p.productId(), p.platform(), p.price(), p.originalPrice(),
                            p.shopName(), p.productUrl(), p.rating(), p.sales(),
                            p.tags(), p.reasons(), p.score(),
                            p.title(), p.imageUrl(), p.brand(),
                            p.priceHistory(), p.matchedPreferences(),
                            deriveSpecs(p, cat)));
                    // Recompute group stats
                    double newBestPrice = Math.min(g.bestPrice(), p.price());
                    double newMinPrice = Math.min(g.priceRange() != null ? g.priceRange().min() : g.bestPrice(), p.price());
                    double newMaxPrice = Math.max(g.priceRange() != null ? g.priceRange().max() : g.bestPrice(), p.price());
                    List<String> newHighlights = new ArrayList<>(g.highlights());
                    if (!newHighlights.contains("多平台")) {
                        newHighlights.add("多平台");
                    }
                    ProductGroup merged = new ProductGroup(
                            g.groupId(), g.sameItemKey(), g.displayTitle(),
                            g.category(), g.brand(), g.thumbnailUrl(),
                            newBestPrice, g.originalPrice(),
                            new PriceRange(newMinPrice, newMaxPrice),
                            mergedPlatforms.size(), mergedPlatforms,
                            newHighlights, g.matchLevel());
                    groups.set(i, merged);
                    return;
                }
            }
        }

        // No existing group to merge into — create a new relaxed group
        groups.add(buildGroup(p.productId(), List.of(p), "relaxed", effectiveCategory));
    }

    /**
     * Find additional products by relaxing non-category constraints.
     * Relaxation order: color → rating → platform → brand.
     * Never relax category or budget.
     */
    private List<ProductOffer> findRelaxedProducts(List<ProductOffer> all,
                                                    ShoppingIntent intent,
                                                    int needed) {
        // Re-search without color, minRating, platform, or brand — keep only category and budget.
        String keyword = intent.keyword();
        ProductSearchQuery relaxedQuery = new ProductSearchQuery(
                keyword, List.of(), intent.maxPrice(), null,
                null, List.of(), intent.sortBy(), null);
        ProductSearchResult relaxedSr = productSource.search(relaxedQuery);

        List<ProductOffer> relaxedProducts = new ArrayList<>(relaxedSr.products());
        // Remove already-included products
        relaxedProducts.removeIf(p -> all.stream().anyMatch(
                a -> a.productId().equals(p.productId())));
        // Sort by score descending
        relaxedProducts.sort(Comparator.comparingDouble(ProductOffer::score).reversed());

        return relaxedProducts.subList(0, Math.min(needed, relaxedProducts.size()));
    }

    private ProductGroup buildGroup(String groupId, List<ProductOffer> products,
                                     String matchLevel, String effectiveCategory) {
        if (products.isEmpty()) throw new IllegalArgumentException("products must not be empty");

        ProductOffer first = products.get(0);

        // Compute best (lowest) price
        double bestPrice = products.stream().mapToDouble(ProductOffer::price).min().orElse(first.price());
        double originalPrice = first.originalPrice();

        // Compute price range
        double minPrice = products.stream().mapToDouble(ProductOffer::price).min().orElse(bestPrice);
        double maxPrice = products.stream().mapToDouble(ProductOffer::price).max().orElse(bestPrice);

        // Derive display title and category first — needed for specs derivation
        String displayTitle = deriveGroupTitle(products);
        // Category: use the resolved effective category (from search keyword / recognition).
        // Never fall back to brand — category is a product type, brand is a manufacturer.
        final String cat = resolveCategory(effectiveCategory, first);

        // Build platform summaries with extended fields
        List<PlatformOfferSummary> platforms = products.stream()
                .map(p -> new PlatformOfferSummary(
                        p.productId(), p.platform(), p.price(), p.originalPrice(),
                        p.shopName(), p.productUrl(), p.rating(), p.sales(),
                        p.tags(), p.reasons(), p.score(),
                        p.title(), p.imageUrl(), p.brand(),
                        p.priceHistory(), p.matchedPreferences(),
                        deriveSpecs(p, cat)))
                .toList();

        // Highlights — up to 3
        List<String> highlights = new ArrayList<>();
        highlights.add("最低 ¥" + formatPrice(bestPrice));
        if (products.size() > 1) {
            highlights.add(products.size() + " 个平台有售");
        }
        ProductOffer highestRated = products.stream()
                .max(Comparator.comparingDouble(ProductOffer::rating)).orElse(first);
        if (highestRated.rating() >= 4.5) {
            highlights.add("高评分");
        } else if (products.stream().anyMatch(p -> p.sales() >= 10000)) {
            highlights.add("高销量");
        } else if (bestPrice < originalPrice) {
            highlights.add("有优惠");
        }
        if (highlights.size() > 3) highlights = highlights.subList(0, 3);

        return new ProductGroup(
                groupId,
                first.sameItemKey(),
                displayTitle,
                cat,
                first.brand(),
                first.imageUrl(),
                bestPrice,
                originalPrice,
                new PriceRange(minPrice, maxPrice),
                products.size(),
                platforms,
                highlights,
                matchLevel
        );
    }

    private String resolveCategory(String effectiveCategory, ProductOffer first) {
        if (effectiveCategory != null && !effectiveCategory.isBlank()) return effectiveCategory;
        String resolved = CategoryResolver.defaultResolver().resolveName(first.title());
        if (resolved != null && !resolved.isBlank()) return resolved;
        return "其他";
    }

    /**
     * Derive product specs from the offer and the resolved category.
     * Always includes: 品类, 店铺, 平台服务.
     * Includes 品牌 only when present.
     * Includes 颜色 only when detectable from title/tags.
     */
    private static final Set<String> KNOWN_COLORS = Set.of(
            "白色", "黑色", "红色", "蓝色", "绿色", "黄色", "粉色", "紫色", "灰色", "银色",
            "金色", "棕色", "橘色", "橙色", "米色", "卡其色", "藏青", "深蓝", "浅灰", "深灰"
    );

    private List<ProductSpec> deriveSpecs(ProductOffer p, String category) {
        List<ProductSpec> specs = new ArrayList<>();
        specs.add(new ProductSpec("品类", category));
        if (p.brand() != null && !p.brand().isBlank()) {
            specs.add(new ProductSpec("品牌", p.brand()));
        }

        // Detect color from title and tags
        String combined = p.title() + " " + String.join(" ", p.tags());
        for (String color : KNOWN_COLORS) {
            if (combined.contains(color)) {
                specs.add(new ProductSpec("颜色", color));
                break;
            }
        }

        // Platform service tags
        List<String> serviceTags = new ArrayList<>();
        for (String tag : p.tags()) {
            if (tag.contains("自营") || tag.contains("官方") || tag.contains("包邮")
                    || tag.contains("配送") || tag.contains("售后") || tag.contains("发货")) {
                serviceTags.add(tag);
            }
        }
        if (!serviceTags.isEmpty()) {
            specs.add(new ProductSpec("平台服务", String.join("、", serviceTags)));
        } else {
            specs.add(new ProductSpec("平台服务", "标准配送"));
        }

        specs.add(new ProductSpec("店铺", p.shopName()));
        return specs;
    }

    private String deriveGroupTitle(List<ProductOffer> products) {
        ProductOffer best = products.stream()
                .min(Comparator.comparingDouble(ProductOffer::price)).orElse(products.get(0));
        String title = best.title();
        // Clean marketing words
        title = title.replaceAll("爆款|高性价比|专业级|高音质|新款|百搭配色|春季新款|经典|轻便|时尚设计", "");
        title = title.replaceAll("\\s+", " ").trim();
        if (title.length() > 36) {
            title = title.substring(0, 34) + "…";
        }
        if (title.isBlank()) {
            title = best.brand() != null ? best.brand() + " 商品" : "推荐商品";
        }
        return title;
    }

    private String formatPrice(double price) {
        return BigDecimal.valueOf(price).stripTrailingZeros().toPlainString();
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
        if (isMeaningfulMaxPrice(intent.maxPrice())) {
            parts.add("预算≤" + formatNumber(intent.maxPrice()) + "元");
        }
        if (intent.color() != null && !intent.color().isBlank()) {
            parts.add("颜色：" + intent.color());
        }
        if (intent.brand() != null && !intent.brand().isBlank()) {
            parts.add("品牌：" + intent.brand());
        }
        if (intent.platforms() != null && !intent.platforms().isEmpty()
                && !isDefaultPlatformSelection(intent.platforms())) {
            List<String> labels = new ArrayList<>();
            for (String platform : intent.platforms()) {
                labels.add(platformLabel(platform));
            }
            parts.add("平台：" + String.join("、", labels));
        }
        boolean hasMeaningfulMinRating = isMeaningfulMinRating(intent.minRating());
        if (hasMeaningfulMinRating) {
            parts.add("评分≥" + formatNumber(intent.minRating()));
        }
        String sort = sortLabel(intent.sortBy());
        if (sort != null && !"recommended".equals(intent.sortBy())) {
            parts.add("排序：" + sort);
        }
        List<String> preferenceLabels = new ArrayList<>();
        if (intent.officialStore()) preferenceLabels.add("官方/自营");
        if (intent.fastDelivery()) preferenceLabels.add("配送更快");
        if (intent.lowestPrice() && !"price_asc".equals(intent.sortBy())) preferenceLabels.add("低价优先");
        if (intent.highRating() && !hasMeaningfulMinRating) preferenceLabels.add("高评分");
        if (intent.highSales()) preferenceLabels.add("高销量");
        if (!preferenceLabels.isEmpty()) {
            parts.add("偏好：" + String.join("、", preferenceLabels));
        }
        return parts;
    }

    private boolean isDefaultPlatformSelection(List<String> platforms) {
        return platforms.size() == DEFAULT_PLATFORM_SET.size()
                && Set.copyOf(platforms).equals(DEFAULT_PLATFORM_SET);
    }

    private boolean isMeaningfulMaxPrice(Double maxPrice) {
        return maxPrice != null && maxPrice > 0.0 && maxPrice < 9999.0;
    }

    private boolean isMeaningfulMinRating(Double minRating) {
        return minRating != null && minRating > 0.0;
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
        // Search products for the recognized category to provide product_group_list
        String category = "运动鞋";
        String brand = "Mock 品牌";
        List<ProductGroup> groups = quickSearchGroups(category, null, null, null);
        String emptyReason = groups.isEmpty() ? "当前演示数据中暂无运动鞋商品。" : null;

        // Merge recognition info into filterSummary — no separate recognition card
        List<String> filterSummary = new ArrayList<>();
        filterSummary.add("品类：" + category);
        filterSummary.add("识别品牌：" + brand);
        filterSummary.add("识别型号：Mock 型号");
        filterSummary.add("置信度：82%");
        Card pgCard = Card.productGroupList("匹配商品", groups, filterSummary, emptyReason);
        // Carry recognition metadata on the product_group_list card for detail-page use
        pgCard = pgCard.withRecognitionMeta(
                imageIds.get(0), category, brand, "Mock 型号",
                List.of("运动鞋", "白色", "跑步鞋"), Map.of("color", "白色", "style", "通勤运动鞋"),
                0.82, "mock", false, "当前为演示识别结果。", null);

        return new AgentReply(UUID.randomUUID().toString(), "product_recommendation",
                "我已经识别了你的商品图片。你更看重哪一点？",
                List.of(pgCard, buildSuggestionCard(category, null)));
    }

    private AgentReply buildRecognitionReplyWithResult(RecognitionResult rec) {
        String category = CategoryResolver.defaultResolver().resolveName(rec.getCategory());
        if (category == null) category = rec.getCategory();
        // Search by category only — recognized brand goes into filterSummary/metadata,
        // not as a hard filter, to avoid empty results when mock data lacks the brand.
        List<ProductGroup> groups = quickSearchGroups(category, null, null, null);
        String emptyReason = groups.isEmpty() ? "当前数据中暂无「" + category + "」商品。" : null;

        // Merge recognition info into filterSummary — no separate recognition card
        List<String> filterSummary = new ArrayList<>();
        filterSummary.add("品类：" + (category != null ? category : rec.getCategory()));
        if (rec.getBrand() != null && !rec.getBrand().isBlank())
            filterSummary.add("识别品牌：" + rec.getBrand());
        if (rec.getModel() != null && !rec.getModel().isBlank())
            filterSummary.add("识别型号：" + rec.getModel());
        if (rec.getConfidence() > 0)
            filterSummary.add("置信度：" + Math.round(rec.getConfidence() * 100) + "%");

        Card pgCard = Card.productGroupList("匹配商品", groups, filterSummary, emptyReason);
        pgCard = pgCard.withRecognitionMeta(
                rec.getImageId(), rec.getCategory(), rec.getBrand(), rec.getModel(),
                rec.getKeywords(), rec.getAttributes(),
                rec.getConfidence(), rec.getAiProvider(), rec.isFallbackUsed(),
                rec.getExplanation(), rec.getRecognitionId());

        return new AgentReply(UUID.randomUUID().toString(), "product_recommendation",
                "我已经识别了你的商品图片。你更看重哪一点？",
                List.of(pgCard, buildSuggestionCard(rec.getCategory(), rec.getBrand())));
    }

    private AgentReply buildClarification(String category) {
        // Also provide product_group_list for non-shopping text
        String keyword = category != null ? category : "运动鞋";
        List<ProductGroup> groups = quickSearchGroups(keyword, null, null, null);
        String emptyReason = groups.isEmpty() ? "请输入你想要的商品关键词以开始搜索。" : null;
        List<String> filterSummary = List.of("品类：" + keyword);
        Card pgCard = Card.productGroupList("匹配商品", groups, filterSummary, emptyReason);

        return new AgentReply(UUID.randomUUID().toString(), "clarification",
                "我已经收到你的需求。你更看重哪一点？",
                List.of(pgCard, buildSuggestionCard(category, null)));
    }

    /**
     * Quick product search and grouping helper for non-product-recommendation flows.
     */
    private List<ProductGroup> quickSearchGroups(String keyword, String brand,
                                                  Double maxPrice, String sortBy) {
        ProductSearchResult sr = productSource.search(
                new ProductSearchQuery(keyword, List.of(), maxPrice, null,
                        brand, List.of(), sortBy, null));
        ShoppingIntent dummyIntent = new ShoppingIntent(keyword, maxPrice, null,
                false, false, false, false, false,
                brand, List.of(), sortBy, null,
                false, null, "mock", false, List.of());
        return groupProducts(sr.products(), dummyIntent, sr);
    }

    /**
     * Build a dynamic suggestion card whose options vary by recognized category and brand.
     */
    private Card buildSuggestionCard(String category, String brand) {
        List<Option> options = new ArrayList<>();
        options.add(new Option("lowest_price", "查看同款低价"));
        options.add(new Option("official_store", "只看官方旗舰店"));
        options.add(new Option("fast_delivery", "配送更快"));

        String normalizedCategory = CategoryResolver.defaultResolver().resolveName(category);
        if (normalizedCategory != null) {
            switch (normalizedCategory) {
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
                null, null, null);
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
            List<String> filterSummary,
            List<ProductGroup> groups,
            String emptyReason) {

        public static Card clarification(String title) {
            return new Card("clarification", title, null, null, null, null,
                    List.of(new Option("lowest_price", "价格最低"),
                            new Option("official_store", "官方店铺"),
                            new Option("fast_delivery", "配送更快")),
                    null, null, null, null, null, null,
                    0.0, null, false, null, null, null, null,
                    null, null, null, null, null,
                    null, null, null, null, null,
                    null, null, null);
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
                    null, null, null);
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
                    null, null, null);
        }

        public static Card productList(String title, List<ProductOffer> products,
                                       List<String> filterSummary) {
            return new Card("product_list", title, null, null, null, null, null,
                    null, null, null, null, null, null,
                    0.0, null, false, null, null, products, null,
                    null, null, null, null, null,
                    null, null, null, null, null,
                    filterSummary, null, null);
        }

        public static Card comparison(String title,
                                      Map<String, ProductSearchResult.PlatformStats> stats) {
            return new Card("comparison", title, null, null, null, null, null,
                    null, null, null, null, null, null,
                    0.0, null, false, null, null, null, stats,
                    null, null, null, null, null,
                    null, null, null, null, null,
                    null, null, null);
        }

        public static Card productGroupList(String title, List<ProductGroup> groups,
                                            List<String> filterSummary, String emptyReason) {
            return new Card("product_group_list", title, null, null, null, null, null,
                    null, null, null, null, null, null,
                    0.0, null, false, null, null, null, null,
                    null, null, null, null, null,
                    null, null, null, null, null,
                    filterSummary, groups, emptyReason);
        }

        /**
         * Returns a copy of this card with recognition metadata fields populated.
         * Used when a product_group_list card also carries image recognition info
         * (so the frontend can show recognition details without a separate card).
         */
        public Card withRecognitionMeta(String imageId, String category, String brand,
                                         String model, List<String> keywords,
                                         Map<String, Object> attributes, double confidence,
                                         String aiProvider, boolean fallbackUsed,
                                         String explanation, String recognitionId) {
            return new Card(this.cardType, this.title,
                    this.productName, this.platform, this.price, this.reason,
                    this.options,
                    imageId, category, brand, model, keywords, attributes,
                    confidence, aiProvider, fallbackUsed, explanation, recognitionId,
                    this.products, this.platformStats,
                    this.decisionScore, this.decisionSignals, this.evidence, this.risks,
                    this.productAnalyses,
                    this.intentProvider, this.intentFallbackUsed,
                    this.explanationProvider, this.explanationFallbackUsed,
                    this.notices,
                    this.filterSummary, this.groups, this.emptyReason);
        }
    }

    public record Option(String optionId, String label) {}

    public record ProductGroup(
            String groupId,
            String sameItemKey,
            String displayTitle,
            String category,
            String brand,
            String thumbnailUrl,
            double bestPrice,
            double originalPrice,
            PriceRange priceRange,
            int platformCount,
            List<PlatformOfferSummary> platforms,
            List<String> highlights,
            String matchLevel
    ) {}

    public record PriceRange(double min, double max) {}

    public record PlatformOfferSummary(
            String productId,
            String platform,
            double price,
            double originalPrice,
            String shopName,
            String productUrl,
            double rating,
            int sales,
            List<String> tags,
            List<String> reasons,
            double score,
            String title,
            String imageUrl,
            String brand,
            List<Double> priceHistory,
            List<String> matchedPreferences,
            List<ProductSpec> specs
    ) {}

    public record ProductSpec(String label, String value) {}
}
