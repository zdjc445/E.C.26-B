package com.ec26b.shoppingagent.product;

import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Rule-based parser that extracts structured shopping preferences from free text.
 * No AI — pure regex and keyword matching.
 */
@Component
public class UserPreferenceParser {

    private static final List<String> KNOWN_BRANDS = List.of(
            "耐克", "nike", "Nike", "NIKE",
            "阿迪达斯", "阿迪", "adidas", "Adidas",
            "李宁", "安踏", "新百伦", "newbalance", "New Balance",
            "索尼", "sony", "Sony", "SONY",
            "森海塞尔", "Sennheiser", "森海", "铁三角",
            "小米", "Xiaomi", "华为", "huawei", "Huawei",
            "苹果", "Apple", "戴森", "Dyson", "飞利浦", "Philips",
            "松下", "Panasonic"
    );

    public UserPreference parse(String text) {
        if (text == null || text.isBlank()) return UserPreference.empty();

        Double maxPrice = parseMaxPrice(text);
        String color = parseColor(text);
        boolean official = text.contains("官方") || text.contains("旗舰") || text.contains("自营");
        boolean fastDelivery = text.contains("配送快") || text.contains("物流快") || text.contains("尽快到");
        boolean lowestPrice = text.contains("低价") || text.contains("便宜") || text.contains("价格低") || text.contains("价格最低");
        boolean highRating = text.contains("评分高") || text.contains("好评") || text.contains("评价高");
        boolean highSales = text.contains("销量高") || text.contains("爆款") || text.contains("热销");
        String brand = parseBrand(text);
        List<String> platforms = parsePlatforms(text);
        String sortBy = parseSortBy(text);
        Double minRating = parseMinRating(text);

        return new UserPreference(maxPrice, color, official, fastDelivery,
                lowestPrice, highRating, highSales,
                brand, platforms, sortBy, minRating);
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

    private String parseBrand(String text) {
        for (String b : KNOWN_BRANDS) {
            if (text.toLowerCase().contains(b.toLowerCase())) {
                return canonicalBrand(b);
            }
        }
        return null;
    }

    private String canonicalBrand(String raw) {
        String lower = raw.toLowerCase();
        if (lower.equals("nike") || raw.equals("耐克")) return "耐克";
        if (lower.equals("adidas") || raw.equals("阿迪达斯") || raw.equals("阿迪")) return "阿迪达斯";
        if (lower.equals("newbalance") || lower.equals("new balance") || raw.equals("新百伦")) return "新百伦";
        if (lower.equals("sony") || raw.equals("索尼")) return "索尼";
        if (raw.equals("森海") || raw.equals("森海塞尔") || lower.equals("sennheiser")) return "森海塞尔";
        if (lower.equals("xiaomi") || raw.equals("小米")) return "小米";
        if (lower.equals("huawei") || raw.equals("华为")) return "华为";
        if (lower.equals("apple") || raw.equals("苹果")) return "苹果";
        if (lower.equals("dyson") || raw.equals("戴森")) return "戴森";
        if (lower.equals("philips") || raw.equals("飞利浦")) return "飞利浦";
        if (lower.equals("panasonic") || raw.equals("松下")) return "松下";
        return raw;
    }

    private List<String> parsePlatforms(String text) {
        List<String> result = new ArrayList<>();
        if (text.contains("京东") || text.contains("JD") || text.contains("jd")) result.add("京东-mock");
        if (text.contains("拼多多") || text.contains("PDD") || text.contains("pdd")) result.add("拼多多-mock");
        if (text.contains("淘宝")) result.add("淘宝-mock");
        if (text.contains("天猫")) result.add("天猫-mock");
        return result;
    }

    private String parseSortBy(String text) {
        if (text.contains("价格从低到高") || text.contains("价格升序") || text.contains("从便宜开始")
                || text.contains("价格最低") || text.contains("低价优先")) {
            return "price_asc";
        }
        if (text.contains("价格从高到低") || text.contains("价格降序")) {
            return "price_desc";
        }
        if (text.contains("销量优先") || text.contains("销量排序") || text.contains("按销量")) {
            return "sales_desc";
        }
        if (text.contains("好评率") || text.contains("评分优先") || text.contains("评分排序") || text.contains("按评分")) {
            return "rating_desc";
        }
        if (text.contains("综合推荐") || text.contains("综合排序")) {
            return "recommended";
        }
        return null;
    }

    private Double parseMinRating(String text) {
        Matcher m = Pattern.compile("(?:评分|好评|评价)[^0-9]{0,4}(\\d+(?:\\.\\d+)?)\\s*(?:分|星)?\\s*(?:以上|起|及以上|\\+)?")
                .matcher(text);
        if (m.find()) {
            try {
                double v = Double.parseDouble(m.group(1));
                if (v > 5) return null;
                return v;
            } catch (NumberFormatException e) {}
        }
        m = Pattern.compile("(\\d(?:\\.\\d+)?)\\s*(?:分|星)\\s*(?:以上|起|及以上|\\+)").matcher(text);
        if (m.find()) {
            try {
                double v = Double.parseDouble(m.group(1));
                if (v > 5) return null;
                return v;
            } catch (NumberFormatException e) {}
        }
        return null;
    }
}
