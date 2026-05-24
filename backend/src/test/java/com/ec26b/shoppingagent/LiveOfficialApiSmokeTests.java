package com.ec26b.shoppingagent;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.math.BigDecimal;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
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
        List<String> platforms = csvEnv("ECOMMERCE_LIVE_PLATFORMS");

        JsonNode diagnostics = getJson(token, diagnosticsPath(query, platforms)).get("data");
        JsonNode providerDiagnostics = diagnostics.get("providers");
        assertThat(providerDiagnostics).isNotNull();
        assertThat(providerDiagnostics.size()).isGreaterThan(0);
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
        request.put("sortBy", "price_asc");
        if (!platforms.isEmpty()) {
            request.put("platforms", platforms);
        }
        JsonNode search = postJson(token, "/api/search-tasks", request).get("data");

        JsonNode items = search.get("items");
        assertThat(items).isNotNull();
        assertThat(items.size()).isGreaterThan(0);
        JsonNode first = items.get(0);
        assertThat(first.get("sourceType").asText()).isEqualTo("official_api");
        assertThat(first.get("platform").asText()).isNotBlank();
        assertThat(first.get("title").asText()).isNotBlank();
        assertThat(first.get("url").asText()).startsWith("http");
        assertThat(new BigDecimal(first.get("price").get("amount").asText())).isGreaterThan(BigDecimal.ZERO);
    }

    private String registerAndToken() throws Exception {
        JsonNode response = postJson(null, "/api/auth/register", Map.of(
                "username", "live" + UUID.randomUUID().toString().replace("-", "").substring(0, 10),
                "password", "password123",
                "nickname", "LiveTester"
        ));
        return response.get("data").get("accessToken").asText();
    }

    private String diagnosticsPath(String query, List<String> platforms) {
        String path = "/api/ecommerce/diagnostics?query=" + encode(query) + "&pageSize=3";
        if (!platforms.isEmpty()) {
            path += "&platforms=" + encode(String.join(",", platforms));
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
