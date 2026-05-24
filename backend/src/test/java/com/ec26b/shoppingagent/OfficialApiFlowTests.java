package com.ec26b.shoppingagent;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OfficialApiFlowTests {
    private static HttpServer server;
    private static int port;
    private static final Map<String, String> lastRequest = new ConcurrentHashMap<>();

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @DynamicPropertySource
    static void officialApiProperties(DynamicPropertyRegistry registry) {
        ensureServer();
        registry.add("app.ecommerce.enabled", () -> "true");
        registry.add("app.ecommerce.pdd.enabled", () -> "true");
        registry.add("app.ecommerce.pdd.base-url", () -> "http://127.0.0.1:" + port + "/api/router");
        registry.add("app.ecommerce.pdd.client-id", () -> "test-client");
        registry.add("app.ecommerce.pdd.client-secret", () -> "test-secret");
        registry.add("app.ecommerce.jd.enabled", () -> "true");
        registry.add("app.ecommerce.jd.base-url", () -> "http://127.0.0.1:" + port + "/jd-fail");
        registry.add("app.ecommerce.jd.app-key", () -> "test-jd-key");
        registry.add("app.ecommerce.jd.app-secret", () -> "test-jd-secret");
        registry.add("app.ecommerce.request-timeout-seconds", () -> "3");
    }

    @AfterAll
    static void stopServer() {
        if (server != null) {
            server.stop(0);
        }
    }

    @Test
    void officialApiSearchUsesSignedPddRequestAndMapsResults() throws Exception {
        String token = registerAndToken();
        JsonNode status = getJson(token, "/api/ecommerce/status").get("data");
        assertThat(status.get("enabled").asBoolean()).isTrue();
        assertThat(status.get("hasConfiguredClient").asBoolean()).isTrue();
        assertThat(status.get("providers").toString()).contains("拼多多");
        assertThat(provider(status, "拼多多").get("enabled").asBoolean()).isTrue();
        assertThat(provider(status, "拼多多").get("missingConfig").isEmpty()).isTrue();

        JsonNode search = postJson(token, "/api/search-tasks", Map.of(
                "query", "吹风机",
                "sourceType", "official_api",
                "platforms", java.util.List.of("pdd"),
                "sortBy", "price_asc"
        )).get("data");

        JsonNode first = search.get("items").get(0);
        assertThat(first.get("platform").asText()).isEqualTo("拼多多");
        assertThat(first.get("sourceType").asText()).isEqualTo("official_api");
        assertThat(first.get("price").get("amount").asText()).isEqualTo("129.00");
        assertThat(first.get("platformProductId").asLong()).isGreaterThan(3_000_000_000_000L);

        assertThat(lastRequest).containsEntry("type", "pdd.ddk.goods.search");
        assertThat(lastRequest).containsEntry("client_id", "test-client");
        assertThat(lastRequest.get("keyword")).contains("吹风机");
        assertThat(lastRequest.get("sign")).isNotBlank();

        long platformProductId = first.get("platformProductId").asLong();
        JsonNode history = getJson(token, "/api/platform-products/" + platformProductId + "/price-history").get("data");
        assertThat(history.get("currentPrice").get("amount").asText()).isEqualTo("129.00");

        JsonNode review = getJson(token, "/api/platform-products/" + platformProductId + "/review-summary").get("data");
        assertThat(review.get("summary").asText()).contains("拼多多官方 API");

        String jdFailure = mockMvc.perform(post("/api/search-tasks")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of(
                                "query", "吹风机",
                                "sourceType", "official_api",
                                "platforms", java.util.List.of("jd")
                        )))
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isBadRequest())
                .andReturn().getResponse().getContentAsString(StandardCharsets.UTF_8);
        assertThat(jdFailure).contains("京东");

        JsonNode diagnostics = getJson(token, "/api/ecommerce/diagnostics?query=吹风机&pageSize=2").get("data");
        assertThat(diagnostics.get("query").asText()).isEqualTo("吹风机");
        assertThat(diagnostic(diagnostics, "拼多多").get("success").asBoolean()).isTrue();
        assertThat(diagnostic(diagnostics, "拼多多").get("itemCount").asInt()).isEqualTo(1);
        assertThat(diagnostic(diagnostics, "拼多多").get("sampleTitles").get(0).asText()).contains("吹风机");
        assertThat(diagnostic(diagnostics, "京东").get("success").asBoolean()).isFalse();
        assertThat(diagnostic(diagnostics, "京东").get("status").asText()).isEqualTo("failed");

        JsonNode pddDiagnostics = getJson(token, "/api/ecommerce/diagnostics?query=吹风机&pageSize=2&platforms=pdd").get("data");
        assertThat(pddDiagnostics.get("providers").size()).isEqualTo(1);
        assertThat(diagnostic(pddDiagnostics, "拼多多").get("success").asBoolean()).isTrue();
    }

    private static synchronized void ensureServer() {
        if (server != null) {
            return;
        }
        try {
            server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            port = server.getAddress().getPort();
            server.createContext("/api/router", exchange -> {
                byte[] requestBytes = exchange.getRequestBody().readAllBytes();
                lastRequest.clear();
                lastRequest.putAll(parseForm(new String(requestBytes, StandardCharsets.UTF_8)));
                byte[] response = """
                        {
                          "goods_search_response": {
                            "goods_list": [
                              {
                                "goods_id": 123456789,
                                "goods_name": "官方高速负离子吹风机 黑色 低噪",
                                "goods_thumbnail_url": "https://img.example.test/hair-dryer.jpg",
                                "min_group_price": 12900,
                                "min_normal_price": 16900,
                                "mall_name": "MockCare官方旗舰店",
                                "sales_tip": "2.5万+件",
                                "avg_desc": "4.9",
                                "goods_sign": "test-goods-sign"
                              }
                            ]
                          }
                        }
                        """.getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().add("Content-Type", "application/json;charset=UTF-8");
                exchange.sendResponseHeaders(200, response.length);
                exchange.getResponseBody().write(response);
                exchange.close();
            });
            server.createContext("/jd-fail", exchange -> {
                byte[] response = "{\"error\":\"temporary jd failure\"}".getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().add("Content-Type", "application/json;charset=UTF-8");
                exchange.sendResponseHeaders(500, response.length);
                exchange.getResponseBody().write(response);
                exchange.close();
            });
            server.start();
        } catch (IOException ex) {
            throw new IllegalStateException("Cannot start official API stub", ex);
        }
    }

    private static Map<String, String> parseForm(String body) {
        Map<String, String> params = new ConcurrentHashMap<>();
        if (body == null || body.isBlank()) {
            return params;
        }
        Arrays.stream(body.split("&"))
                .map(pair -> pair.split("=", 2))
                .forEach(pair -> {
                    String key = URLDecoder.decode(pair[0], StandardCharsets.UTF_8);
                    String value = pair.length > 1 ? URLDecoder.decode(pair[1], StandardCharsets.UTF_8) : "";
                    params.put(key, value);
                });
        return params;
    }

    private JsonNode provider(JsonNode status, String platform) {
        for (JsonNode provider : status.get("providers")) {
            if (platform.equals(provider.get("platform").asText())) {
                return provider;
            }
        }
        throw new AssertionError("Provider not found: " + platform);
    }

    private JsonNode diagnostic(JsonNode diagnostics, String platform) {
        for (JsonNode provider : diagnostics.get("providers")) {
            if (platform.equals(provider.get("platform").asText())) {
                return provider;
            }
        }
        throw new AssertionError("Diagnostic not found: " + platform);
    }

    private String registerAndToken() throws Exception {
        JsonNode response = postJson(null, "/api/auth/register", Map.of(
                "username", "u" + UUID.randomUUID().toString().replace("-", "").substring(0, 12),
                "password", "password123",
                "nickname", "OfficialTester"
        ));
        return response.get("data").get("accessToken").asText();
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
        String content = mockMvc.perform(get(path).header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString(StandardCharsets.UTF_8);
        return objectMapper.readTree(content);
    }
}
