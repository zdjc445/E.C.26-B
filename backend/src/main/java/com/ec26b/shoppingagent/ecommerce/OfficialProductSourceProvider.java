package com.ec26b.shoppingagent.ecommerce;

import com.ec26b.shoppingagent.api.ApiException;
import com.ec26b.shoppingagent.api.ApiModels.EcommerceDiagnosticsPayload;
import com.ec26b.shoppingagent.api.ApiModels.EcommerceProviderDiagnostic;
import com.ec26b.shoppingagent.api.ApiModels.EcommerceProviderStatus;
import com.ec26b.shoppingagent.api.ApiModels.EcommerceStatusPayload;
import com.ec26b.shoppingagent.service.MockCatalog;
import org.springframework.stereotype.Component;

import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

@Component
public class OfficialProductSourceProvider {
    private static final List<String> SORT_MODES = List.of("comprehensive", "price_asc", "sales_desc", "rating_desc");

    private final List<OfficialApiClient> clients;
    private final EcommerceApiProperties properties;
    private final Map<Long, MockCatalog.ProductData> products = new ConcurrentHashMap<>();
    private final Map<Long, MockCatalog.PlatformProductData> platformProducts = new ConcurrentHashMap<>();
    private final Map<Long, MockCatalog.ReviewSummaryData> reviewSummaries = new ConcurrentHashMap<>();
    private final Map<Long, MockCatalog.PriceHistoryData> priceHistories = new ConcurrentHashMap<>();

    public OfficialProductSourceProvider(List<OfficialApiClient> clients, EcommerceApiProperties properties) {
        this.clients = clients;
        this.properties = properties;
    }

    public List<MockCatalog.PlatformProductData> search(ProductSourceQuery query) {
        List<String> failures = new ArrayList<>();
        List<OfficialProductResult> results = new ArrayList<>();
        int attempted = 0;
        for (OfficialApiClient client : clientsFor(query.platforms())) {
            if (!client.configured()) {
                continue;
            }
            attempted++;
            try {
                results.addAll(client.search(query));
            } catch (RuntimeException ex) {
                failures.add(client.platform() + ": " + ex.getMessage());
            }
        }
        if (attempted == 0 && !normalizePlatforms(query.platforms()).isEmpty()) {
            throw ApiException.badRequest("official_api not configured for selected platforms: " + String.join(", ", query.platforms()));
        }
        if (attempted > 0 && results.isEmpty() && !failures.isEmpty()) {
            throw ApiException.badRequest("official ecommerce api request failed: " + String.join("; ", failures));
        }
        return results.stream()
                .peek(this::remember)
                .map(OfficialProductResult::platformProduct)
                .sorted(Comparator.comparing(MockCatalog.PlatformProductData::platform)
                        .thenComparing(MockCatalog.PlatformProductData::platformProductId))
                .toList();
    }

    public Optional<MockCatalog.ProductData> product(long productId) {
        return Optional.ofNullable(products.get(productId));
    }

    public Optional<MockCatalog.PlatformProductData> platformProduct(long platformProductId) {
        return Optional.ofNullable(platformProducts.get(platformProductId));
    }

    public Optional<MockCatalog.ReviewSummaryData> reviewSummary(long platformProductId) {
        return Optional.ofNullable(reviewSummaries.get(platformProductId));
    }

    public Optional<MockCatalog.PriceHistoryData> priceHistory(long platformProductId) {
        return Optional.ofNullable(priceHistories.get(platformProductId));
    }

    public boolean hasConfiguredClient() {
        return clients.stream().anyMatch(OfficialApiClient::configured);
    }

    public EcommerceStatusPayload status() {
        List<EcommerceProviderStatus> providers = clients.stream()
                .sorted(Comparator.comparing(OfficialApiClient::platform))
                .map(this::providerStatus)
                .toList();
        return new EcommerceStatusPayload(properties.isEnabled(), hasConfiguredClient(), providers);
    }

    public EcommerceDiagnosticsPayload diagnostics(String keyword, int pageSize, List<String> platforms) {
        return diagnostics(keyword, pageSize, platforms, Map.of());
    }

    public EcommerceDiagnosticsPayload diagnostics(String keyword, int pageSize, List<String> platforms, Map<String, Object> filters) {
        return diagnostics(keyword, pageSize, platforms, filters, "comprehensive");
    }

    public EcommerceDiagnosticsPayload diagnostics(String keyword, int pageSize, List<String> platforms, Map<String, Object> filters, String sortBy) {
        String normalizedKeyword = isBlank(keyword) ? "吹风机" : keyword.trim();
        int safePageSize = Math.max(1, Math.min(5, pageSize));
        ProductSourceQuery query = new ProductSourceQuery(
                normalizedKeyword,
                "",
                "",
                "",
                filters == null ? Map.of() : filters,
                normalizePlatforms(platforms),
                normalizeSort(sortBy),
                safePageSize
        );
        List<EcommerceProviderDiagnostic> providers = clientsFor(query.platforms()).stream()
                .sorted(Comparator.comparing(OfficialApiClient::platform))
                .map(client -> diagnose(client, query))
                .toList();
        return new EcommerceDiagnosticsPayload(normalizedKeyword, OffsetDateTime.now(), providers);
    }

    private EcommerceProviderDiagnostic diagnose(OfficialApiClient client, ProductSourceQuery query) {
        EcommerceProviderStatus status = providerStatus(client);
        if (!client.configured()) {
            return new EcommerceProviderDiagnostic(
                    client.platform(),
                    false,
                    false,
                    "not_configured",
                    0,
                    0,
                    List.of(),
                    "",
                    "missing config: " + String.join(", ", status.missingConfig()),
                    status.missingConfig()
            );
        }
        long started = System.nanoTime();
        try {
            List<OfficialProductResult> results = client.search(query);
            results.forEach(this::remember);
            long durationMs = Math.max(1, (System.nanoTime() - started) / 1_000_000);
            return new EcommerceProviderDiagnostic(
                    client.platform(),
                    true,
                    true,
                    "ok",
                    results.size(),
                    durationMs,
                    results.stream()
                            .map(result -> result.platformProduct().title())
                            .limit(3)
                            .toList(),
                    "",
                    "",
                    List.of()
            );
        } catch (RuntimeException ex) {
            long durationMs = Math.max(1, (System.nanoTime() - started) / 1_000_000);
            return new EcommerceProviderDiagnostic(
                    client.platform(),
                    true,
                    false,
                    "failed",
                    0,
                    durationMs,
                    List.of(),
                    ex instanceof OfficialApiException official ? official.errorCode() : "",
                    truncate(ex.getMessage()),
                    List.of()
            );
        }
    }

    private EcommerceProviderStatus providerStatus(OfficialApiClient client) {
        if ("拼多多".equals(client.platform())) {
            List<String> required = List.of("ECOMMERCE_API_ENABLED", "PDD_API_ENABLED", "PDD_CLIENT_ID", "PDD_CLIENT_SECRET");
            List<String> missing = new ArrayList<>();
            EcommerceApiProperties.Pdd pdd = properties.getPdd();
            if (!properties.isEnabled()) {
                missing.add("ECOMMERCE_API_ENABLED");
            }
            if (!pdd.isEnabled()) {
                missing.add("PDD_API_ENABLED");
            }
            if (OfficialCredentialValue.missing(pdd.getClientId())) {
                missing.add("PDD_CLIENT_ID");
            }
            if (OfficialCredentialValue.missing(pdd.getClientSecret())) {
                missing.add("PDD_CLIENT_SECRET");
            }
            return new EcommerceProviderStatus(client.platform(), properties.isEnabled() && pdd.isEnabled(), client.configured(), required, missing);
        }
        if ("京东".equals(client.platform())) {
            List<String> required = List.of("ECOMMERCE_API_ENABLED", "JD_API_ENABLED", "JD_APP_KEY", "JD_APP_SECRET");
            List<String> missing = new ArrayList<>();
            EcommerceApiProperties.Jd jd = properties.getJd();
            if (!properties.isEnabled()) {
                missing.add("ECOMMERCE_API_ENABLED");
            }
            if (!jd.isEnabled()) {
                missing.add("JD_API_ENABLED");
            }
            if (OfficialCredentialValue.missing(jd.getAppKey())) {
                missing.add("JD_APP_KEY");
            }
            if (OfficialCredentialValue.missing(jd.getAppSecret())) {
                missing.add("JD_APP_SECRET");
            }
            return new EcommerceProviderStatus(client.platform(), properties.isEnabled() && jd.isEnabled(), client.configured(), required, missing);
        }
        return new EcommerceProviderStatus(client.platform(), client.configured(), client.configured(), List.of(), List.of());
    }

    private void remember(OfficialProductResult result) {
        products.put(result.product().productId(), result.product());
        platformProducts.put(result.platformProduct().platformProductId(), result.platformProduct());
        result.reviewSummary().ifPresent(summary -> reviewSummaries.put(summary.platformProductId(), summary));
        priceHistories.putIfAbsent(
                result.platformProduct().platformProductId(),
                new MockCatalog.PriceHistoryData(
                        result.platformProduct().platformProductId(),
                        List.of(new MockCatalog.PricePointData(OffsetDateTime.now(), result.platformProduct().price()))
                )
        );
    }

    private boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    private String truncate(String value) {
        if (isBlank(value)) {
            return "official ecommerce api request failed";
        }
        return value.length() <= 240 ? value : value.substring(0, 240);
    }

    private String normalizeSort(String value) {
        if (isBlank(value)) {
            return "comprehensive";
        }
        String normalized = value.trim().toLowerCase(Locale.ROOT);
        return SORT_MODES.contains(normalized) ? normalized : "comprehensive";
    }

    private List<OfficialApiClient> clientsFor(List<String> platforms) {
        List<String> normalized = normalizePlatforms(platforms);
        return clients.stream()
                .filter(client -> normalized.isEmpty() || normalized.contains(normalizePlatform(client.platform())))
                .toList();
    }

    private List<String> normalizePlatforms(List<String> platforms) {
        if (platforms == null || platforms.isEmpty()) {
            return List.of();
        }
        return platforms.stream()
                .flatMap(value -> Arrays.stream(String.valueOf(value).split(",")))
                .map(String::trim)
                .filter(value -> !value.isBlank())
                .map(this::normalizePlatform)
                .distinct()
                .toList();
    }

    private String normalizePlatform(String value) {
        String normalized = value == null ? "" : value.toLowerCase(Locale.ROOT).replace("平台", "").replace("商城", "").trim();
        return switch (normalized) {
            case "pdd", "拼多多", "多多进宝" -> "pdd";
            case "jd", "jingdong", "京东", "京东自营" -> "jd";
            case "taobao", "淘宝" -> "taobao";
            case "tmall", "天猫" -> "tmall";
            default -> normalized;
        };
    }
}
