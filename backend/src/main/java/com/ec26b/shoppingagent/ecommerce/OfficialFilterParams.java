package com.ec26b.shoppingagent.ecommerce;

import com.ec26b.shoppingagent.api.ApiModels.Money;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Map;

final class OfficialFilterParams {
    private OfficialFilterParams() {
    }

    static BigDecimal moneyFilter(ProductSourceQuery query, String key) {
        if (query == null || query.filters() == null) {
            return null;
        }
        return number(query.filters().get(key));
    }

    static boolean boolFilter(ProductSourceQuery query, String... keys) {
        if (query == null || query.filters() == null) {
            return false;
        }
        for (String key : keys) {
            if (truthy(query.filters().get(key))) {
                return true;
            }
        }
        return false;
    }

    static String decimalString(BigDecimal value) {
        return value.stripTrailingZeros().toPlainString();
    }

    static String centsString(BigDecimal yuan) {
        return yuan.multiply(BigDecimal.valueOf(100))
                .setScale(0, RoundingMode.HALF_UP)
                .toPlainString();
    }

    private static BigDecimal number(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof Number number) {
            return BigDecimal.valueOf(number.doubleValue());
        }
        if (value instanceof Money money) {
            return parse(money.amount());
        }
        if (value instanceof Map<?, ?> map && map.containsKey("amount")) {
            return number(map.get("amount"));
        }
        return parse(String.valueOf(value)
                .replace("CNY", "")
                .replace("RMB", "")
                .replace("￥", "")
                .replace("¥", "")
                .replace("元", "")
                .replace(",", "")
                .trim());
    }

    private static BigDecimal parse(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        try {
            return new BigDecimal(value);
        } catch (NumberFormatException ignored) {
            return null;
        }
    }

    private static boolean truthy(Object value) {
        if (value instanceof Boolean bool) {
            return bool;
        }
        if (value instanceof Number number) {
            return number.intValue() != 0;
        }
        if (value == null) {
            return false;
        }
        String normalized = String.valueOf(value).trim().toLowerCase();
        return "true".equals(normalized)
                || "1".equals(normalized)
                || "yes".equals(normalized)
                || "on".equals(normalized);
    }
}
