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
    private static final List<String> SUPPORTED_PLATFORMS = List.of("京东-mock", "拼多多-mock", "淘宝-mock", "天猫-mock");
    private static final List<String> SUPPORTED_SORT = List.of(
            "recommended", "price_asc", "price_desc", "sales_desc", "rating_desc");

    public ArkShoppingIntentParser(ArkClient arkClient, ObjectMapper objectMapper) {
        this.arkClient = arkClient;
        this.objectMapper = objectMapper;
    }

    @Override
    public ShoppingIntent parse(String text) {
        String categoryNames = String.join("/", CategoryResolver.defaultResolver().supportedCategoryNames());
        List<Map<String, Object>> messages = List.of(
                Map.of("role", "system", "content",
                        "你是电商购物意图解析器。只输出 JSON。字段固定为：" +
                        "keyword(只能是 " + categoryNames + " 之一)，" +
                        "maxPrice(数字)，color(字符串)，" +
                        "officialStore(bool)，fastDelivery(bool)，lowestPrice(bool)，" +
                        "highRating(bool)，highSales(bool)，" +
                        "brand(字符串，例如 耐克、阿迪达斯、索尼、小米、华为、苹果、戴森、飞利浦、松下、新百伦、森海塞尔)，" +
                        "platforms(字符串数组，元素只能是 京东-mock/拼多多-mock/淘宝-mock/天猫-mock)，" +
                        "sortBy(只能是 recommended/price_asc/price_desc/sales_desc/rating_desc 之一)，" +
                        "minRating(0-5 之间的小数)，" +
                        "needsClarification(bool)，clarificationQuestion(字符串)。" +
                        "不要输出 Markdown，不要输出额外字段。"),
                Map.of("role", "user", "content", "分析这句话的购物意图：" + text)
        );
        JsonNode json = arkClient.chatJson(messages);

        String keyword = CategoryResolver.defaultResolver().resolveName(json.path("keyword").asText(""));
        if (keyword == null) keyword = RuleBasedShoppingIntentParser.extractKeyword(text);

        Double maxPrice = json.path("maxPrice").isNumber() ? json.path("maxPrice").asDouble() : null;
        String color = json.path("color").isNull() ? null : json.path("color").asText(null);
        boolean official = json.path("officialStore").asBoolean(false);
        boolean fast = json.path("fastDelivery").asBoolean(false);
        boolean low = json.path("lowestPrice").asBoolean(false);
        boolean rating = json.path("highRating").asBoolean(false);
        boolean sales = json.path("highSales").asBoolean(false);
        String brand = json.path("brand").isNull() ? null : json.path("brand").asText(null);
        if (brand != null && brand.isBlank()) brand = null;

        List<String> platforms = new ArrayList<>();
        if (json.path("platforms").isArray()) {
            json.path("platforms").forEach(node -> {
                String pv = node.asText("");
                if (SUPPORTED_PLATFORMS.contains(pv)) platforms.add(pv);
            });
        }
        String sortBy = json.path("sortBy").asText(null);
        if (sortBy != null && (sortBy.isBlank() || !SUPPORTED_SORT.contains(sortBy))) sortBy = null;
        Double minRating = json.path("minRating").isNumber() ? json.path("minRating").asDouble() : null;
        if (minRating != null && (minRating < 0 || minRating > 5)) minRating = null;

        boolean needsClar = json.path("needsClarification").asBoolean(false);
        String clarQ = json.path("clarificationQuestion").asText(null);

        List<String> notices = new ArrayList<>();
        if (json.path("notices").isArray()) {
            json.path("notices").forEach(n -> notices.add(n.asText()));
        }

        return new ShoppingIntent(keyword, maxPrice, color, official, fast, low, rating, sales,
                brand, platforms, sortBy, minRating,
                needsClar, clarQ, providerName(), false, notices);
    }

    @Override
    public String providerName() {
        return "ark";
    }
}
