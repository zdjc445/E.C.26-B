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
import java.nio.charset.StandardCharsets;
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
        JsonNode search = postJson(token, "/api/search-tasks", Map.of(
                "query", query,
                "sourceType", "official_api",
                "sortBy", "price_asc"
        )).get("data");

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
}
