package com.ec26b.shoppingagent.product;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

final class ProductSearchResults {

    private ProductSearchResults() {
    }

    static ProductSearchResult fromProducts(List<ProductOffer> products, String sortBy) {
        List<ProductOffer> sorted = new ArrayList<>(products == null ? List.of() : products);
        sorted.sort(comparator(sortBy));

        Map<String, ProductSearchResult.PlatformStats> stats = new LinkedHashMap<>();
        for (String platform : sorted.stream().map(ProductOffer::platform).distinct().toList()) {
            List<ProductOffer> platformProducts = sorted.stream()
                    .filter(p -> p.platform().equals(platform))
                    .toList();
            if (!platformProducts.isEmpty()) {
                double lowest = platformProducts.stream()
                        .mapToDouble(ProductOffer::price).min().orElse(0);
                double avg = platformProducts.stream()
                        .mapToDouble(ProductOffer::price).average().orElse(0);
                stats.put(platform, new ProductSearchResult.PlatformStats(
                        platform, lowest, round(avg), platformProducts.size(), highlight(platform)));
            }
        }

        ProductOffer topPick = sorted.isEmpty() ? null : sorted.get(0);
        return new ProductSearchResult(sorted, stats, topPick);
    }

    static Comparator<ProductOffer> comparator(String sortBy) {
        return switch (sortBy == null ? "" : sortBy) {
            case "price_asc" -> Comparator.comparingDouble(ProductOffer::price);
            case "price_desc" -> Comparator.comparingDouble(ProductOffer::price).reversed();
            case "sales_desc" -> Comparator.comparingInt(ProductOffer::sales).reversed();
            case "rating_desc" -> Comparator.comparingDouble(ProductOffer::rating).reversed();
            default -> Comparator.comparingDouble(ProductOffer::score).reversed();
        };
    }

    private static String highlight(String platform) {
        return switch (platform) {
            case "京东-mock" -> "自营保障，物流快";
            case "拼多多-mock" -> "价格优势明显";
            case "淘宝-mock" -> "品类丰富，选择多";
            case "天猫-mock" -> "品牌旗舰，正品保障";
            default -> "";
        };
    }

    private static double round(double v) {
        return Math.round(v * 100.0) / 100.0;
    }
}
