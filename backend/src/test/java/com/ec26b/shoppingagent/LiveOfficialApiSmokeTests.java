package com.ec26b.shoppingagent;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.math.BigDecimal;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.OffsetDateTime;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@EnabledIfEnvironmentVariable(named = "ECOMMERCE_LIVE_TEST", matches = "true")
class LiveOfficialApiSmokeTests {
    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void configuredOfficialApiReturnsLiveProducts() throws Exception {
        JsonNode statusPayload = getJson(null, "/api/ecommerce/status").get("data");
        assertThat(statusPayload.get("enabled").asBoolean()).isTrue();
        assertThat(statusPayload.get("hasConfiguredClient").asBoolean()).isTrue();

        String token = registerAndToken();
        String query = envOrDefault("ECOMMERCE_LIVE_QUERY", "吹风机");
        String sortBy = envOrDefault("ECOMMERCE_LIVE_SORT_BY", "price_asc");
        List<String> platforms = csvEnv("ECOMMERCE_LIVE_PLATFORMS");
        Map<String, Object> filters = liveFilters();

        JsonNode diagnostics = getJson(token, diagnosticsPath(query, platforms, filters, sortBy)).get("data");
        JsonNode providerDiagnostics = diagnostics.get("providers");
        assertThat(providerDiagnostics).isNotNull();
        assertThat(providerDiagnostics.size()).isGreaterThan(0);
        assertRequestedProvidersSucceeded(providerDiagnostics, platforms);
        JsonNode successfulProvider = firstSuccessfulProvider(providerDiagnostics);
        assertThat(successfulProvider.get("configured").asBoolean()).isTrue();
        assertThat(successfulProvider.get("status").asText()).isEqualTo("ok");
        assertThat(successfulProvider.get("itemCount").asInt()).isGreaterThan(0);
        assertThat(successfulProvider.get("durationMs").asLong()).isGreaterThan(0);
        assertThat(successfulProvider.get("sampleTitles").size()).isGreaterThan(0);
        assertThat(textOrBlank(successfulProvider.get("errorCode"))).isBlank();

        Map<String, Object> request = new LinkedHashMap<>();
        request.put("query", query);
        request.put("sourceType", "official_api");
        request.put("sortBy", sortBy);
        if (!filters.isEmpty()) {
            request.put("filters", filters);
        }
        if (!platforms.isEmpty()) {
            request.put("platforms", platforms);
        }
        JsonNode search = postJson(token, "/api/search-tasks", request).get("data");

        JsonNode items = search.get("items");
        assertThat(items).isNotNull();
        assertThat(items.size()).isGreaterThan(0);
        JsonNode first = items.get(0);
        assertLiveProductItem(first, "first official API search item");
        assertSearchContainsRequestedPlatforms(items, platforms);

        writeLiveReport(query, sortBy, platforms, filters, diagnostics, search);
    }

    private String registerAndToken() throws Exception {
        JsonNode response = postJson(null, "/api/auth/register", Map.of(
                "username", "live" + UUID.randomUUID().toString().replace("-", "").substring(0, 10),
                "password", "password123",
                "nickname", "LiveTester"
        ));
        return response.get("data").get("accessToken").asText();
    }

    private String diagnosticsPath(String query, List<String> platforms, Map<String, Object> filters, String sortBy) {
        String path = "/api/ecommerce/diagnostics?query=" + encode(query) + "&pageSize=3";
        if (!platforms.isEmpty()) {
            path += "&platforms=" + encode(String.join(",", platforms));
        }
        if (sortBy != null && !sortBy.isBlank()) {
            path += "&sortBy=" + encode(sortBy);
        }
        for (Map.Entry<String, Object> entry : filters.entrySet()) {
            path += "&" + encode(entry.getKey()) + "=" + encode(String.valueOf(entry.getValue()));
        }
        return path;
    }

    private String encode(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }

    private JsonNode firstSuccessfulProvider(JsonNode providers) {
        for (JsonNode provider : providers) {
            if (provider.get("success").asBoolean()) {
                return provider;
            }
        }
        throw new AssertionError("No official ecommerce provider passed live diagnostics: " + providers);
    }

    private void assertRequestedProvidersSucceeded(JsonNode providers, List<String> requestedPlatforms) {
        if (requestedPlatforms.isEmpty()) {
            return;
        }
        for (String requestedPlatform : requestedPlatforms) {
            JsonNode provider = providerFor(providers, requestedPlatform);
            assertThat(provider)
                    .as("diagnostics should include requested platform %s", requestedPlatform)
                    .isNotNull();
            assertThat(provider.get("configured").asBoolean())
                    .as("requested platform %s should be configured", requestedPlatform)
                    .isTrue();
            assertThat(provider.get("success").asBoolean())
                    .as("requested platform %s should pass diagnostics: %s", requestedPlatform, provider)
                    .isTrue();
            assertThat(provider.get("itemCount").asInt())
                    .as("requested platform %s should return live products: %s", requestedPlatform, provider)
                    .isGreaterThan(0);
            assertThat(provider.get("sampleTitles").size())
                    .as("requested platform %s should return sample titles: %s", requestedPlatform, provider)
                    .isGreaterThan(0);
        }
    }

    private JsonNode providerFor(JsonNode providers, String requestedPlatform) {
        for (JsonNode provider : providers) {
            if (samePlatform(provider.path("platform").asText(), requestedPlatform)) {
                return provider;
            }
        }
        return null;
    }

    private void assertSearchContainsRequestedPlatforms(JsonNode items, List<String> requestedPlatforms) {
        if (requestedPlatforms.isEmpty()) {
            return;
        }
        for (String requestedPlatform : requestedPlatforms) {
            JsonNode item = itemForPlatform(items, requestedPlatform);
            assertThat(item)
                    .as("search should include a live official_api product for requested platform %s", requestedPlatform)
                    .isNotNull();
            assertLiveProductItem(item, "requested platform " + requestedPlatform + " search item");
        }
    }

    private JsonNode itemForPlatform(JsonNode items, String requestedPlatform) {
        for (JsonNode item : items) {
            if (samePlatform(item.path("platform").asText(), requestedPlatform)) {
                return item;
            }
        }
        return null;
    }

    private void assertLiveProductItem(JsonNode item, String description) {
        assertThat(textOrBlank(item.get("sourceType")))
                .as("%s sourceType", description)
                .isEqualTo("official_api");
        assertThat(textOrBlank(item.get("platform")))
                .as("%s platform", description)
                .isNotBlank();
        assertThat(textOrBlank(item.get("title")))
                .as("%s title", description)
                .isNotBlank();
        assertThat(textOrBlank(item.get("url")))
                .as("%s url", description)
                .startsWith("http");
        JsonNode price = item.get("price");
        assertThat(price)
                .as("%s price", description)
                .isNotNull();
        String amount = textOrBlank(price.get("amount"));
        assertThat(amount)
                .as("%s price amount", description)
                .isNotBlank();
        assertThat(new BigDecimal(amount))
                .as("%s price amount", description)
                .isGreaterThan(BigDecimal.ZERO);
    }

    private boolean samePlatform(String platform, String requestedPlatform) {
        String normalized = requestedPlatform == null ? "" : requestedPlatform.trim().toLowerCase();
        return switch (normalized) {
            case "pdd", "拼多多", "多多进宝" -> "拼多多".equals(platform);
            case "jd", "jingdong", "京东", "京东自营" -> "京东".equals(platform);
            default -> platform.equalsIgnoreCase(normalized);
        };
    }

    private String textOrBlank(JsonNode node) {
        return node == null || node.isNull() ? "" : node.asText();
    }

    private JsonNode postJson(String token, String path, Object body) throws Exception {
        var request = post(path)
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(body));
        if (token != null) {
            request.header("Authorization", "Bearer " + token);
        }
        String content = mockMvc.perform(request)
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString(StandardCharsets.UTF_8);
        return objectMapper.readTree(content);
    }

    private JsonNode getJson(String token, String path) throws Exception {
        var request = get(path);
        if (token != null) {
            request.header("Authorization", "Bearer " + token);
        }
        String content = mockMvc.perform(request)
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString(StandardCharsets.UTF_8);
        return objectMapper.readTree(content);
    }

    private String envOrDefault(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value;
    }

    private void writeLiveReport(String query, String sortBy, List<String> platforms, Map<String, Object> filters, JsonNode diagnostics, JsonNode search) throws Exception {
        Path reportPath = Path.of(envOrDefault("ECOMMERCE_LIVE_REPORT_PATH", "target/live-ecommerce-smoke-report.json"));
        Path parent = reportPath.toAbsolutePath().getParent();
        if (parent != null) {
            Files.createDirectories(parent);
        }

        var report = objectMapper.createObjectNode();
        report.put("checkedAt", OffsetDateTime.now().toString());
        report.put("query", query);
        report.put("sortBy", sortBy);
        var requestedPlatforms = report.putArray("requestedPlatforms");
        platforms.forEach(requestedPlatforms::add);
        var reportFilters = report.putObject("filters");
        filters.forEach((key, value) -> reportFilters.set(key, objectMapper.valueToTree(value)));
        report.set("diagnostics", diagnostics);

        JsonNode items = search.get("items");
        var searchReport = report.putObject("search");
        searchReport.put("itemCount", items == null ? 0 : items.size());
        var sampleItems = searchReport.putArray("sampleItems");
        if (items != null) {
            for (int i = 0; i < Math.min(3, items.size()); i++) {
                JsonNode item = items.get(i);
                var sample = sampleItems.addObject();
                sample.put("platform", textOrBlank(item.get("platform")));
                sample.put("title", textOrBlank(item.get("title")));
                sample.put("url", textOrBlank(item.get("url")));
                sample.put("sourceType", textOrBlank(item.get("sourceType")));
                JsonNode price = item.get("price");
                if (price != null) {
                    var priceNode = sample.putObject("price");
                    priceNode.put("amount", textOrBlank(price.get("amount")));
                    priceNode.put("currency", textOrBlank(price.get("currency")));
                }
            }
        }

        objectMapper.writerWithDefaultPrettyPrinter().writeValue(reportPath.toFile(), report);
    }

    private Map<String, Object> liveFilters() {
        Map<String, Object> filters = new LinkedHashMap<>();
        putTextEnv(filters, "minPrice", "ECOMMERCE_LIVE_MIN_PRICE");
        putTextEnv(filters, "maxPrice", "ECOMMERCE_LIVE_MAX_PRICE");
        putBoolEnv(filters, "withCoupon", "ECOMMERCE_LIVE_WITH_COUPON");
        putBoolEnv(filters, "officialOnly", "ECOMMERCE_LIVE_OFFICIAL_ONLY");
        putBoolEnv(filters, "selfOperatedOnly", "ECOMMERCE_LIVE_SELF_OPERATED_ONLY");
        return filters;
    }

    private void putTextEnv(Map<String, Object> filters, String key, String envName) {
        String value = System.getenv(envName);
        if (value != null && !value.isBlank()) {
            filters.put(key, value.trim());
        }
    }

    private void putBoolEnv(Map<String, Object> filters, String key, String envName) {
        String value = System.getenv(envName);
        if (value != null && !value.isBlank()) {
            filters.put(key, "true".equalsIgnoreCase(value.trim()) || "1".equals(value.trim()) || "yes".equalsIgnoreCase(value.trim()) || "on".equalsIgnoreCase(value.trim()));
        }
    }

    private List<String> csvEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            return List.of();
        }
        return Arrays.stream(value.split(","))
                .map(String::trim)
                .filter(item -> !item.isBlank())
                .toList();
    }
}
