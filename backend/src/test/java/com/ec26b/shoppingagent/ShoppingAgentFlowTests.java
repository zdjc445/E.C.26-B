package com.ec26b.shoppingagent;

import com.ec26b.shoppingagent.ai.ArkClient;
import com.ec26b.shoppingagent.ai.ArkRecognitionProvider;
import com.ec26b.shoppingagent.ai.ArkRefineProvider;
import com.ec26b.shoppingagent.ai.FallbackRecognitionProvider;
import com.ec26b.shoppingagent.ai.FallbackRefineProvider;
import com.ec26b.shoppingagent.ai.ImagePayload;
import com.ec26b.shoppingagent.ai.MockRecognitionProvider;
import com.ec26b.shoppingagent.ai.RuleBasedRefineProvider;
import com.ec26b.shoppingagent.api.ApiModels.*;
import com.ec26b.shoppingagent.persistence.ShoppingStateRepository;
import com.ec26b.shoppingagent.service.MockCatalog;
import com.ec26b.shoppingagent.service.ShoppingService.UserAccount;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ShoppingAgentFlowTests {
    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Autowired
    MockCatalog mockCatalog;

    @Autowired
    RecordingShoppingStateRepository persistence;

    @Test
    void fullShoppingFlowSupportsRefineCompareAndRecommendation() throws Exception {
        String token = registerAndToken();
        long imageId = uploadImage(token);
        JsonNode recognition = postJson(token, "/api/recognitions", Map.of("imageId", imageId)).get("data");
        JsonNode search = postJson(token, "/api/search-tasks", Map.of(
                "recognitionId", recognition.get("recognitionId").asLong(),
                "query", "500 元以内，适合宿舍用，噪音小一点",
                "sourceType", "mock",
                "sortBy", "comprehensive"
        )).get("data");

        JsonNode refine = postJson(token, "/api/search-tasks/" + search.get("searchTaskId").asLong() + "/refine", Map.of(
                "text", "1000 元以内的黑色款，要评价 4.8 分以上，只看官方",
                "sortBy", "rating_desc"
        )).get("data");

        assertThat(refine.get("items").size()).isGreaterThanOrEqualTo(1);
        assertThat(refine.get("filters").get("officialOnly").asBoolean()).isTrue();
        assertThat(refine.get("suggestionCards").size()).isGreaterThanOrEqualTo(3);
        assertThat(refine.get("aiProvider").asText()).isNotBlank();
        assertThat(refine.get("items").get(0).get("matchReasons").size()).isGreaterThanOrEqualTo(1);

        List<Long> ids = objectMapper.readerForListOf(Long.class)
                .readValue(objectMapper.writeValueAsString(refine.get("items").findValues("platformProductId")));
        JsonNode comparison = postJson(token, "/api/comparisons", Map.of(
                "searchTaskId", search.get("searchTaskId").asLong(),
                "platformProductIds", ids
        )).get("data");
        assertThat(comparison.get("platformStats").size()).isGreaterThanOrEqualTo(1);

        JsonNode recommendation = postJson(token, "/api/agent/recommendations", Map.of(
                "searchTaskId", search.get("searchTaskId").asLong(),
                "userQuery", "1000 元以内的黑色款，要评价 4.8 分以上",
                "candidateIds", ids
        )).get("data");
        assertThat(recommendation.get("evidence").size()).isGreaterThanOrEqualTo(3);
        assertThat(recommendation.get("decisionScore").asInt()).isBetween(0, 100);
        assertThat(recommendation.get("decisionSignals").size()).isEqualTo(5);
        assertThat(recommendation.get("decisionSignals").toString())
                .contains("match", "price", "reputation", "channel", "risk");
        assertThat(recommendation.get("decisionTrace").size()).isGreaterThanOrEqualTo(6);
        assertThat(recommendation.get("decisionTrace").toString())
                .contains("intent", "constraints", "retrieval", "market", "risk", "decision");
        assertThat(recommendation.get("candidateAnalyses").size()).isGreaterThanOrEqualTo(1);
        assertThat(recommendation.get("candidateAnalyses").get(0).get("verdict").asText()).isEqualTo("winner");
        assertThat(recommendation.get("candidateAnalyses").get(0).get("strengths").size()).isGreaterThanOrEqualTo(1);

        JsonNode report = getJson(token, "/api/agent/recommendations/" + recommendation.get("recommendationId").asLong() + "/report").get("data");
        assertThat(report.get("markdown").asText())
                .contains("购物决策证据报告", "五类决策信号", "六步决策轨迹", "候选胜因/败因矩阵", "Evidence")
                .contains("数据源：演示数据集")
                .contains("品牌 LumaCare", "模型 HD-001");
        assertThat(report.get("summary").asText()).contains("决策分");

        long selectedProductId = ids.get(0);
        JsonNode favorite = postJson(token, "/api/favorites", Map.of(
                "platformProductId", selectedProductId,
                "note", "答辩演示收藏"
        )).get("data");
        assertThat(favorite.get("platformProductId").asLong()).isEqualTo(selectedProductId);

        JsonNode favorites = getJson(token, "/api/favorites?page=1&pageSize=5").get("data");
        assertThat(favorites.get("items").size()).isGreaterThanOrEqualTo(1);

        JsonNode alert = postJson(token, "/api/price-alerts", Map.of(
                "platformProductId", selectedProductId,
                "targetPrice", Map.of("amount", "199.00", "currency", "CNY"),
                "enabled", true
        )).get("data");
        assertThat(alert.get("platformProductId").asLong()).isEqualTo(selectedProductId);
        assertThat(alert.get("targetPrice").get("amount").asText()).isEqualTo("199.00");

        JsonNode alerts = getJson(token, "/api/price-alerts?page=1&pageSize=5").get("data");
        assertThat(alerts.get("items").size()).isGreaterThanOrEqualTo(1);
    }

    @Test
    void fullShoppingFlowWritesPersistenceSnapshots() throws Exception {
        persistence.clear();

        String token = registerAndToken();
        long imageId = uploadImage(token);
        JsonNode recognition = postJson(token, "/api/recognitions", Map.of("imageId", imageId)).get("data");
        JsonNode search = postJson(token, "/api/search-tasks", Map.of(
                "recognitionId", recognition.get("recognitionId").asLong(),
                "query", "500 元以内，适合宿舍用",
                "sourceType", "mock"
        )).get("data");
        JsonNode refine = postJson(token, "/api/search-tasks/" + search.get("searchTaskId").asLong() + "/refine", Map.of(
                "text", "只看官方，按好评排序",
                "sortBy", "rating_desc"
        )).get("data");
        List<Long> ids = objectMapper.readerForListOf(Long.class)
                .readValue(objectMapper.writeValueAsString(refine.get("items").findValues("platformProductId")));
        JsonNode comparison = postJson(token, "/api/comparisons", Map.of(
                "searchTaskId", search.get("searchTaskId").asLong(),
                "platformProductIds", ids
        )).get("data");
        JsonNode recommendation = postJson(token, "/api/agent/recommendations", Map.of(
                "searchTaskId", search.get("searchTaskId").asLong(),
                "userQuery", "只看官方，按好评排序",
                "candidateIds", ids
        )).get("data");
        JsonNode favorite = postJson(token, "/api/favorites", Map.of(
                "platformProductId", ids.get(0),
                "note", "持久化验收"
        )).get("data");
        JsonNode alert = postJson(token, "/api/price-alerts", Map.of(
                "platformProductId", ids.get(0),
                "targetPrice", Map.of("amount", "199.00", "currency", "CNY"),
                "enabled", true
        )).get("data");

        deleteJson(token, "/api/favorites/" + favorite.get("favoriteId").asLong());
        deleteJson(token, "/api/price-alerts/" + alert.get("priceAlertId").asLong());

        assertThat(comparison.get("comparisonId").asLong()).isPositive();
        assertThat(recommendation.get("recommendationId").asLong()).isPositive();
        assertThat(persistence.count("saveUser")).isEqualTo(1);
        assertThat(persistence.count("saveRefreshSession")).isEqualTo(1);
        assertThat(persistence.count("saveImage")).isEqualTo(1);
        assertThat(persistence.count("saveRecognition")).isEqualTo(1);
        assertThat(persistence.count("saveSearchTask")).isGreaterThanOrEqualTo(2);
        assertThat(persistence.count("saveRefinement")).isEqualTo(1);
        assertThat(persistence.count("saveComparison")).isEqualTo(1);
        assertThat(persistence.count("saveRecommendation")).isEqualTo(1);
        assertThat(persistence.count("saveFavorite")).isEqualTo(1);
        assertThat(persistence.count("deleteFavorite")).isEqualTo(1);
        assertThat(persistence.count("savePriceAlert")).isEqualTo(1);
        assertThat(persistence.count("deletePriceAlert")).isEqualTo(1);
    }

    @Test
    void healthEndpointExposesRuntimeReadinessWithoutSecrets() throws Exception {
        JsonNode health = getJson(null, "/api/health").get("data");

        assertThat(health.get("status").asText()).isEqualTo("ok");
        assertThat(health.get("profile").asText()).isEqualTo("default");
        assertThat(health.get("dataset").get("productCount").asInt()).isGreaterThanOrEqualTo(6);
        assertThat(health.get("dataset").get("platformProductCount").asInt()).isGreaterThanOrEqualTo(12);
        assertThat(health.get("dataset").get("recognitionSampleCount").asInt()).isGreaterThanOrEqualTo(6);
        assertThat(health.get("dataset").get("categories").toString()).contains("耳机");
        assertThat(health.get("ai").get("recognitionProvider").asText()).isNotBlank();
        assertThat(health.get("ai").get("refineProvider").asText()).isNotBlank();
        assertThat(health.get("persistence").get("mode").asText()).isEqualTo("recording");
        assertThat(health.get("persistence").get("failFast").asBoolean()).isFalse();
        assertThat(health.get("ecommerce").has("providers")).isTrue();
        assertThat(health.toString()).doesNotContain("dev-only-change-me", "password123", "pdd-secret", "jd-secret");
    }

    @Test
    void arkProvidersFallbackWhenKeyIsMissing() {
        ArkClient unconfiguredArk = new ArkClient(objectMapper, "", "", "https://ark.cn-beijing.volces.com/api/v3");
        var recognitionProvider = new FallbackRecognitionProvider(
                new ArkRecognitionProvider(unconfiguredArk, objectMapper),
                new MockRecognitionProvider(mockCatalog)
        );
        var recognition = recognitionProvider.recognize(new ImagePayload(1001, "/uploads/hair-dryer.jpg", "image/jpeg", new byte[]{1, 2, 3}, "hair-dryer.jpg"));
        assertThat(recognition.provider()).isEqualTo("mock");
        assertThat(recognition.fallbackUsed()).isTrue();

        var refineProvider = new FallbackRefineProvider(
                new ArkRefineProvider(unconfiguredArk, objectMapper),
                new RuleBasedRefineProvider()
        );
        var parsed = refineProvider.parse("1000 元以内的黑色款，要评价 4.8 分以上，只看官方", Map.of());
        assertThat(parsed.provider()).isEqualTo("rule");
        assertThat(parsed.fallbackUsed()).isTrue();
        assertThat(parsed.filters()).containsEntry("officialOnly", true);
    }

    @Test
    void recognitionCannotBeReadAcrossUsers() throws Exception {
        String ownerToken = registerAndToken();
        String otherToken = registerAndToken();
        long imageId = uploadImage(ownerToken);
        JsonNode recognition = postJson(ownerToken, "/api/recognitions", Map.of("imageId", imageId)).get("data");

        mockMvc.perform(get("/api/recognitions/" + recognition.get("recognitionId").asLong())
                        .header("Authorization", "Bearer " + otherToken))
                .andExpect(status().isNotFound());
    }

    @Test
    void mockRecognitionSupportsMultipleDemoScenarios() throws Exception {
        String token = registerAndToken();
        long imageId = uploadImage(token, "headphones.jpg");
        JsonNode recognition = postJson(token, "/api/recognitions", Map.of("imageId", imageId)).get("data");
        assertThat(recognition.get("category").asText()).isEqualTo("耳机");
        assertThat(recognition.get("brand").asText()).isEqualTo("Auralis");
        assertThat(recognition.get("model").asText()).isEqualTo("ANC-20");
        assertThat(recognition.get("keywords").toString()).contains("主动降噪");

        JsonNode search = postJson(token, "/api/search-tasks", Map.of(
                "recognitionId", recognition.get("recognitionId").asLong(),
                "query", "500 元以内的黑色降噪耳机，要长续航，只看官方",
                "sourceType", "mock",
                "sortBy", "rating_desc"
        )).get("data");
        assertThat(search.get("items").size()).isGreaterThanOrEqualTo(3);
        assertThat(search.get("items").toString()).contains("Auralis");
        assertThat(search.get("items").toString()).contains("京东自营");
        assertThat(search.get("items").toString()).contains("官方补贴");
    }

    @Test
    void recognitionAttributesCanBeCorrectedByOwner() throws Exception {
        String token = registerAndToken();
        long imageId = uploadImage(token);
        JsonNode recognition = postJson(token, "/api/recognitions", Map.of("imageId", imageId)).get("data");

        JsonNode updated = patchJson(token, "/api/recognitions/" + recognition.get("recognitionId").asLong() + "/attributes", Map.of(
                "category", "电吹风",
                "brand", "LumaCare",
                "model", "HD-2026",
                "attributes", Map.of(
                        "color", "深蓝色",
                        "scenario", "宿舍",
                        "maxPower", 1600
                )
        )).get("data");

        assertThat(updated.get("category").asText()).isEqualTo("电吹风");
        assertThat(updated.get("brand").asText()).isEqualTo("LumaCare");
        assertThat(updated.get("model").asText()).isEqualTo("HD-2026");
        assertThat(updated.get("attributes").get("color").asText()).isEqualTo("深蓝色");
        assertThat(updated.get("attributes").get("maxPower").asInt()).isEqualTo(1600);
        assertThat(updated.get("suggestionCards").toString()).contains("相似电吹风推荐", "筛选：深蓝色");
    }

    @Test
    void officialApiFailsClearlyWhenNoProviderIsConfigured() throws Exception {
        JsonNode statusPayload = getJson(null, "/api/ecommerce/status").get("data");
        assertThat(statusPayload.get("enabled").asBoolean()).isFalse();
        assertThat(statusPayload.get("hasConfiguredClient").asBoolean()).isFalse();
        assertThat(statusPayload.get("providers").toString())
                .contains("ECOMMERCE_API_ENABLED")
                .contains("PDD_CLIENT_ID")
                .contains("JD_APP_KEY");

        String token = registerAndToken();
        JsonNode diagnostics = getJson(token, "/api/ecommerce/diagnostics?query=吹风机").get("data");
        assertThat(diagnostics.get("providers").toString())
                .contains("not_configured")
                .contains("ECOMMERCE_API_ENABLED");

        String content = mockMvc.perform(post("/api/search-tasks")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of(
                                "query", "吹风机",
                                "sourceType", "official_api"
                        )))
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isBadRequest())
                .andReturn().getResponse().getContentAsString();
        JsonNode response = objectMapper.readTree(content);
        assertThat(response.get("message").asText()).contains("official_api not configured");
    }

    private String registerAndToken() throws Exception {
        JsonNode response = postJson(null, "/api/auth/register", Map.of(
                "username", "u" + UUID.randomUUID().toString().replace("-", "").substring(0, 12),
                "password", "password123",
                "nickname", "Tester"
        ));
        return response.get("data").get("accessToken").asText();
    }

    private long uploadImage(String token) throws Exception {
        return uploadImage(token, "hair-dryer.jpg");
    }

    private long uploadImage(String token, String filename) throws Exception {
        MockMultipartFile file = new MockMultipartFile("file", filename, "image/jpeg", new byte[]{1, 2, 3});
        String content = mockMvc.perform(multipart("/api/images").file(file).param("scene", "recognition")
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
        return objectMapper.readTree(content).get("data").get("imageId").asLong();
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
                .andReturn().getResponse().getContentAsString();
        return objectMapper.readTree(content);
    }

    private JsonNode patchJson(String token, String path, Object body) throws Exception {
        var request = patch(path)
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(body));
        if (token != null) {
            request.header("Authorization", "Bearer " + token);
        }
        String content = mockMvc.perform(request)
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
        return objectMapper.readTree(content);
    }

    private JsonNode getJson(String token, String path) throws Exception {
        var request = get(path);
        if (token != null) {
            request.header("Authorization", "Bearer " + token);
        }
        String content = mockMvc.perform(request)
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
        return objectMapper.readTree(content);
    }

    private void deleteJson(String token, String path) throws Exception {
        var request = delete(path);
        if (token != null) {
            request.header("Authorization", "Bearer " + token);
        }
        mockMvc.perform(request)
                .andExpect(status().isOk());
    }

    @TestConfiguration
    static class PersistenceTestConfig {
        @Bean
        @Primary
        RecordingShoppingStateRepository recordingShoppingStateRepository() {
            return new RecordingShoppingStateRepository();
        }
    }

    static class RecordingShoppingStateRepository implements ShoppingStateRepository {
        private final Map<String, Integer> calls = new ConcurrentHashMap<>();

        int count(String method) {
            return calls.getOrDefault(method, 0);
        }

        void clear() {
            calls.clear();
        }

        private void record(String method) {
            calls.merge(method, 1, Integer::sum);
        }

        @Override
        public void saveUser(UserAccount user) {
            record("saveUser");
        }

        @Override
        public void saveRefreshSession(String refreshTokenHash, long userId) {
            record("saveRefreshSession");
        }

        @Override
        public void deleteRefreshSession(String refreshTokenHash) {
            record("deleteRefreshSession");
        }

        @Override
        public void saveImage(long userId, ImageDto image, boolean deleted) {
            record("saveImage");
        }

        @Override
        public void saveRecognition(long userId, RecognitionDto recognition) {
            record("saveRecognition");
        }

        @Override
        public void saveSearchTask(long userId, SearchTaskDto searchTask) {
            record("saveSearchTask");
        }

        @Override
        public void saveRefinement(long userId, RefineSearchTaskPayload refinement) {
            record("saveRefinement");
        }

        @Override
        public void saveComparison(long userId, ComparisonDto comparison) {
            record("saveComparison");
        }

        @Override
        public void saveRecommendation(long userId, RecommendationDto recommendation, String userQuery) {
            record("saveRecommendation");
        }

        @Override
        public void saveFavorite(long userId, FavoriteDto favorite) {
            record("saveFavorite");
        }

        @Override
        public void deleteFavorite(long userId, long favoriteId) {
            record("deleteFavorite");
        }

        @Override
        public void savePriceAlert(long userId, PriceAlertDto priceAlert) {
            record("savePriceAlert");
        }

        @Override
        public void deletePriceAlert(long userId, long priceAlertId) {
            record("deletePriceAlert");
        }
    }
}
