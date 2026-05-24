package com.ec26b.shoppingagent.ai;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class RuleBasedRefineProvider implements AiRefineProvider {
    @Override
    public RefineParseResult parse(String text, Map<String, Object> existingFilters) {
        Map<String, Object> filters = new LinkedHashMap<>();
        if (text == null || text.isBlank()) {
            return new RefineParseResult(filters, providerName(), false, List.of());
        }
        Matcher maxPrice = Pattern.compile("(\\d+(?:\\.\\d+)?)\\s*元?\\s*(以内|以下|内|之内)").matcher(text);
        Matcher maxPricePrefix = Pattern.compile("(不超过|低于|小于|少于)\\s*(\\d+(?:\\.\\d+)?)").matcher(text);
        if (maxPrice.find()) {
            filters.put("maxPrice", money(maxPrice.group(1)));
        } else if (maxPricePrefix.find()) {
            filters.put("maxPrice", money(maxPricePrefix.group(2)));
        }

        Matcher minPrice = Pattern.compile("(\\d+(?:\\.\\d+)?)\\s*元?\\s*(以上|起|及以上)").matcher(text);
        if (minPrice.find() && !text.contains("评分") && !text.contains("评价")) {
            filters.put("minPrice", money(minPrice.group(1)));
        }

        Matcher rating = Pattern.compile("(\\d(?:\\.\\d)?)\\s*分\\s*(以上|起|及以上)?").matcher(text);
        if (rating.find()) {
            filters.put("minRating", Double.parseDouble(rating.group(1)));
        }

        for (String color : List.of("深蓝色", "黑色", "白色", "蓝色", "银色", "红色", "绿色", "粉色", "灰色")) {
            if (text.contains(color)) {
                filters.put("color", color);
                break;
            }
        }
        if (text.contains("官方") || text.contains("旗舰")) {
            filters.put("officialOnly", true);
        }
        if (text.contains("自营")) {
            filters.put("selfOperatedOnly", true);
        }
        if (text.contains("低价") || text.contains("便宜") || text.contains("价格从低")) {
            filters.put("sortBy", "price_asc");
        } else if (text.contains("销量")) {
            filters.put("sortBy", "sales_desc");
        } else if (text.contains("好评") || text.contains("评分") || text.contains("评价")) {
            filters.put("sortBy", "rating_desc");
        }
        return new RefineParseResult(FilterSanitizer.sanitize(filters), providerName(), false, List.of());
    }

    @Override
    public String providerName() {
        return "rule";
    }

    private String money(String value) {
        return new BigDecimal(value).setScale(2, RoundingMode.HALF_UP).toPlainString();
    }
}
