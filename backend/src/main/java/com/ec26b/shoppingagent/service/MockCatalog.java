package com.ec26b.shoppingagent.service;

import com.ec26b.shoppingagent.api.ApiException;
import com.ec26b.shoppingagent.api.ApiModels.Money;
import com.ec26b.shoppingagent.api.ApiModels.PlatformProductDto;
import com.ec26b.shoppingagent.api.ApiModels.ProductDto;
import com.ec26b.shoppingagent.api.ApiModels.ReviewSummaryDto;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.OffsetDateTime;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.function.Function;
import java.util.stream.Collectors;

@Component
public class MockCatalog {
    private final List<ProductData> products;
    private final List<PlatformProductData> platformProducts;
    private final List<RecognitionSample> recognitions;
    private final Map<Long, PriceHistoryData> priceHistories;
    private final Map<Long, ReviewSummaryData> reviewSummaries;
    private final Map<Long, ProductData> productsById;
    private final Map<Long, PlatformProductData> platformProductsById;

    public MockCatalog(ObjectMapper objectMapper, @Value("${app.mock-data-dir}") String mockDataDir) {
        Path root = resolveMockDataPath(mockDataDir);
        this.products = read(objectMapper, root.resolve("products.json"), new TypeReference<>() {
        });
        this.platformProducts = read(objectMapper, root.resolve("platform-products.json"), new TypeReference<>() {
        });
        this.recognitions = read(objectMapper, root.resolve("recognitions.json"), new TypeReference<>() {
        });
        List<PriceHistoryData> histories = read(objectMapper, root.resolve("price-history.json"), new TypeReference<>() {
        });
        List<ReviewSummaryData> summaries = read(objectMapper, root.resolve("review-summaries.json"), new TypeReference<>() {
        });
        this.priceHistories = histories.stream().collect(Collectors.toMap(PriceHistoryData::platformProductId, Function.identity()));
        this.reviewSummaries = summaries.stream().collect(Collectors.toMap(ReviewSummaryData::platformProductId, Function.identity()));
        this.productsById = products.stream().collect(Collectors.toMap(ProductData::productId, Function.identity()));
        this.platformProductsById = platformProducts.stream().collect(Collectors.toMap(PlatformProductData::platformProductId, Function.identity()));
    }

    public List<ProductData> products() {
        return products;
    }

    public List<PlatformProductData> platformProducts() {
        return platformProducts;
    }

    public ProductData product(long productId) {
        ProductData product = productsById.get(productId);
        if (product == null) {
            throw ApiException.notFound(40404, "product not found");
        }
        return product;
    }

    public PlatformProductData platformProduct(long platformProductId) {
        PlatformProductData product = platformProductsById.get(platformProductId);
        if (product == null) {
            throw ApiException.notFound(40405, "platform product not found");
        }
        return product;
    }

    public Optional<ReviewSummaryData> reviewSummary(long platformProductId) {
        return Optional.ofNullable(reviewSummaries.get(platformProductId));
    }

    public Optional<PriceHistoryData> priceHistory(long platformProductId) {
        return Optional.ofNullable(priceHistories.get(platformProductId));
    }

    public RecognitionSample recognitionSampleFor(String imageUrl, long fallbackId) {
        String normalized = imageUrl == null ? "" : imageUrl.toLowerCase();
        for (RecognitionSample sample : recognitions) {
            String name = sample.mockImageName().toLowerCase();
            String stem = name.replace(".jpg", "").replace(".png", "");
            if (normalized.contains(name) || normalized.contains(stem)) {
                return sample;
            }
        }
        int index = (int) Math.abs(fallbackId % recognitions.size());
        return recognitions.get(index);
    }

    public ProductDto toProductDto(ProductData product) {
        return new ProductDto(
                product.productId(),
                product.name(),
                product.category(),
                product.brand(),
                product.model(),
                product.attributes(),
                OffsetDateTime.now()
        );
    }

    public PlatformProductDto toPlatformProductDto(PlatformProductData product) {
        return new PlatformProductDto(
                product.platformProductId(),
                product.productId(),
                product.platform(),
                product.title(),
                product.imageUrl(),
                product.price(),
                product.originalPrice(),
                product.url(),
                product.shopName(),
                safeList(product.tags()),
                product.salesVolume(),
                product.rating(),
                product.isOfficial(),
                product.isSelfOperated(),
                normalizeSourceType(product.sourceType()),
                OffsetDateTime.now()
        );
    }

    public ReviewSummaryDto toReviewSummaryDto(long platformProductId) {
        ReviewSummaryData summary = reviewSummaries.get(platformProductId);
        if (summary == null) {
            return new ReviewSummaryDto(platformProductId, null, 0, List.of(), List.of(), 0.5, "暂无评价摘要，已使用中性风险兜底。");
        }
        return new ReviewSummaryDto(
                summary.platformProductId(),
                summary.rating(),
                summary.reviewCount(),
                safeList(summary.positiveTags()),
                safeList(summary.riskTags()),
                summary.riskScore(),
                summary.summary()
        );
    }

    public BigDecimal amount(Money money) {
        return new BigDecimal(money.amount());
    }

    private Path resolveMockDataPath(String configured) {
        Path path = Path.of(configured);
        if (path.isAbsolute() && Files.exists(path)) {
            return path;
        }
        Path cwd = Path.of("").toAbsolutePath();
        List<Path> candidates = List.of(
                cwd.resolve(configured),
                cwd.resolve("..").resolve(configured).normalize(),
                cwd.resolve("..").resolve("..").resolve(configured).normalize()
        );
        return candidates.stream()
                .filter(Files::exists)
                .findFirst()
                .orElseThrow(() -> new ApiException(50003, "mock data directory not found: " + configured, HttpStatus.INTERNAL_SERVER_ERROR));
    }

    private <T> T read(ObjectMapper mapper, Path path, TypeReference<T> type) {
        try {
            return mapper.readValue(path.toFile(), type);
        } catch (IOException ex) {
            throw new ApiException(50003, "failed to read mock data: " + path, HttpStatus.INTERNAL_SERVER_ERROR);
        }
    }

    private <T> List<T> safeList(List<T> value) {
        return value == null ? List.of() : value;
    }

    public String normalizeSourceType(String sourceType) {
        if (sourceType == null || sourceType.isBlank()) {
            return "mock";
        }
        return sourceType;
    }

    public List<PlatformProductData> candidatesSortedByPrice(List<Long> ids) {
        return ids.stream()
                .map(this::platformProduct)
                .sorted(Comparator.comparing(item -> amount(item.price())))
                .toList();
    }

    public record ProductData(
            long productId,
            String name,
            String category,
            String brand,
            String model,
            Map<String, Object> attributes
    ) {
    }

    public record PlatformProductData(
            long platformProductId,
            long productId,
            String platform,
            String title,
            String imageUrl,
            Money price,
            Money originalPrice,
            String url,
            String shopName,
            String sourceType,
            List<String> tags,
            int salesVolume,
            double rating,
            boolean isOfficial,
            boolean isSelfOperated
    ) {
    }

    public record RecognitionSample(
            String mockImageName,
            String category,
            String brand,
            String model,
            List<String> keywords,
            Map<String, Object> attributes,
            double confidence
    ) {
    }

    public record PriceHistoryData(long platformProductId, List<PricePointData> points) {
    }

    public record PricePointData(OffsetDateTime recordedAt, Money price) {
    }

    public record ReviewSummaryData(
            long platformProductId,
            Double rating,
            Integer reviewCount,
            List<String> positiveTags,
            List<String> riskTags,
            double riskScore,
            String summary
    ) {
    }
}
