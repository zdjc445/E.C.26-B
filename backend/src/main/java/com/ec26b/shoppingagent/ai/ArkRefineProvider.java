package com.ec26b.shoppingagent.ai;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.List;
import java.util.Map;

public class ArkRefineProvider implements AiRefineProvider {
    private final ArkClient arkClient;
    private final ObjectMapper objectMapper;

    public ArkRefineProvider(ArkClient arkClient, ObjectMapper objectMapper) {
        this.arkClient = arkClient;
        this.objectMapper = objectMapper;
    }

    @Override
    public RefineParseResult parse(String text, Map<String, Object> existingFilters) {
        List<Map<String, Object>> messages = List.of(
                Map.of(
                        "role", "system",
                        "content", "你是电商搜索条件解析器。只输出 JSON 对象，字段只能包含 filters 和 notices。filters 只能包含 maxPrice, minPrice, color, brand, category, minRating, officialOnly, selfOperatedOnly, sortBy, platforms。sortBy 只能是 comprehensive, price_asc, sales_desc, rating_desc。platforms 只能包含 jd, taobao, pdd, tmall, other。"
                ),
                Map.of(
                        "role", "user",
                        "content", "已有筛选条件：" + existingFilters + "\n用户追加筛选：" + text
                )
        );
        JsonNode json = arkClient.chatJson(messages);
        Map<String, Object> rawFilters = objectMapper.convertValue(json.path("filters"), new TypeReference<>() {
        });
        List<String> notices = objectMapper.convertValue(json.path("notices"), new TypeReference<>() {
        });
        return new RefineParseResult(
                FilterSanitizer.sanitize(rawFilters),
                providerName(),
                false,
                notices == null ? List.of() : notices
        );
    }

    @Override
    public String providerName() {
        return "ark";
    }
}
