package com.ec26b.shoppingagent.product;

import java.util.ArrayList;
import java.util.List;

public record ProductOffer(
        String productId,
        String title,
        String platform,
        double price,
        double originalPrice,
        String shopName,
        String imageUrl,
        String productUrl,
        double rating,
        int sales,
        List<String> tags,
        List<String> reasons,
        double score,
        String brand,
        List<Double> priceHistory,
        List<String> matchedPreferences
) {

    public ProductOffer {
        tags = tags == null ? List.of() : List.copyOf(tags);
        reasons = reasons == null ? List.of() : List.copyOf(reasons);
        priceHistory = priceHistory == null ? List.of() : List.copyOf(priceHistory);
        matchedPreferences = matchedPreferences == null ? List.of() : List.copyOf(matchedPreferences);
    }

    public ProductOffer(String productId, String title, String platform,
                        double price, double originalPrice, String shopName,
                        String imageUrl, String productUrl,
                        double rating, int sales,
                        List<String> tags, List<String> reasons, double score) {
        this(productId, title, platform, price, originalPrice, shopName, imageUrl, productUrl,
                rating, sales, tags, reasons, score, null, List.of(), List.of());
    }

    public ProductOffer(String productId, String title, String platform,
                        double price, double originalPrice, String shopName,
                        String imageUrl, String productUrl,
                        double rating, int sales,
                        List<String> tags, List<String> reasons, double score,
                        String brand) {
        this(productId, title, platform, price, originalPrice, shopName, imageUrl, productUrl,
                rating, sales, tags, reasons, score, brand, defaultPriceHistory(price, originalPrice), List.of());
    }

    public ProductOffer withScoringResult(double newScore, List<String> newReasons,
                                          List<String> matched) {
        List<String> mergedReasons = new ArrayList<>(this.reasons);
        for (String r : newReasons) {
            if (!mergedReasons.contains(r)) mergedReasons.add(r);
        }
        return new ProductOffer(productId, title, platform, price, originalPrice, shopName,
                imageUrl, productUrl, rating, sales, tags, mergedReasons, newScore,
                brand, priceHistory, matched);
    }

    private static List<Double> defaultPriceHistory(double price, double originalPrice) {
        if (price <= 0) return List.of();
        double base = originalPrice > price ? originalPrice : price * 1.15;
        return List.of(
                round(base),
                round(base * 0.97),
                round((base + price) / 2.0),
                round(price * 1.05),
                round(price)
        );
    }

    private static double round(double v) {
        return Math.round(v * 100.0) / 100.0;
    }
}
