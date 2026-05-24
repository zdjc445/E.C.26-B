package com.ec26b.shoppingagent.ai;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;

import java.util.List;
import java.util.Map;

public class ArkClient {
    private final ObjectMapper objectMapper;
    private final RestClient restClient;
    private final String endpointId;
    private final boolean enabled;

    public ArkClient(ObjectMapper objectMapper, String apiKey, String endpointId, String baseUrl) {
        this.objectMapper = objectMapper;
        this.endpointId = endpointId == null ? "" : endpointId.trim();
        String key = apiKey == null ? "" : apiKey.trim();
        String normalizedBaseUrl = normalizeBaseUrl(baseUrl);
        this.enabled = !key.isBlank() && !this.endpointId.isBlank();
        this.restClient = RestClient.builder()
                .baseUrl(normalizedBaseUrl)
                .defaultHeader(HttpHeaders.AUTHORIZATION, "Bearer " + key)
                .build();
    }

    public JsonNode chatJson(List<Map<String, Object>> messages) {
        if (!enabled) {
            throw new IllegalStateException("Ark provider is not configured");
        }
        Map<String, Object> body = Map.of(
                "model", endpointId,
                "messages", messages,
                "temperature", 0.1,
                "response_format", Map.of("type", "json_object")
        );
        JsonNode response = restClient.post()
                .uri("/chat/completions")
                .contentType(MediaType.APPLICATION_JSON)
                .body(body)
                .retrieve()
                .body(JsonNode.class);
        String content = response == null ? "" : response.at("/choices/0/message/content").asText("");
        if (content.isBlank()) {
            throw new IllegalStateException("Ark response content is empty");
        }
        try {
            return objectMapper.readTree(extractJsonObject(content));
        } catch (Exception ex) {
            throw new IllegalStateException("Ark response is not valid JSON", ex);
        }
    }

    private String normalizeBaseUrl(String baseUrl) {
        String value = baseUrl == null || baseUrl.isBlank()
                ? "https://ark.cn-beijing.volces.com/api/v3"
                : baseUrl.trim();
        while (value.endsWith("/")) {
            value = value.substring(0, value.length() - 1);
        }
        if (value.endsWith("/chat/completions")) {
            return value.substring(0, value.length() - "/chat/completions".length());
        }
        return value;
    }

    private String extractJsonObject(String content) {
        String cleaned = content.trim();
        if (cleaned.startsWith("```")) {
            cleaned = cleaned.replaceFirst("^```(?:json)?", "").replaceFirst("```$", "").trim();
        }
        int start = cleaned.indexOf('{');
        int end = cleaned.lastIndexOf('}');
        if (start >= 0 && end > start) {
            return cleaned.substring(start, end + 1);
        }
        return cleaned;
    }
}
