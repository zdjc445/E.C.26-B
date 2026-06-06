package com.ec26b.shoppingagent.product;

import org.springframework.stereotype.Component;

import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Rule-based parser that extracts structured shopping preferences from free text.
 * No AI — pure regex and keyword matching.
 */
@Component
public class UserPreferenceParser {

    public UserPreference parse(String text) {
        if (text == null || text.isBlank()) return UserPreference.empty();

        Double maxPrice = parseMaxPrice(text);
        String color = parseColor(text);
        boolean official = text.contains("官方") || text.contains("旗舰") || text.contains("自营");
        boolean fastDelivery = text.contains("配送快") || text.contains("物流快") || text.contains("尽快到");
        boolean lowestPrice = text.contains("低价") || text.contains("便宜") || text.contains("价格低") || text.contains("价格最低");
        boolean highRating = text.contains("评分高") || text.contains("好评") || text.contains("评价高");
        boolean highSales = text.contains("销量高") || text.contains("爆款") || text.contains("热销");

        return new UserPreference(maxPrice, color, official, fastDelivery, lowestPrice, highRating, highSales);
    }

    private Double parseMaxPrice(String text) {
        Matcher m = Pattern.compile("(\\d+)\\s*(元|块)?\\s*(以内|以下|不超过|内)").matcher(text);
        if (m.find()) {
            try { return Double.parseDouble(m.group(1)); } catch (NumberFormatException e) {}
        }
        m = Pattern.compile("不超过\\s*(\\d+)").matcher(text);
        if (m.find()) {
            try { return Double.parseDouble(m.group(1)); } catch (NumberFormatException e) {}
        }
        m = Pattern.compile("预算\\s*(\\d+)").matcher(text);
        if (m.find()) {
            try { return Double.parseDouble(m.group(1)); } catch (NumberFormatException e) {}
        }
        return null;
    }

    private String parseColor(String text) {
        for (String c : List.of("深蓝色", "黑色", "白色", "蓝色", "银色", "红色", "绿色", "粉色", "灰色")) {
            if (text.contains(c)) return c;
        }
        return null;
    }
}
