package com.ec26b.shoppingagent;

import com.ec26b.shoppingagent.ai.ArkClient;
import com.ec26b.shoppingagent.ai.ArkRecognitionProvider;
import com.ec26b.shoppingagent.ai.ArkRefineProvider;
import com.ec26b.shoppingagent.ai.FallbackRecognitionProvider;
import com.ec26b.shoppingagent.ai.FallbackRefineProvider;
import com.ec26b.shoppingagent.ai.ImagePayload;
import com.ec26b.shoppingagent.ai.MockRecognitionProvider;
import com.ec26b.shoppingagent.ai.RuleBasedRefineProvider;
import com.ec26b.shoppingagent.service.MockCatalog;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
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

    private String registerAndToken() throws Exception {
        JsonNode response = postJson(null, "/api/auth/register", Map.of(
                "username", "u" + UUID.randomUUID().toString().replace("-", "").substring(0, 12),
                "password", "password123",
                "nickname", "Tester"
        ));
        return response.get("data").get("accessToken").asText();
    }

    private long uploadImage(String token) throws Exception {
        MockMultipartFile file = new MockMultipartFile("file", "hair-dryer.jpg", "image/jpeg", new byte[]{1, 2, 3});
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
}
