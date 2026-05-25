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
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;

@Component
public class PddDdkApiClient implements OfficialApiClient {
    private final EcommerceApiProperties properties;
    private final ObjectMapper objectMapper;
    private final HttpClient httpClient;

    public PddDdkApiClient(EcommerceApiProperties properties, ObjectMapper objectMapper) {
        this.properties = properties;
        this.objectMapper = objectMapper;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(Math.max(1, properties.getRequestTimeoutSeconds())))
                .build();
    }

    @Override
    public String platform() {
        return "拼多多";
    }

    @Override
    public boolean configured() {
        EcommerceApiProperties.Pdd pdd = properties.getPdd();
        return properties.isEnabled()
                && pdd.isEnabled()
                && !isBlank(pdd.getClientId())
                && !isBlank(pdd.getClientSecret());
    }

    @Override
    public List<OfficialProductResult> search(ProductSourceQuery query) {
        if (!configured() || isBlank(query.keyword())) {
            return List.of();
        }
        EcommerceApiProperties.Pdd pdd = properties.getPdd();
        Map<String, String> params = new LinkedHashMap<>();
        params.put("type", pdd.getType());
        params.put("client_id", pdd.getClientId());
        params.put("timestamp", String.valueOf(Instant.now().getEpochSecond()));
        params.put("data_type", "JSON");
        params.put("keyword", query.keyword());
        params.put("page", "1");
        params.put("page_size", String.valueOf(Math.max(1, Math.min(30, query.pageSize()))));
        if (!isBlank(pdd.getPid())) {
            params.put("pid", pdd.getPid());
        }
        if (!isBlank(pdd.getCustomParameters())) {
            params.put("custom_parameters", pdd.getCustomParameters());
        }
        sortType(query.sortBy()).ifPresent(value -> params.put("sort_type", value));
        applyFilters(params, query);
        params.put("sign", EcommerceSigning.md5SignWithSecretWrap(params, pdd.getClientSecret()));

        String body = EcommerceHttp.postForm(httpClient, pdd.getBaseUrl(), params, Duration.ofSeconds(Math.max(1, properties.getRequestTimeoutSeconds())));
        try {
            return parseResponse(body, query);
        } catch (RuntimeException ex) {
            throw ex;
        } catch (Exception ex) {
            throw new IllegalStateException("PDD official API parse failed", ex);
        }
    }

    private Optional<String> sortType(String sortBy) {
        String normalized = sortBy == null ? "" : sortBy.toLowerCase(Locale.ROOT);
        return switch (normalized) {
            case "price_asc" -> Optional.of("3");
            case "sales_desc" -> Optional.of("6");
            default -> Optional.empty();
        };
    }

    private void applyFilters(Map<String, String> params, ProductSourceQuery query) {
        BigDecimal minPrice = OfficialFilterParams.moneyFilter(query, "minPrice");
        BigDecimal maxPrice = OfficialFilterParams.moneyFilter(query, "maxPrice");
        if (minPrice != null || maxPrice != null) {
            StringBuilder range = new StringBuilder("[{\"range_id\":0");
            if (minPrice != null) {
                range.append(",\"range_from\":").append(OfficialFilterParams.centsString(minPrice));
            }
            if (maxPrice != null) {
                range.append(",\"range_to\":").append(OfficialFilterParams.centsString(maxPrice));
            }
            range.append("}]");
            params.put("range_list", range.toString());
        }
        if (OfficialFilterParams.boolFilter(query, "withCoupon", "couponOnly", "hasCoupon")) {
            params.put("with_coupon", "true");
        }
        if (OfficialFilterParams.boolFilter(query, "officialOnly")) {
            params.put("merchant_type", "3");
        }
    }

    private List<OfficialProductResult> parseResponse(String body, ProductSourceQuery query) throws Exception {
        JsonNode root = objectMapper.readTree(body);
        detectError(root);
        JsonNode list = root.path("goods_search_response").path("goods_list");
        if (!list.isArray()) {
            list = root.path("goods_list");
        }
        if (!list.isArray()) {
            return List.of();
        }
        List<OfficialProductResult> items = new ArrayList<>();
        for (JsonNode node : list) {
            String goodsId = text(node, "goods_id", "goodsId");
            if (isBlank(goodsId)) {
                continue;
            }
            String title = firstNonBlank(text(node, "goods_name", "goodsName"), query.keyword());
            String imageUrl = text(node, "goods_thumbnail_url", "goods_image_url", "image_url");
            Money price = centsMoney(firstNonBlank(text(node, "min_group_price"), text(node, "min_normal_price"), text(node, "price")));
            Money originalPrice = centsMoney(firstNonBlank(text(node, "min_normal_price"), text(node, "market_fee")));
            String mallName = firstNonBlank(text(node, "mall_name", "mallName"), "拼多多店铺");
            int sales = parseSales(firstNonBlank(text(node, "sales_tip"), text(node, "sales"), text(node, "sold_quantity")));
            double rating = rating(firstNonBlank(text(node, "avg_desc"), text(node, "goods_eval_score")));
            boolean official = contains(mallName, "旗舰") || contains(title, "官方");
            Map<String, Object> attributes = new LinkedHashMap<>();
            attributes.put("externalGoodsId", goodsId);
            attributes.put("sourcePlatform", platform());
            String category = firstNonBlank(query.category(), text(node, "category_name", "opt_name"), "拼多多商品");
            attributes.put("category", category);
            String goodsSign = text(node, "goods_sign");
            if (!isBlank(goodsSign)) {
                attributes.put("goodsSign", goodsSign);
            }

            long productId = OfficialProductIds.productId(platform(), goodsId);
            long platformProductId = OfficialProductIds.platformProductId(platform(), goodsId);
            MockCatalog.ProductData product = new MockCatalog.ProductData(
                    productId,
                    title,
                    category,
                    firstNonBlank(query.brand(), platform()),
                    firstNonBlank(query.model(), goodsId),
                    attributes
            );
            MockCatalog.PlatformProductData platformProduct = new MockCatalog.PlatformProductData(
                    platformProductId,
                    productId,
                    platform(),
                    title,
                    normalizeUrl(imageUrl),
                    price,
                    originalPrice,
                    "https://mobile.yangkeduo.com/goods.html?goods_id=" + goodsId,
                    mallName,
                    "official_api",
                    List.of("官方API", "拼多多", official ? "官方店铺" : "平台店铺"),
                    sales,
                    rating,
                    official,
                    false
            );
            MockCatalog.ReviewSummaryData review = new MockCatalog.ReviewSummaryData(
                    platformProductId,
                    rating,
                    sales,
                    List.of("来自拼多多官方接口商品数据"),
                    List.of(),
                    0.22,
                    "拼多多官方 API 返回的商品、价格、店铺和销量信息，评价摘要使用结构化字段兜底。"
            );
            items.add(new OfficialProductResult(product, platformProduct, Optional.of(review)));
        }
        return items;
    }

    private void detectError(JsonNode root) {
        JsonNode error = firstObject(root.path("error_response"), root.path("errorResponse"), root.path("error"));
        if (error != null) {
            String code = errorCode(error);
            throw new OfficialApiException(code, "PDD official API error: " + errorMessage(error));
        }
        String code = text(root, "error_code", "errorCode", "code");
        String message = text(root, "error_msg", "errorMsg", "message", "msg");
        if (!isBlank(code) || !isBlank(message)) {
            throw new OfficialApiException(code, "PDD official API error: " + firstNonBlank(message, code));
        }
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
        String message = firstNonBlank(text(error, "error_msg", "errorMsg", "sub_msg", "subMsg", "message", "msg"), code);
        if (!isBlank(code) && !message.contains(code)) {
            return code + " " + message;
        }
        return isBlank(message) ? "unknown error" : message;
    }

    private String errorCode(JsonNode error) {
        return text(error, "error_code", "errorCode", "code", "sub_code", "subCode");
    }

    private Money centsMoney(String value) {
        if (isBlank(value)) {
            return new Money("0.00", "CNY");
        }
        BigDecimal raw = decimal(value);
        if (raw.compareTo(BigDecimal.valueOf(10_000)) > 0 || !value.contains(".")) {
            raw = raw.divide(BigDecimal.valueOf(100), 2, RoundingMode.HALF_UP);
        }
        return new Money(raw.setScale(2, RoundingMode.HALF_UP).toPlainString(), "CNY");
    }

    private BigDecimal decimal(String value) {
        String cleaned = value == null ? "0" : value.replace("￥", "").replace("¥", "").replace(",", "").trim();
        if (cleaned.isBlank()) {
            return BigDecimal.ZERO;
        }
        return new BigDecimal(cleaned);
    }

    private int parseSales(String value) {
        if (isBlank(value)) {
            return 0;
        }
        String text = value.replace("+", "").replace("件", "").replace("已拼", "").replace("已售", "").trim();
        try {
            if (text.contains("万")) {
                return decimal(text.replace("万", "")).multiply(BigDecimal.valueOf(10_000)).intValue();
            }
            String digits = text.replaceAll("[^0-9.]", "");
            return digits.isBlank() ? 0 : decimal(digits).intValue();
        } catch (Exception ignored) {
            return 0;
        }
    }

    private double rating(String value) {
        if (isBlank(value)) {
            return 4.6;
        }
        BigDecimal raw = decimal(value);
        if (raw.compareTo(BigDecimal.ONE) <= 0) {
            return raw.multiply(BigDecimal.valueOf(5)).setScale(1, RoundingMode.HALF_UP).doubleValue();
        }
        return Math.min(5.0, raw.doubleValue());
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
