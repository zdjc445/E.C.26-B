package com.ec26b.shoppingagent.ecommerce;

import com.ec26b.shoppingagent.api.ApiModels.Money;
import com.ec26b.shoppingagent.service.MockCatalog;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.net.http.HttpClient;
import java.time.Duration;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;

@Component
public class JdUnionApiClient implements OfficialApiClient {
    private static final DateTimeFormatter TIMESTAMP_FORMAT = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    private final EcommerceApiProperties properties;
    private final ObjectMapper objectMapper;
    private final HttpClient httpClient;

    public JdUnionApiClient(EcommerceApiProperties properties, ObjectMapper objectMapper) {
        this.properties = properties;
        this.objectMapper = objectMapper;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(Math.max(1, properties.getRequestTimeoutSeconds())))
                .build();
    }

    @Override
    public String platform() {
        return "京东";
    }

    @Override
    public boolean configured() {
        EcommerceApiProperties.Jd jd = properties.getJd();
        return properties.isEnabled()
                && jd.isEnabled()
                && OfficialCredentialValue.present(jd.getAppKey())
                && OfficialCredentialValue.present(jd.getAppSecret());
    }

    @Override
    public List<OfficialProductResult> search(ProductSourceQuery query) {
        if (!configured() || isBlank(query.keyword())) {
            return List.of();
        }
        EcommerceApiProperties.Jd jd = properties.getJd();
        try {
            Map<String, Object> goodsReq = new LinkedHashMap<>();
            goodsReq.put("keyword", query.keyword());
            goodsReq.put("pageIndex", 1);
            goodsReq.put("pageSize", Math.max(1, Math.min(30, query.pageSize())));
            putLongIfPresent(goodsReq, "siteId", jd.getSiteId());
            putLongIfPresent(goodsReq, "positionId", jd.getPositionId());
            applySort(goodsReq, query.sortBy());
            applyFilters(goodsReq, query);
            Map<String, Object> paramJson = Map.of("goodsReqDTO", goodsReq);

            Map<String, String> params = new LinkedHashMap<>();
            params.put("method", jd.getMethod());
            params.put("app_key", jd.getAppKey());
            params.put("timestamp", LocalDateTime.now().format(TIMESTAMP_FORMAT));
            params.put("format", "json");
            params.put("v", "1.0");
            params.put("sign_method", "md5");
            params.put("param_json", objectMapper.writeValueAsString(paramJson));
            if (OfficialCredentialValue.present(jd.getAccessToken())) {
                params.put("access_token", jd.getAccessToken());
            }
            params.put("sign", EcommerceSigning.md5SignWithSecretWrap(params, jd.getAppSecret()));

            String body = EcommerceHttp.postForm(httpClient, jd.getBaseUrl(), params, Duration.ofSeconds(Math.max(1, properties.getRequestTimeoutSeconds())));
            return parseResponse(body, query);
        } catch (RuntimeException ex) {
            throw ex;
        } catch (Exception ex) {
            throw new IllegalStateException("JD official API parse failed", ex);
        }
    }

    private void applySort(Map<String, Object> goodsReq, String sortBy) {
        String normalized = sortBy == null ? "" : sortBy.toLowerCase(Locale.ROOT);
        if ("price_asc".equals(normalized)) {
            goodsReq.put("sortName", "price");
            goodsReq.put("sort", "asc");
        } else if ("sales_desc".equals(normalized)) {
            goodsReq.put("sortName", "inOrderCount30Days");
            goodsReq.put("sort", "desc");
        } else if ("rating_desc".equals(normalized)) {
            goodsReq.put("sortName", "goodCommentsShare");
            goodsReq.put("sort", "desc");
        }
    }

    private void putLongIfPresent(Map<String, Object> goodsReq, String key, String value) {
        if (OfficialCredentialValue.missing(value)) {
            return;
        }
        try {
            goodsReq.put(key, Long.parseLong(value.trim()));
        } catch (NumberFormatException ex) {
            goodsReq.put(key, value.trim());
        }
    }

    private void applyFilters(Map<String, Object> goodsReq, ProductSourceQuery query) {
        BigDecimal minPrice = OfficialFilterParams.moneyFilter(query, "minPrice");
        BigDecimal maxPrice = OfficialFilterParams.moneyFilter(query, "maxPrice");
        if (minPrice != null) {
            goodsReq.put("pricefrom", OfficialFilterParams.decimalString(minPrice));
        }
        if (maxPrice != null) {
            goodsReq.put("priceto", OfficialFilterParams.decimalString(maxPrice));
        }
        if (OfficialFilterParams.boolFilter(query, "withCoupon", "couponOnly", "hasCoupon")) {
            goodsReq.put("isCoupon", 1);
        }
        if (OfficialFilterParams.boolFilter(query, "selfOperatedOnly")) {
            goodsReq.put("owner", "g");
        }
    }

    private List<OfficialProductResult> parseResponse(String body, ProductSourceQuery query) throws Exception {
        JsonNode root = objectMapper.readTree(body);
        detectTopLevelError(root);
        JsonNode response = root.path("jd_union_open_goods_query_response");
        detectResponseError(response);
        JsonNode result = response.path("result");
        if (result.isTextual()) {
            result = objectMapper.readTree(result.asText());
        }
        detectResultError(result);
        JsonNode data = result.path("data");
        if (!data.isArray()) {
            data = response.path("data");
        }
        if (!data.isArray()) {
            return List.of();
        }
        List<OfficialProductResult> items = new ArrayList<>();
        for (JsonNode node : data) {
            String skuId = text(node, "skuId", "sku_id", "wareId");
            if (isBlank(skuId)) {
                continue;
            }
            String title = firstNonBlank(text(node, "skuName", "sku_name", "title"), query.keyword());
            String imageUrl = imageUrl(node.path("imageInfo").path("imageList"));
            if (isBlank(imageUrl)) {
                imageUrl = text(node, "imageUrl", "image_url");
            }
            String url = firstNonBlank(text(node, "materialUrl", "material_url", "url"), "https://item.jd.com/" + skuId + ".html");
            Money price = money(firstNonBlank(
                    text(node.path("priceInfo"), "price"),
                    text(node.path("priceInfo"), "lowestPrice"),
                    text(node, "price")
            ));
            Money originalPrice = money(firstNonBlank(
                    text(node.path("priceInfo"), "originPrice"),
                    text(node.path("priceInfo"), "lowestCouponPrice")
            ));
            String shopName = firstNonBlank(text(node.path("shopInfo"), "shopName"), "京东");
            int sales = intValue(node, "inOrderCount30Days", "comments", "commentCount");
            double rating = rating(node);
            boolean selfOperated = boolValue(node, "isJdSale") || contains(shopName, "京东自营");
            boolean official = contains(shopName, "旗舰") || selfOperated;
            Map<String, Object> attributes = new LinkedHashMap<>();
            attributes.put("externalSkuId", skuId);
            attributes.put("sourcePlatform", platform());
            if (!isBlank(query.category())) {
                attributes.put("category", query.category());
            }

            long productId = OfficialProductIds.productId(platform(), skuId);
            long platformProductId = OfficialProductIds.platformProductId(platform(), skuId);
            MockCatalog.ProductData product = new MockCatalog.ProductData(
                    productId,
                    title,
                    firstNonBlank(query.category(), "京东商品"),
                    firstNonBlank(query.brand(), platform()),
                    firstNonBlank(query.model(), skuId),
                    attributes
            );
            MockCatalog.PlatformProductData platformProduct = new MockCatalog.PlatformProductData(
                    platformProductId,
                    productId,
                    platform(),
                    title,
                    normalizeImage(imageUrl),
                    price,
                    originalPrice,
                    normalizeUrl(url),
                    shopName,
                    "official_api",
                    List.of("官方API", "京东", selfOperated ? "自营" : "第三方店铺"),
                    sales,
                    rating,
                    official,
                    selfOperated
            );
            MockCatalog.ReviewSummaryData review = new MockCatalog.ReviewSummaryData(
                    platformProductId,
                    rating,
                    sales,
                    List.of("来自京东官方接口商品数据"),
                    List.of(),
                    0.2,
                    "京东官方 API 返回的商品、价格、店铺和销量信息，评价摘要使用结构化字段兜底。"
            );
            items.add(new OfficialProductResult(product, platformProduct, Optional.of(review)));
        }
        return items;
    }

    private void detectTopLevelError(JsonNode root) {
        JsonNode error = firstObject(root.path("error_response"), root.path("errorResponse"), root.path("error"));
        if (error != null) {
            String code = errorCode(error);
            throw new OfficialApiException(code, "JD official API error: " + errorMessage(error));
        }
    }

    private void detectResponseError(JsonNode response) {
        String code = text(response, "code");
        if (!isBlank(code) && !"0".equals(code)) {
            throw new OfficialApiException(code, "JD official API error: " + responseMessage(response, code));
        }
    }

    private void detectResultError(JsonNode result) {
        String code = text(result, "code");
        if (isBlank(code) || "0".equals(code) || "200".equals(code)) {
            return;
        }
        throw new OfficialApiException(code, "JD official API error: " + responseMessage(result, code));
    }

    private JsonNode firstObject(JsonNode... nodes) {
        for (JsonNode node : nodes) {
            if (node != null && node.isObject() && !node.isEmpty()) {
                return node;
            }
        }
        return null;
    }

    private String errorMessage(JsonNode error) {
        String code = errorCode(error);
        String message = firstNonBlank(text(error, "zh_desc", "en_desc", "message", "msg", "error_msg", "errorMsg"), code);
        if (!isBlank(code) && !message.contains(code)) {
            return code + " " + message;
        }
        return isBlank(message) ? "unknown error" : message;
    }

    private String errorCode(JsonNode error) {
        return text(error, "code", "sub_code", "subCode");
    }

    private String responseMessage(JsonNode node, String code) {
        String message = firstNonBlank(text(node, "message", "msg", "zh_desc", "en_desc", "error_msg", "errorMsg"), code);
        if (!isBlank(code) && !message.contains(code)) {
            return code + " " + message;
        }
        return isBlank(message) ? "unknown error" : message;
    }

    private String imageUrl(JsonNode imageList) {
        if (!imageList.isArray() || imageList.isEmpty()) {
            return "";
        }
        return text(imageList.get(0), "url", "imageUrl");
    }

    private double rating(JsonNode node) {
        String value = firstNonBlank(text(node, "goodCommentsShare"), text(node.path("commentsInfo"), "goodRateShow"));
        if (isBlank(value)) {
            return 4.6;
        }
        BigDecimal raw = decimal(value);
        if (raw.compareTo(BigDecimal.ONE) <= 0) {
            return raw.multiply(BigDecimal.valueOf(5)).setScale(1, RoundingMode.HALF_UP).doubleValue();
        }
        if (raw.compareTo(BigDecimal.TEN) > 0) {
            return raw.divide(BigDecimal.valueOf(20), 1, RoundingMode.HALF_UP).doubleValue();
        }
        return Math.min(5.0, raw.doubleValue());
    }

    private Money money(String value) {
        if (isBlank(value)) {
            return new Money("0.00", "CNY");
        }
        return new Money(decimal(value).setScale(2, RoundingMode.HALF_UP).toPlainString(), "CNY");
    }

    private BigDecimal decimal(String value) {
        String cleaned = value == null ? "0" : value.replace("￥", "").replace("¥", "").replace(",", "").trim();
        if (cleaned.isBlank()) {
            return BigDecimal.ZERO;
        }
        return new BigDecimal(cleaned);
    }

    private int intValue(JsonNode node, String... names) {
        for (String name : names) {
            JsonNode value = node.path(name);
            if (value.isNumber()) {
                return value.asInt();
            }
            if (value.isTextual() && !value.asText().isBlank()) {
                return parseSales(value.asText());
            }
        }
        return 0;
    }

    private int parseSales(String value) {
        String text = value.replace("+", "").replace("件", "").replace("已售", "").trim();
        try {
            if (text.contains("万")) {
                return new BigDecimal(text.replace("万", "")).multiply(BigDecimal.valueOf(10_000)).intValue();
            }
            return new BigDecimal(text.replaceAll("[^0-9.]", "")).intValue();
        } catch (Exception ignored) {
            return 0;
        }
    }

    private boolean boolValue(JsonNode node, String name) {
        JsonNode value = node.path(name);
        if (value.isBoolean()) {
            return value.asBoolean();
        }
        if (value.isNumber()) {
            return value.asInt() == 1;
        }
        return "1".equals(value.asText()) || "true".equalsIgnoreCase(value.asText());
    }

    private String normalizeUrl(String value) {
        if (isBlank(value)) {
            return value;
        }
        if (value.startsWith("//")) {
            return "https:" + value;
        }
        if (!value.startsWith("http")) {
            return "https://" + value;
        }
        return value;
    }

    private String normalizeImage(String value) {
        return normalizeUrl(value);
    }

    private String text(JsonNode node, String... names) {
        for (String name : names) {
            JsonNode value = node.path(name);
            if (!value.isMissingNode() && !value.isNull() && !value.asText().isBlank()) {
                return value.asText();
            }
        }
        return "";
    }

    private String firstNonBlank(String... values) {
        for (String value : values) {
            if (!isBlank(value)) {
                return value;
            }
        }
        return "";
    }

    private boolean contains(String value, String keyword) {
        return value != null && keyword != null && value.toLowerCase(Locale.ROOT).contains(keyword.toLowerCase(Locale.ROOT));
    }

    private boolean isBlank(String value) {
        return value == null || value.isBlank();
    }
}
