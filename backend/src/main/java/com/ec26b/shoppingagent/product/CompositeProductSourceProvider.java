package com.ec26b.shoppingagent.product;

import com.ec26b.shoppingagent.ai.ArkClient;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Primary;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;
import java.util.stream.Collectors;

/**
 * Primary product source with configurable dataset mode.
 */
@Primary
@Component
public class CompositeProductSourceProvider implements ProductSourceProvider {

    static final List<String> DOMESTIC_PLATFORMS = List.of(
            "拼多多-mock", "淘宝-mock", "天猫-mock", "京东-mock"
    );

    private static final Map<String, PlatformProfile> PLATFORM_PROFILES = Map.of(
            "拼多多-mock", new PlatformProfile("拼多多", 0.82, 0.92, "品牌店",
                    List.of("包邮", "先用后付"), "48h内发货", "放心退"),
            "淘宝-mock", new PlatformProfile("淘宝", 0.92, 1.02, "运动装备店",
                    List.of("包邮", "运费险"), "浙江发货", "7天无理由"),
            "天猫-mock", new PlatformProfile("天猫", 0.96, 1.06, "官方旗舰店",
                    List.of("包邮", "正品保障"), "菜鸟配送", "7天无理由"),
            "京东-mock", new PlatformProfile("京东", 0.98, 1.10, "自营旗舰店",
                    List.of("京东物流", "正品保障"), "京仓发货", "上门换新")
    );

    private final List<MockProduct> catalog;
    private final ResultReRanker reRanker;
    private final ArkQueryDecomposer queryDecomposer;
    private final HybridRetriever hybridRetriever;
    private final PublicDatasetProductSourceProvider publicDataset;
    private final String mode;

    /**
     * Primary constructor — used by Spring with injected {@link RecommendationScorer}.
     */
    @Autowired
    public CompositeProductSourceProvider(ObjectMapper objectMapper,
                                          @Value("${app.product-source.mock-resource:mock-data/mock-data.json}")
                                          String resourcePath,
                                          @Value("${app.product-source.public-resource:data/public-product-offers.json}")
                                          String publicResourcePath,
                                          @Value("${app.product-source.mode:public-dataset}")
                                          String mode,
                                          ArkClient arkClient,
                                          RecommendationScorer scorer) {
        this.catalog = loadCatalog(objectMapper, resourcePath);
        this.queryDecomposer = new ArkQueryDecomposer(arkClient);
        this.reRanker = new ResultReRanker(scorer);
        this.publicDataset = new PublicDatasetProductSourceProvider(
                scorer, objectMapper, publicResourcePath);
        this.mode = mode == null || mode.isBlank() ? "public-dataset" : mode.trim();

        // Build product maps for hybrid retrieval
        List<Map<String, String>> productMaps = catalog.stream()
                .map(p -> Map.of("productId", p.productId, "title", p.title,
                        "brand", p.brand, "category", p.category))
                .toList();
        this.hybridRetriever = new HybridRetriever(productMaps, arkClient);
    }

    public CompositeProductSourceProvider(ObjectMapper objectMapper,
                                          String resourcePath,
                                          ArkClient arkClient,
                                          RecommendationScorer scorer) {
        this(objectMapper, resourcePath, "data/public-product-offers.json",
                "mock-data", arkClient, scorer);
    }

    // ── Search ─────────────────────────────────────────────────

    @Override
    public ProductSearchResult search(ProductSearchQuery query) {
        String normalizedMode = mode.toLowerCase(Locale.ROOT);
        if ("mock".equals(normalizedMode) || "mock-data".equals(normalizedMode)) {
            return searchMockData(query);
        }
        if ("public-dataset-only".equals(normalizedMode)) {
            return publicDataset.search(query);
        }
        if ("public-dataset-platforms".equals(normalizedMode)) {
            return publicDataset.searchWithPlatformVariants(query, DOMESTIC_PLATFORMS);
        }

        ProductSearchResult publicResult = publicDataset.search(query);
        ProductSearchResult mockResult = searchMockData(query);
        List<ProductOffer> products = new ArrayList<>();
        products.addAll(publicResult.products());
        products.addAll(mockResult.products());
        return ProductSearchResults.fromProducts(products, query.sortBy());
    }

    private ProductSearchResult searchMockData(ProductSearchQuery query) {
        String rawQuery = query.keyword();

        // === RAG Stage 1: Query Decomposition (LLM + rule fallback) ===
        ArkQueryDecomposer.DecomposedQuery decomposed = queryDecomposer.decompose(rawQuery);

        String category = decomposed.hasCategory()
                ? decomposed.category()
                : CategoryResolver.defaultResolver().resolveName(rawQuery);

        // Build search text from decomposed query
        String searchText = buildSearchText(decomposed, rawQuery);

        // === RAG Stage 2: Hybrid Retrieval (vector + BM25 + LLM) ===
        Map<String, String> productTexts = catalog.stream()
                .filter(p -> category == null || category.equals(p.category))
                .filter(p -> matchesBrand(query.brand(), p))
                .collect(Collectors.toMap(p -> p.productId,
                        p -> p.title + " " + p.brand + " " + p.category));

        List<HybridRetriever.ScoredProduct> retrieved = hybridRetriever.retrieve(
                decomposed, productTexts, Math.min(catalog.size(), 30));

        // Map retrieved product IDs back to MockProducts
        Map<String, MockProduct> productById = catalog.stream()
                .collect(Collectors.toMap(p -> p.productId, p -> p));

        // === RAG Stage 3: Build offers for top retrieved products ===
        List<ProductOffer> offers = new ArrayList<>();
        List<String> allowedPlatforms = resolveAllowedPlatforms(query);
        Set<String> seen = new LinkedHashSet<>();

        for (HybridRetriever.ScoredProduct sp : retrieved) {
            MockProduct p = productById.get(sp.productId());
            if (p == null) continue;
            if (category != null && !category.equals(p.category)) continue;

            String sameItemKey = p.brand + "|" + p.category;
            for (String plat : allowedPlatforms) {
                ProductOffer offer = buildOffer(p, plat, sameItemKey, query);
                if (offer != null && seen.add(offer.productId())) {
                    offer = applyProfileWeight(offer, query.profile());
                    offers.add(offer);
                }
            }
        }

        // Fallback: if no results from hybrid retrieval, use category-only matching
        if (offers.isEmpty()) {
            for (MockProduct p : catalog) {
                if (category != null && !category.equals(p.category)) continue;
                if (!matchesBrand(query.brand(), p)) continue;
                String sameItemKey = p.brand + "|" + p.category;
                for (String plat : allowedPlatforms) {
                    ProductOffer offer = buildOffer(p, plat, sameItemKey, query);
                    if (offer != null) {
                        offer = applyProfileWeight(offer, query.profile());
                        offers.add(offer);
                    }
                }
            }
        }

        // === RAG Stage 4: Re-ranking (multi-factor + diversity) ===
        List<ProductOffer> reranked = reRanker.rerank(offers, searchText, query.profile());

        return ProductSearchResults.fromProducts(reranked, query.sortBy());
    }

    private String buildSearchText(ArkQueryDecomposer.DecomposedQuery dq, String fallback) {
        StringBuilder sb = new StringBuilder();
        if (dq.hasCategory()) sb.append(dq.category()).append(" ");
        sb.append(fallback != null ? fallback : dq.originalText()).append(" ");
        if (dq.hasExpansions()) sb.append(String.join(" ", dq.expandedKeywords()));
        return sb.toString();
    }

    /**
     * Adjust offer score based on user profile preferences.
     * Matching preferences get a small boost; dislikes get a penalty.
     * Score adjustments are small (0.3–0.5) so search intent remains primary.
     */
    @SuppressWarnings("unchecked")
    private ProductOffer applyProfileWeight(ProductOffer offer, Map<String, Object> profile) {
        if (profile == null || profile.isEmpty()) return offer;

        double boost = 0.0;
        List<String> newReasons = new ArrayList<>(offer.reasons());

        // Preferred platforms
        List<String> prefPlatforms = (List<String>) profile.get("preferredPlatforms");
        if (prefPlatforms != null && prefPlatforms.contains(platformLabel(offer.platform()))) {
            boost += 0.5;
        }

        // Inferred brands
        List<String> inferredBrands = (List<String>) profile.get("inferredBrands");
        if (inferredBrands != null && offer.brand() != null
                && inferredBrands.contains(offer.brand())) {
            boost += 0.5;
            if (newReasons.size() < 2) newReasons.add("你最近关注过这个品牌");
        }

        // Price range match
        Object priceMin = profile.get("inferredPriceMin");
        Object priceMax = profile.get("inferredPriceMax");
        if (priceMin instanceof Number && priceMax instanceof Number) {
            double min = ((Number) priceMin).doubleValue();
            double max = ((Number) priceMax).doubleValue();
            if (offer.price() >= min && offer.price() <= max) {
                boost += 0.5;
                if (newReasons.size() < 2) newReasons.add("价格在你常看的区间内");
            }
        }

        // Preferred categories
        List<String> prefCats = (List<String>) profile.get("preferredCategories");
        if (prefCats != null && offer.sameItemKey() != null) {
            for (String cat : prefCats) {
                if (offer.sameItemKey().contains(cat)) {
                    boost += 0.3;
                    break;
                }
            }
        }

        // Dislikes — small penalty
        List<String> dislikes = (List<String>) profile.get("dislikes");
        if (dislikes != null) {
            if (dislikes.contains("non_official") && offer.tags().stream()
                    .noneMatch(t -> t.contains("自营") || t.contains("官方") || t.contains("旗舰"))) {
                boost -= 1.0;
            }
            if (dislikes.contains("high_price") && offer.price() > 500) {
                boost -= 0.5;
            }
        }

        if (boost == 0.0) return offer;
        return offer.withScoringResult(offer.score() + boost, newReasons,
                offer.matchedPreferences());
    }

    /** Map internal platform key to display label. */
    private static String platformLabel(String platform) {
        return switch (platform) {
            case "京东-mock" -> "京东";
            case "拼多多-mock" -> "拼多多";
            case "淘宝-mock" -> "淘宝";
            case "天猫-mock" -> "天猫";
            default -> platform;
        };
    }

    @Override
    public String sourceName() {
        String normalizedMode = mode.toLowerCase(Locale.ROOT);
        if ("mock".equals(normalizedMode) || "mock-data".equals(normalizedMode)) {
            return "mock-data";
        }
        if ("public-dataset-only".equals(normalizedMode)) {
            return publicDataset.sourceName();
        }
        if ("public-dataset-platforms".equals(normalizedMode)) {
            return "public-dataset-platforms";
        }
        return "public-dataset+mock-data";
    }

    // ── Filters ────────────────────────────────────────────────

    private boolean matchesBrand(String queryBrand, MockProduct p) {
        return queryBrand == null || queryBrand.isBlank()
                || queryBrand.equals(p.brand)
                || (p.title != null && p.title.contains(queryBrand));
    }

    private List<String> resolveAllowedPlatforms(ProductSearchQuery query) {
        List<String> qp = query.platforms();
        if (qp == null || qp.isEmpty()) return DOMESTIC_PLATFORMS;
        List<String> allowed = new ArrayList<>();
        for (String p : DOMESTIC_PLATFORMS) {
            if (qp.contains(p)) allowed.add(p);
        }
        return allowed;
    }

    // ── Offer builder ──────────────────────────────────────────

    private ProductOffer buildOffer(MockProduct p, String platform, String sameItemKey,
                                     ProductSearchQuery query) {
        PlatformProfile profile = PLATFORM_PROFILES.get(platform);
        if (profile == null) return null;

        int hash = Math.abs((p.productId + platform).hashCode());

        // Price: deterministic within platform range
        double price = Math.round(p.basePrice * profile.priceMin
                + (hash % (int)(p.basePrice * (profile.priceMax - profile.priceMin))));
        price = Math.max(p.basePrice * 0.6, price);
        price = Math.round(price);
        if (query.maxPrice() != null && price > query.maxPrice()) return null;

        double origPrice = price > p.basePrice * 0.85
                ? Math.round(price * 1.2 / 10.0) * 10.0
                : Math.round(p.basePrice * 1.25 / 10.0) * 10.0;

        // Rating respecting minRating filter
        double minRating = query.minRating() != null && query.minRating() > 0
                ? query.minRating() : 4.2;
        double rating = minRating + (hash % (int)((5.0 - minRating) * 10 + 1)) * 0.1;
        rating = Math.max(minRating, Math.min(5.0, Math.round(rating * 10.0) / 10.0));

        int sales = 200 + (hash % 9800);
        String shopName = p.brand + profile.shopSuffix;
        String variantId = p.productId + "_" + platform.replace("-mock", "");

        List<String> tags = new ArrayList<>(profile.tags);
        if (price < origPrice * 0.75) tags.add("券后价");

        List<Double> priceHistory = generatePriceHistory(price, origPrice);

        return new ProductOffer(
                variantId, p.title, platform, price, origPrice,
                shopName, p.imageUrl, "",
                rating, sales, tags, List.of(), 0,
                p.brand, priceHistory, List.of(), sameItemKey
        );
    }

    private static List<Double> generatePriceHistory(double price, double origPrice) {
        double high = Math.max(price, origPrice);
        return List.of(
                Math.round(high * 100.0) / 100.0,
                Math.round(high * 0.95 * 100.0) / 100.0,
                Math.round((high + price) / 2.0 * 100.0) / 100.0,
                Math.round(price * 1.08 * 100.0) / 100.0,
                Math.round(price * 100.0) / 100.0
        );
    }

    // ── Data loading ───────────────────────────────────────────

    private static List<MockProduct> loadCatalog(ObjectMapper objectMapper, String resourcePath) {
        Path path = Path.of(resourcePath);
        if (!Files.exists(path)) {
            path = Path.of("..", resourcePath);
        }
        try {
            MockDataFile file = objectMapper.readValue(path.toFile(), MockDataFile.class);
            return file.products() == null ? List.of() : List.copyOf(file.products());
        } catch (IOException ex) {
            throw new IllegalStateException(
                    "Failed to load mock product data: " + resourcePath, ex);
        }
    }

    // ── DTOs ───────────────────────────────────────────────────

    private record MockDataFile(String description, List<MockProduct> products) {}

    private record MockProduct(
            String productId, String category, String title, String brand,
            String imageUrl, List<String> platforms, double basePrice
    ) {}

    private record PlatformProfile(
            String displayName, double priceMin, double priceMax, String shopSuffix,
            List<String> tags, String shipping, String afterSale
    ) {}
}
