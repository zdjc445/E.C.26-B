package com.ec26b.shoppingagent.product;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Real ecommerce provider scaffold.
 *
 * <p>Activated when {@code app.ecommerce.real-provider-enabled=true} <em>and</em>
 * both base URL and API key are configured. When disabled or misconfigured, this
 * provider returns an empty result and the caller (see
 * {@link com.ec26b.shoppingagent.api.EcommerceController}) falls back to
 * {@link MockProductSourceProvider}.
 *
 * <p>The expected upstream contract is a simple JSON API:
 * <pre>
 * GET {baseUrl}/products?keyword={kw}&maxPrice={mp}&platform={pl}
 * → { "products": [{"productId", "title", "platform", "price", "originalPrice",
 *                   "shopName", "rating", "sales", "tags": [...], "brand"}, ...] }
 * </pre>
 *
 * <p>The shape mirrors {@link ProductOffer} fields so that wiring a real platform
 * adapter only requires implementing the upstream proxy or a translation layer.
 */
@Component
public class RealEcommerceProvider implements ProductSourceProvider {

    private final boolean enabled;
    private final String baseUrl;
    private final String apiKey;
    private final ObjectMapper objectMapper;
    private final RestClient restClient;

    public RealEcommerceProvider(
            @Value("${app.ecommerce.real-provider-enabled:false}") boolean enabled,
            @Value("${app.ecommerce.real-provider-base-url:}") String baseUrl,
            @Value("${app.ecommerce.real-provider-api-key:}") String apiKey,
            ObjectMapper objectMapper) {
        this.enabled = enabled && baseUrl != null && !baseUrl.isBlank()
                && apiKey != null && !apiKey.isBlank();
        this.baseUrl = baseUrl == null ? "" : baseUrl;
        this.apiKey = apiKey == null ? "" : apiKey;
        this.objectMapper = objectMapper;
        this.restClient = RestClient.builder().build();
    }

    @Override
    public ProductSearchResult search(ProductSearchQuery query) {
        if (!enabled) {
            return new ProductSearchResult(List.of(), Map.of(), null);
        }
        try {
            StringBuilder uri = new StringBuilder(baseUrl);
            uri.append(baseUrl.endsWith("/") ? "products" : "/products");
            uri.append("?keyword=").append(percent(query.keyword()));
            if (query.maxPrice() != null) uri.append("&maxPrice=").append(query.maxPrice());
            if (query.platforms() != null) {
                for (String p : query.platforms()) {
                    uri.append("&platform=").append(percent(p));
                }
            }
            if (query.brand() != null) uri.append("&brand=").append(percent(query.brand()));
            String body = restClient.get()
                    .uri(uri.toString())
                    .header(HttpHeaders.AUTHORIZATION, "Bearer " + apiKey)
                    .accept(MediaType.APPLICATION_JSON)
                    .retrieve()
                    .body(String.class);
            if (body == null || body.isBlank()) {
                return new ProductSearchResult(List.of(), Map.of(), null);
            }
            JsonNode root;
            try {
                root = objectMapper.readTree(body);
            } catch (com.fasterxml.jackson.core.JsonProcessingException ex) {
                return new ProductSearchResult(List.of(), Map.of(), null);
            }
            List<ProductOffer> offers = new ArrayList<>();
            for (JsonNode node : root.path("products")) {
                offers.add(new ProductOffer(
                        node.path("productId").asText(),
                        node.path("title").asText(""),
                        node.path("platform").asText(""),
                        node.path("price").asDouble(0),
                        node.path("originalPrice").asDouble(0),
                        node.path("shopName").asText(""),
                        node.path("imageUrl").asText(""),
                        node.path("productUrl").asText(""),
                        node.path("rating").asDouble(0),
                        node.path("sales").asInt(0),
                        toList(node.path("tags")),
                        toList(node.path("reasons")),
                        0,
                        node.path("brand").isMissingNode() ? null : node.path("brand").asText(null)));
            }
            Map<String, ProductSearchResult.PlatformStats> stats = new LinkedHashMap<>();
            for (ProductOffer offer : offers) {
                stats.computeIfAbsent(offer.platform(), k -> new ProductSearchResult.PlatformStats(
                        k, offer.price(), offer.price(), 0, "real-source"));
            }
            return new ProductSearchResult(offers, stats, offers.isEmpty() ? null : offers.get(0));
        } catch (RuntimeException ex) {
            return new ProductSearchResult(List.of(), Map.of(), null);
        }
    }

    @Override
    public String sourceName() {
        return enabled ? "real" : "real-disabled";
    }

    public boolean enabled() {
        return enabled;
    }

    public String baseUrl() {
        return baseUrl;
    }

    private String percent(String value) {
        if (value == null) return "";
        return java.net.URLEncoder.encode(value, java.nio.charset.StandardCharsets.UTF_8);
    }

    private List<String> toList(JsonNode node) {
        if (node == null || !node.isArray()) return List.of();
        List<String> result = new ArrayList<>();
        node.forEach(n -> result.add(n.asText()));
        return result;
    }
}
