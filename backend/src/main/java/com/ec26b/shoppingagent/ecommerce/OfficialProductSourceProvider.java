package com.ec26b.shoppingagent.ecommerce;

import com.ec26b.shoppingagent.api.ApiException;
import com.ec26b.shoppingagent.api.ApiModels.EcommerceProviderStatus;
import com.ec26b.shoppingagent.api.ApiModels.EcommerceStatusPayload;
import com.ec26b.shoppingagent.service.MockCatalog;
import org.springframework.stereotype.Component;

import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

@Component
public class OfficialProductSourceProvider {
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
        for (OfficialApiClient client : clients) {
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
            if (isBlank(pdd.getClientId())) {
                missing.add("PDD_CLIENT_ID");
            }
            if (isBlank(pdd.getClientSecret())) {
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
            if (isBlank(jd.getAppKey())) {
                missing.add("JD_APP_KEY");
            }
            if (isBlank(jd.getAppSecret())) {
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
}
