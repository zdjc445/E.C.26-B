package com.ec26b.shoppingagent.product;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;

@Component
public class PublicDatasetProductSourceProvider implements ProductSourceProvider {

    public static final String PLATFORM = "Flipkart-sample";

    private final RecommendationScorer scorer;
    private final List<CatalogProduct> catalog;

    public PublicDatasetProductSourceProvider(RecommendationScorer scorer,
                                              ObjectMapper objectMapper,
                                              @Value("${app.product-source.public-resource:data/public-product-offers.json}")
                                              String resourcePath) {
        this.scorer = scorer;
        this.catalog = loadCatalog(objectMapper, resourcePath);
    }

    @Override
    public ProductSearchResult search(ProductSearchQuery query) {
        String category = CategoryResolver.defaultResolver().resolveName(query.keyword());
        if (category == null) {
            return new ProductSearchResult(List.of(), java.util.Map.of(), null);
        }

        UserPreference pref = new UserPreference(query.maxPrice(), query.color(),
                false, false, false, false, false,
                query.brand(), query.platforms(), query.sortBy(), query.minRating());
        List<String> prefs = query.preferences() != null ? query.preferences() : List.of();

        List<ProductOffer> filtered = catalog.stream()
                .filter(p -> category.equals(p.category()))
                .filter(p -> platformMatches(query.platforms()))
                .map(CatalogProduct::toProductOffer)
                .map(p -> scorer.scoreProduct(p, prefs, query.maxPrice(), pref))
                .filter(p -> query.maxPrice() == null || p.price() <= query.maxPrice())
                .filter(p -> matchesTextFilter(query.color(), p))
                .filter(p -> matchesBrand(query.brand(), p))
                .filter(p -> query.minRating() == null || p.rating() >= query.minRating())
                .toList();

        return ProductSearchResults.fromProducts(filtered, query.sortBy());
    }

    public ProductSearchResult searchWithPlatformVariants(ProductSearchQuery query,
                                                          List<String> platforms) {
        String category = CategoryResolver.defaultResolver().resolveName(query.keyword());
        if (category == null) {
            return new ProductSearchResult(List.of(), java.util.Map.of(), null);
        }

        UserPreference pref = new UserPreference(query.maxPrice(), query.color(),
                false, false, false, false, false,
                query.brand(), query.platforms(), query.sortBy(), query.minRating());
        List<String> prefs = query.preferences() != null ? query.preferences() : List.of();
        List<String> allowedPlatforms = resolvePlatforms(query.platforms(), platforms);

        List<ProductOffer> filtered = catalog.stream()
                .filter(p -> category.equals(p.category()))
                .flatMap(p -> allowedPlatforms.stream()
                        .map(platform -> p.toPlatformOffer(platform)))
                .map(p -> scorer.scoreProduct(p, prefs, query.maxPrice(), pref))
                .filter(p -> query.maxPrice() == null || p.price() <= query.maxPrice())
                .filter(p -> matchesTextFilter(query.color(), p))
                .filter(p -> matchesBrand(query.brand(), p))
                .filter(p -> query.minRating() == null || p.rating() >= query.minRating())
                .toList();

        return ProductSearchResults.fromProducts(filtered, query.sortBy());
    }

    @Override
    public String sourceName() {
        return "public-dataset";
    }

    private boolean platformMatches(List<String> platforms) {
        return platforms == null || platforms.isEmpty() || platforms.contains(PLATFORM);
    }

    private List<String> resolvePlatforms(List<String> requestedPlatforms,
                                          List<String> supportedPlatforms) {
        List<String> supported = supportedPlatforms == null ? List.of() : supportedPlatforms;
        if (requestedPlatforms == null || requestedPlatforms.isEmpty()) {
            return supported;
        }
        List<String> resolved = new ArrayList<>();
        for (String platform : supported) {
            if (requestedPlatforms.contains(platform)) {
                resolved.add(platform);
            }
        }
        return resolved;
    }

    private boolean matchesTextFilter(String value, ProductOffer product) {
        if (value == null || value.isBlank()) {
            return true;
        }
        return product.title().contains(value)
                || product.tags().stream().anyMatch(t -> t.contains(value));
    }

    private boolean matchesBrand(String brand, ProductOffer product) {
        if (brand == null || brand.isBlank()) {
            return true;
        }
        return brand.equalsIgnoreCase(product.brand())
                || (product.title() != null && product.title().contains(brand));
    }

    private static List<CatalogProduct> loadCatalog(ObjectMapper objectMapper, String resourcePath) {
        try (InputStream in = new ClassPathResource(resourcePath).getInputStream()) {
            CatalogFile file = objectMapper.readValue(in, CatalogFile.class);
            return file.products() == null ? List.of() : List.copyOf(file.products());
        } catch (IOException ex) {
            throw new IllegalStateException(
                    "Failed to load public product dataset resource: " + resourcePath, ex);
        }
    }

    private record CatalogFile(SourceInfo source, List<CatalogProduct> products) {
    }

    private record SourceInfo(String name, String url, String file) {
    }

    private record CatalogProduct(
            String productId,
            String category,
            String title,
            String platform,
            double price,
            double originalPrice,
            String shopName,
            String imageUrl,
            String productUrl,
            double rating,
            int sales,
            String brand,
            List<String> tags,
            String sourceCategory,
            String rawRating
    ) {
        ProductOffer toProductOffer() {
            return new ProductOffer(productId, title, platform, price, originalPrice,
                    shopName, imageUrl, productUrl, rating, sales,
                    tags == null ? List.of() : tags, List.of(), 0, brand);
        }

        ProductOffer toPlatformOffer(String targetPlatform) {
            int hash = Math.abs((productId + targetPlatform).hashCode());
            double platformPrice = round(price * platformFactor(targetPlatform) + (hash % 17) - 8);
            platformPrice = Math.max(1, platformPrice);
            double platformOriginal = originalPrice > 0
                    ? round(originalPrice * platformFactor(targetPlatform))
                    : round(platformPrice * 1.15);
            String platformShop = platformLabel(targetPlatform) + "样例店";
            List<String> mergedTags = new ArrayList<>(tags == null ? List.of() : tags);
            mergedTags.add(platformLabel(targetPlatform));

            return new ProductOffer(
                    productId + "_" + targetPlatform.replace("-mock", ""),
                    title,
                    targetPlatform,
                    platformPrice,
                    platformOriginal,
                    platformShop,
                    imageUrl,
                    productUrl,
                    rating,
                    sales,
                    mergedTags,
                    List.of(),
                    0,
                    brand,
                    defaultPriceHistory(platformPrice, platformOriginal),
                    List.of(),
                    productId
            );
        }
    }

    private static double platformFactor(String platform) {
        return switch (platform) {
            case "拼多多-mock" -> 0.90;
            case "淘宝-mock" -> 0.96;
            case "天猫-mock" -> 1.00;
            case "京东-mock" -> 1.03;
            default -> 1.00;
        };
    }

    private static String platformLabel(String platform) {
        return switch (platform) {
            case "京东-mock" -> "京东";
            case "拼多多-mock" -> "拼多多";
            case "淘宝-mock" -> "淘宝";
            case "天猫-mock" -> "天猫";
            default -> platform;
        };
    }

    private static double round(double v) {
        return Math.round(v * 100.0) / 100.0;
    }

    private static List<Double> defaultPriceHistory(double price, double originalPrice) {
        if (price <= 0) return List.of();
        double base = originalPrice > price ? originalPrice : price * 1.15;
        return List.of(
                round(base),
                round(base * 0.97),
                round((base + price) / 2.0),
                round(price * 1.05),
                round(price)
        );
    }
}
