package com.ec26b.shoppingagent.product;

import com.ec26b.shoppingagent.ai.ArkClient;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public class ArkShoppingIntentParser implements ShoppingIntentParser {

    private final ArkClient arkClient;
    private final ObjectMapper objectMapper;
    private static final List<String> SUPPORTED = List.of("运动鞋", "耳机", "吹风机");

    public ArkShoppingIntentParser(ArkClient arkClient, ObjectMapper objectMapper) {
        this.arkClient = arkClient;
        this.objectMapper = objectMapper;
    }

    @Override
    public ShoppingIntent parse(String text) {
        List<Map<String, Object>> messages = List.of(
                Map.of("role", "system", "content",
                        "你是电商购物意图解析器。只输出 JSON。字段固定为：keyword(只能是 运动鞋/耳机/吹风机 之一), maxPrice(数字), color(字符串), officialStore(bool), fastDelivery(bool), lowestPrice(bool), highRating(bool), highSales(bool), needsClarification(bool), clarificationQuestion(字符串)。不要输出 Markdown，不要输出额外字段。"),
                Map.of("role", "user", "content", "分析这句话的购物意图：" + text)
        );
        JsonNode json = arkClient.chatJson(messages);

        String keyword = json.path("keyword").asText("");
        if (!SUPPORTED.contains(keyword)) keyword = RuleBasedShoppingIntentParser.extractKeyword(text);

        Double maxPrice = json.path("maxPrice").isNumber() ? json.path("maxPrice").asDouble() : null;
        String color = json.path("color").asText(null);
        boolean official = json.path("officialStore").asBoolean(false);
        boolean fast = json.path("fastDelivery").asBoolean(false);
        boolean low = json.path("lowestPrice").asBoolean(false);
        boolean rating = json.path("highRating").asBoolean(false);
        boolean sales = json.path("highSales").asBoolean(false);
        boolean needsClar = json.path("needsClarification").asBoolean(false);
        String clarQ = json.path("clarificationQuestion").asText(null);

        List<String> notices = new ArrayList<>();
        if (json.path("notices").isArray()) {
            json.path("notices").forEach(n -> notices.add(n.asText()));
        }

        return new ShoppingIntent(keyword, maxPrice, color, official, fast, low, rating, sales,
                needsClar, clarQ, providerName(), false, notices);
    }

    @Override
    public String providerName() {
        return "ark";
    }
}
