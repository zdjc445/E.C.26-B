package com.ec26b.shoppingagent.ai;

import com.ec26b.shoppingagent.api.ApiModels.Money;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

final class FilterSanitizer {
    private static final Set<String> SORT_MODES = Set.of("comprehensive", "price_asc", "sales_desc", "rating_desc");
    private static final Set<String> PLATFORMS = Set.of("jd", "taobao", "pdd", "tmall", "other");

    private FilterSanitizer() {
    }

    static Map<String, Object> sanitize(Map<String, Object> input) {
        Map<String, Object> filters = new LinkedHashMap<>();
        if (input == null || input.isEmpty()) {
            return filters;
        }
        putMoney(filters, "maxPrice", input.get("maxPrice"));
        putMoney(filters, "minPrice", input.get("minPrice"));
        putString(filters, "color", input.get("color"));
        putString(filters, "brand", input.get("brand"));
        putString(filters, "category", input.get("category"));
        putRating(filters, input.get("minRating"));
        putBoolean(filters, "officialOnly", input.get("officialOnly"));
        putBoolean(filters, "selfOperatedOnly", input.get("selfOperatedOnly"));
        putSort(filters, input.get("sortBy"));
        putPlatforms(filters, input.get("platforms"));
        return filters;
    }

    private static void putMoney(Map<String, Object> filters, String key, Object value) {
        BigDecimal amount = number(value);
        if (amount != null && amount.compareTo(BigDecimal.ZERO) >= 0) {
            filters.put(key, amount.setScale(2, RoundingMode.HALF_UP).toPlainString());
        }
    }

    private static void putString(Map<String, Object> filters, String key, Object value) {
        if (value == null) {
            return;
        }
        String text = String.valueOf(value).trim();
        if (!text.isBlank() && text.length() <= 64) {
            filters.put(key, text);
        }
    }

    private static void putRating(Map<String, Object> filters, Object value) {
        BigDecimal rating = number(value);
        if (rating != null) {
            BigDecimal clamped = rating.max(BigDecimal.ZERO).min(new BigDecimal("5.0"));
            filters.put("minRating", clamped.setScale(1, RoundingMode.HALF_UP).doubleValue());
        }
    }

    private static void putBoolean(Map<String, Object> filters, String key, Object value) {
        if (value instanceof Boolean bool) {
            if (bool) {
                filters.put(key, true);
            }
            return;
        }
        if (value != null && Boolean.parseBoolean(String.valueOf(value))) {
            filters.put(key, true);
        }
    }

    private static void putSort(Map<String, Object> filters, Object value) {
        if (value == null) {
            return;
        }
        String sortBy = String.valueOf(value).trim().toLowerCase(Locale.ROOT);
        if (SORT_MODES.contains(sortBy)) {
            filters.put("sortBy", sortBy);
        }
    }

    private static void putPlatforms(Map<String, Object> filters, Object value) {
        if (!(value instanceof List<?> list)) {
            return;
        }
        List<String> platforms = new ArrayList<>();
        for (Object item : list) {
            String platform = String.valueOf(item).trim().toLowerCase(Locale.ROOT);
            if (PLATFORMS.contains(platform) && !platforms.contains(platform)) {
                platforms.add(platform);
            }
        }
        if (!platforms.isEmpty()) {
            filters.put("platforms", platforms);
        }
    }

    private static BigDecimal number(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof Number number) {
            return BigDecimal.valueOf(number.doubleValue());
        }
        if (value instanceof Money money) {
            return new BigDecimal(money.amount());
        }
        String text = String.valueOf(value)
                .replace("CNY", "")
                .replace("元", "")
                .trim();
        if (text.isBlank()) {
            return null;
        }
        try {
            return new BigDecimal(text);
        } catch (NumberFormatException ex) {
            return null;
        }
    }
}
