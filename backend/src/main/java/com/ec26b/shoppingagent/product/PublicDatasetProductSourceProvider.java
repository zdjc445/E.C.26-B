package com.ec26b.shoppingagent.product;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.io.InputStream;
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

    @Override
    public String sourceName() {
        return "public-dataset";
    }

    private boolean platformMatches(List<String> platforms) {
        return platforms == null || platforms.isEmpty() || platforms.contains(PLATFORM);
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
            throw new IllegalStateException("Failed to load public product dataset resource: " + resourcePath, ex);
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
    }
}
