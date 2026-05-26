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
    private static final Map<String, String> lastJdRequest = new ConcurrentHashMap<>();

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
        registry.add("app.ecommerce.pdd.pid", () -> "pdd-test-pid");
        registry.add("app.ecommerce.pdd.custom-parameters", () -> "{\"source\":\"flow-test\"}");
        registry.add("app.ecommerce.jd.enabled", () -> "true");
        registry.add("app.ecommerce.jd.base-url", () -> "http://127.0.0.1:" + port + "/jd/router");
        registry.add("app.ecommerce.jd.app-key", () -> "test-jd-key");
        registry.add("app.ecommerce.jd.app-secret", () -> "test-jd-secret");
        registry.add("app.ecommerce.jd.site-id", () -> "12345");
        registry.add("app.ecommerce.jd.position-id", () -> "67890");
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
                "sortBy", "price_asc",
                "filters", Map.of(
                        "minPrice", Map.of("amount", "100.00", "currency", "CNY"),
                        "maxPrice", Map.of("amount", "200.00", "currency", "CNY"),
                        "withCoupon", true,
                        "officialOnly", true
                )
        )).get("data");

        JsonNode first = search.get("items").get(0);
        assertThat(first.get("platform").asText()).isEqualTo("拼多多");
        assertThat(first.get("sourceType").asText()).isEqualTo("official_api");
        assertThat(first.get("price").get("amount").asText()).isEqualTo("129.00");
        assertThat(first.get("platformProductId").asLong()).isGreaterThan(3_000_000_000_000L);

        assertThat(lastRequest).containsEntry("type", "pdd.ddk.goods.search");
        assertThat(lastRequest).containsEntry("client_id", "test-client");
        assertThat(lastRequest).containsEntry("pid", "pdd-test-pid");
        assertThat(lastRequest).containsEntry("custom_parameters", "{\"source\":\"flow-test\"}");
        assertThat(lastRequest.get("keyword")).contains("吹风机");
        assertThat(lastRequest.get("sign")).isNotBlank();
        assertThat(lastRequest).containsEntry("with_coupon", "true");
        assertThat(lastRequest).containsEntry("merchant_type", "3");
        assertThat(lastRequest.get("range_list")).contains("\"range_id\":0", "\"range_from\":10000", "\"range_to\":20000");

        JsonNode signOnlySearch = postJson(token, "/api/search-tasks", Map.of(
                "query", "拼多多签名商品",
                "sourceType", "official_api",
                "platforms", java.util.List.of("pdd")
        )).get("data");
        JsonNode signOnlyItem = signOnlySearch.get("items").get(0);
        assertThat(signOnlyItem.get("platform").asText()).isEqualTo("拼多多");
        assertThat(signOnlyItem.get("sourceType").asText()).isEqualTo("official_api");
        assertThat(signOnlyItem.get("title").asText()).contains("签名");
        assertThat(signOnlyItem.get("url").asText()).contains("goods_sign=test-sign-only");

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

        String mixedPlatformFailure = mockMvc.perform(post("/api/search-tasks")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of(
                                "query", "吹风机",
                                "sourceType", "official_api",
                                "platforms", java.util.List.of("pdd", "jd")
                        )))
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isBadRequest())
                .andReturn().getResponse().getContentAsString(StandardCharsets.UTF_8);
        assertThat(mixedPlatformFailure).contains("selected platforms", "京东");

        JsonNode diagnostics = getJson(token, "/api/ecommerce/diagnostics?query=吹风机&pageSize=2").get("data");
        assertThat(diagnostics.get("query").asText()).isEqualTo("吹风机");
        assertThat(diagnostic(diagnostics, "拼多多").get("success").asBoolean()).isTrue();
        assertThat(diagnostic(diagnostics, "拼多多").get("itemCount").asInt()).isEqualTo(1);
        assertThat(diagnostic(diagnostics, "拼多多").get("sampleTitles").get(0).asText()).contains("吹风机");
        assertThat(diagnostic(diagnostics, "京东").get("success").asBoolean()).isFalse();
        assertThat(diagnostic(diagnostics, "京东").get("status").asText()).isEqualTo("failed");
        assertThat(diagnostic(diagnostics, "京东").get("errorCode").asText()).isEqualTo("40");
        assertThat(diagnostic(diagnostics, "京东").get("errorMessage").asText()).contains("invalid app key");

        JsonNode pddDiagnostics = getJson(token, "/api/ecommerce/diagnostics?query=吹风机&pageSize=2&platforms=pdd&minPrice=100.00&maxPrice=200.00&withCoupon=true&officialOnly=true&sortBy=price_asc").get("data");
        assertThat(pddDiagnostics.get("providers").size()).isEqualTo(1);
        assertThat(diagnostic(pddDiagnostics, "拼多多").get("success").asBoolean()).isTrue();
        assertThat(lastRequest).containsEntry("with_coupon", "true");
        assertThat(lastRequest).containsEntry("merchant_type", "3");
        assertThat(lastRequest).containsEntry("sort_type", "3");
        assertThat(lastRequest.get("range_list")).contains("\"range_from\":10000", "\"range_to\":20000");

        JsonNode pddBusinessError = getJson(token, "/api/ecommerce/diagnostics?query=业务错误&pageSize=2&platforms=pdd").get("data");
        assertThat(diagnostic(pddBusinessError, "拼多多").get("success").asBoolean()).isFalse();
        assertThat(diagnostic(pddBusinessError, "拼多多").get("errorCode").asText()).isEqualTo("10019");
        assertThat(diagnostic(pddBusinessError, "拼多多").get("errorMessage").asText()).contains("invalid client id");

        JsonNode pddHttpError = getJson(token, "/api/ecommerce/diagnostics?query=HTTP错误&pageSize=2&platforms=pdd").get("data");
        assertThat(diagnostic(pddHttpError, "拼多多").get("success").asBoolean()).isFalse();
        assertThat(diagnostic(pddHttpError, "拼多多").get("errorCode").asText()).isEqualTo("http_503");
        assertThat(diagnostic(pddHttpError, "拼多多").get("errorMessage").asText()).contains("http 503", "temporary upstream outage");
        assertThat(diagnostic(pddHttpError, "拼多多").get("errorMessage").asText()).contains("[redacted]");
        assertThat(diagnostic(pddHttpError, "拼多多").get("errorMessage").asText())
                .doesNotContain("test-client", lastRequest.get("sign"));

        JsonNode unsupportedDiagnostics = getJson(token, "/api/ecommerce/diagnostics?query=吹风机&pageSize=2&platforms=taobao").get("data");
        assertThat(unsupportedDiagnostics.get("providers").size()).isEqualTo(1);
        assertThat(diagnostic(unsupportedDiagnostics, "淘宝").get("success").asBoolean()).isFalse();
        assertThat(diagnostic(unsupportedDiagnostics, "淘宝").get("status").asText()).isEqualTo("not_supported");
        assertThat(diagnostic(unsupportedDiagnostics, "淘宝").get("errorCode").asText()).isEqualTo("not_supported");
    }

    @Test
    void officialApiSearchMapsJdUnionResults() throws Exception {
        String token = registerAndToken();

        JsonNode search = postJson(token, "/api/search-tasks", Map.of(
                "query", "京东成功耳机",
                "sourceType", "official_api",
                "platforms", java.util.List.of("jd"),
                "sortBy", "rating_desc",
                "filters", Map.of(
                        "minPrice", Map.of("amount", "100.00", "currency", "CNY"),
                        "maxPrice", "500.00",
                        "withCoupon", "true",
                        "selfOperatedOnly", true
                )
        )).get("data");

        JsonNode first = search.get("items").get(0);
        assertThat(first.get("platform").asText()).isEqualTo("京东");
        assertThat(first.get("sourceType").asText()).isEqualTo("official_api");
        assertThat(first.get("title").asText()).contains("降噪耳机");
        assertThat(first.get("price").get("amount").asText()).isEqualTo("279.00");
        assertThat(first.get("originalPrice").get("amount").asText()).isEqualTo("399.00");
        assertThat(first.get("url").asText()).isEqualTo("https://item.jd.com/987654321.html");
        assertThat(first.get("imageUrl").asText()).isEqualTo("https://img.example.test/jd-headphone.jpg");
        assertThat(first.get("shopName").asText()).contains("Mock品牌旗舰店");
        assertThat(first.get("isSelfOperated").asBoolean()).isTrue();
        assertThat(first.get("rating").asDouble()).isEqualTo(4.9);

        assertThat(lastJdRequest).containsEntry("method", "jd.union.open.goods.query");
        assertThat(lastJdRequest).containsEntry("app_key", "test-jd-key");
        assertThat(lastJdRequest).containsKey("360buy_param_json");
        assertThat(lastJdRequest).doesNotContainKey("param_json");
        assertThat(lastJdRequest.get("sign")).isNotBlank();
        JsonNode paramJson = objectMapper.readTree(lastJdRequest.get("360buy_param_json"));
        assertThat(paramJson.path("goodsReqDTO").path("keyword").asText()).isEqualTo("京东成功耳机");
        assertThat(paramJson.path("goodsReqDTO").path("siteId").asLong()).isEqualTo(12345L);
        assertThat(paramJson.path("goodsReqDTO").path("positionId").asLong()).isEqualTo(67890L);
        assertThat(paramJson.path("goodsReqDTO").path("sortName").asText()).isEqualTo("goodCommentsShare");
        assertThat(paramJson.path("goodsReqDTO").path("sort").asText()).isEqualTo("desc");
        assertThat(paramJson.path("goodsReqDTO").path("pricefrom").asText()).isEqualTo("100");
        assertThat(paramJson.path("goodsReqDTO").path("priceto").asText()).isEqualTo("500");
        assertThat(paramJson.path("goodsReqDTO").path("isCoupon").asInt()).isEqualTo(1);
        assertThat(paramJson.path("goodsReqDTO").path("owner").asText()).isEqualTo("g");

        JsonNode diagnostics = getJson(token, "/api/ecommerce/diagnostics?query=京东成功耳机&pageSize=2&platforms=jd&minPrice=100.00&maxPrice=500.00&withCoupon=true&selfOperatedOnly=true&sortBy=rating_desc").get("data");
        assertThat(diagnostics.get("providers").size()).isEqualTo(1);
        assertThat(diagnostic(diagnostics, "京东").get("success").asBoolean()).isTrue();
        assertThat(diagnostic(diagnostics, "京东").get("itemCount").asInt()).isEqualTo(1);
        assertThat(diagnostic(diagnostics, "京东").get("sampleTitles").get(0).asText()).contains("降噪耳机");
        JsonNode diagnosticParamJson = objectMapper.readTree(lastJdRequest.get("360buy_param_json"));
        assertThat(diagnosticParamJson.path("goodsReqDTO").path("sortName").asText()).isEqualTo("goodCommentsShare");
        assertThat(diagnosticParamJson.path("goodsReqDTO").path("sort").asText()).isEqualTo("desc");
        assertThat(diagnosticParamJson.path("goodsReqDTO").path("pricefrom").asText()).isEqualTo("100");
        assertThat(diagnosticParamJson.path("goodsReqDTO").path("priceto").asText()).isEqualTo("500");
        assertThat(diagnosticParamJson.path("goodsReqDTO").path("isCoupon").asInt()).isEqualTo(1);
        assertThat(diagnosticParamJson.path("goodsReqDTO").path("owner").asText()).isEqualTo("g");

        JsonNode compatSearch = postJson(token, "/api/search-tasks", Map.of(
                "query", "京东兼容耳机",
                "sourceType", "official_api",
                "platforms", java.util.List.of("jd")
        )).get("data");
        JsonNode compatItem = compatSearch.get("items").get(0);
        assertThat(compatItem.get("platform").asText()).isEqualTo("京东");
        assertThat(compatItem.get("sourceType").asText()).isEqualTo("official_api");
        assertThat(compatItem.get("title").asText()).contains("兼容");
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
                if (lastRequest.getOrDefault("keyword", "").contains("业务错误")) {
                    byte[] response = """
                            {
                              "error_response": {
                                "error_code": 10019,
                                "error_msg": "invalid client id or permission"
                              }
                            }
                            """.getBytes(StandardCharsets.UTF_8);
                    exchange.getResponseHeaders().add("Content-Type", "application/json;charset=UTF-8");
                    exchange.sendResponseHeaders(200, response.length);
                    exchange.getResponseBody().write(response);
                    exchange.close();
                    return;
                }
                if (lastRequest.getOrDefault("keyword", "").contains("HTTP错误")) {
                    byte[] response = """
                            {
                              "error": "temporary upstream outage",
                              "client_id": "%s",
                              "sign": "%s"
                            }
                            """.formatted(lastRequest.get("client_id"), lastRequest.get("sign")).getBytes(StandardCharsets.UTF_8);
                    exchange.getResponseHeaders().add("Content-Type", "application/json;charset=UTF-8");
                    exchange.sendResponseHeaders(503, response.length);
                    exchange.getResponseBody().write(response);
                    exchange.close();
                    return;
                }
                if (lastRequest.getOrDefault("keyword", "").contains("签名商品")) {
                    byte[] response = """
                            {
                              "goods_search_response": {
                                "goods_list": [
                                  {
                                    "goods_sign": "test-sign-only",
                                    "goods_name": "只返回 goods_sign 的拼多多签名商品",
                                    "goods_thumbnail_url": "https://img.example.test/pdd-sign-only.jpg",
                                    "min_group_price": 8800,
                                    "min_normal_price": 9900,
                                    "mall_name": "签名官方旗舰店",
                                    "sales_tip": "800+件",
                                    "avg_desc": "4.8"
                                  }
                                ]
                              }
                            }
                            """.getBytes(StandardCharsets.UTF_8);
                    exchange.getResponseHeaders().add("Content-Type", "application/json;charset=UTF-8");
                    exchange.sendResponseHeaders(200, response.length);
                    exchange.getResponseBody().write(response);
                    exchange.close();
                    return;
                }
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
            server.createContext("/jd/router", exchange -> {
                byte[] requestBytes = exchange.getRequestBody().readAllBytes();
                lastJdRequest.clear();
                lastJdRequest.putAll(parseForm(new String(requestBytes, StandardCharsets.UTF_8)));
                String paramJson = lastJdRequest.getOrDefault("360buy_param_json", "");
                byte[] response;
                if (paramJson.contains("京东兼容")) {
                    response = """
                            {
                              "jd_union_open_goods_query_responce": {
                                "code": "0",
                                "result": "{\\"code\\":200,\\"data\\":[{\\"skuId\\":1122334455,\\"skuName\\":\\"京东兼容响应耳机\\",\\"imageInfo\\":{\\"imageList\\":[{\\"url\\":\\"//img.example.test/jd-compat-headphone.jpg\\"}]},\\"priceInfo\\":{\\"price\\":\\"199.00\\"},\\"shopInfo\\":{\\"shopName\\":\\"京东自营旗舰店\\"},\\"inOrderCount30Days\\":456,\\"goodCommentsShare\\":\\"96\\",\\"isJdSale\\":1,\\"materialUrl\\":\\"https://item.jd.com/1122334455.html\\"}]}"
                              }
                            }
                            """.getBytes(StandardCharsets.UTF_8);
                } else if (paramJson.contains("京东成功")) {
                    response = """
                            {
                              "jd_union_open_goods_query_response": {
                                "code": "0",
                                "result": "{\\"code\\":200,\\"data\\":[{\\"skuId\\":987654321,\\"skuName\\":\\"京东官方降噪耳机 Pro\\",\\"imageInfo\\":{\\"imageList\\":[{\\"url\\":\\"//img.example.test/jd-headphone.jpg\\"}]},\\"priceInfo\\":{\\"price\\":\\"299.00\\",\\"lowestCouponPrice\\":\\"279.00\\",\\"originPrice\\":\\"399.00\\"},\\"shopInfo\\":{\\"shopName\\":\\"Mock品牌旗舰店\\"},\\"inOrderCount30Days\\":1234,\\"goodCommentsShare\\":\\"98\\",\\"owner\\":\\"g\\",\\"materialUrl\\":\\"https://item.jd.com/987654321.html\\"}]}"
                              }
                            }
                            """.getBytes(StandardCharsets.UTF_8);
                } else {
                    response = """
                            {
                              "error_response": {
                                "code": "40",
                                "zh_desc": "invalid app key or permission"
                              }
                            }
                            """.getBytes(StandardCharsets.UTF_8);
                }
                exchange.getResponseHeaders().add("Content-Type", "application/json;charset=UTF-8");
                exchange.sendResponseHeaders(200, response.length);
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
