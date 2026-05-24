package com.ec26b.shoppingagent.ecommerce;

import com.ec26b.shoppingagent.api.ApiModels.EcommerceProviderStatus;
import com.ec26b.shoppingagent.api.ApiModels.EcommerceStatusPayload;
import com.ec26b.shoppingagent.service.MockCatalog;
import org.springframework.stereotype.Component;

import java.time.OffsetDateTime;
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
        return clients.stream()
                .filter(OfficialApiClient::configured)
                .flatMap(client -> client.search(query).stream())
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
                .map(client -> new EcommerceProviderStatus(client.platform(), client.configured()))
                .toList();
        return new EcommerceStatusPayload(properties.isEnabled(), hasConfiguredClient(), providers);
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
}
