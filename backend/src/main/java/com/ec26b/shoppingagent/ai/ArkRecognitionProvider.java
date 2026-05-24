package com.ec26b.shoppingagent.ai;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.Base64;
import java.util.List;
import java.util.Map;

public class ArkRecognitionProvider implements AiRecognitionProvider {
    private final ArkClient arkClient;
    private final ObjectMapper objectMapper;

    public ArkRecognitionProvider(ArkClient arkClient, ObjectMapper objectMapper) {
        this.arkClient = arkClient;
        this.objectMapper = objectMapper;
    }

    @Override
    public RecognitionResult recognize(ImagePayload image) {
        if (image.bytes() == null || image.bytes().length == 0) {
            throw new IllegalArgumentException("image bytes are required for Ark recognition");
        }
        String contentType = image.contentType() == null || image.contentType().isBlank() ? "image/jpeg" : image.contentType();
        String dataUrl = "data:" + contentType + ";base64," + Base64.getEncoder().encodeToString(image.bytes());
        List<Map<String, Object>> messages = List.of(
                Map.of(
                        "role", "system",
                        "content", "你是电商拍照识物助手。只输出 JSON，不要输出 Markdown。字段固定为 category, brand, model, keywords, attributes, confidence, explanation。confidence 为 0 到 1。attributes 是对象，优先包含 color、style、scenario、keySpecs。"
                ),
                Map.of(
                        "role", "user",
                        "content", List.of(
                                Map.of("type", "text", "text", "识别这张商品图片，生成可用于购物推荐和筛选的结构化结果。"),
                                Map.of("type", "image_url", "image_url", Map.of("url", dataUrl))
                        )
                )
        );
        JsonNode json = arkClient.chatJson(messages);
        Map<String, Object> attributes = objectMapper.convertValue(json.path("attributes"), new TypeReference<>() {
        });
        List<String> keywords = objectMapper.convertValue(json.path("keywords"), new TypeReference<>() {
        });
        return new RecognitionResult(
                text(json, "category", "未知商品"),
                text(json, "brand", null),
                text(json, "model", null),
                keywords == null ? List.of() : keywords,
                attributes == null ? Map.of() : attributes,
                clamp(json.path("confidence").asDouble(0.7)),
                providerName(),
                false,
                text(json, "explanation", "Ark VLM 根据图片生成识别结果。"),
                List.of()
        );
    }

    @Override
    public String providerName() {
        return "ark";
    }

    private String text(JsonNode json, String field, String fallback) {
        String value = json.path(field).asText("");
        return value.isBlank() ? fallback : value;
    }

    private double clamp(double value) {
        return Math.max(0, Math.min(1, value));
    }
}
