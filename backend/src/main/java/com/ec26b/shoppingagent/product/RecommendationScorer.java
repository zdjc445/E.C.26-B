package com.ec26b.shoppingagent.product;

import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;

/**
 * Scores products based on user preferences and budget.
 * Pure rule-based, no AI. Tracks matched preferences for UI display.
 */
@Component
public class RecommendationScorer {

    public ProductOffer scoreProduct(ProductOffer product, List<String> preferences, Double maxPrice) {
        return scoreProduct(product, preferences, maxPrice, null);
    }

    public ProductOffer scoreProduct(ProductOffer product, List<String> preferences,
                                     Double maxPrice, UserPreference fullPref) {
        double base = 5.0;
        List<String> reasons = new ArrayList<>(product.reasons());
        List<String> matched = new ArrayList<>();

        for (String pref : preferences) {
            switch (pref) {
                case "lowest_price" -> {
                    if (product.price() < 250) {
                        base += 1.0;
                        reasons.add("价格优惠");
                        matched.add("low_price");
                    }
                }
                case "official_store" -> {
                    if (product.tags().contains("官方")
                            || product.tags().contains("旗舰店")
                            || product.tags().contains("自营")) {
                        base += 1.5;
                        reasons.add("官方/自营渠道");
                        matched.add("official_store");
                    }
                }
                case "fast_delivery" -> {
                    if (product.platform().contains("京东")) {
                        base += 1.0;
                        reasons.add("物流较快");
                        matched.add("fast_delivery");
                    }
                }
            }
        }

        if (product.rating() >= 4.8) {
            base += 0.5;
            reasons.add("高评分");
            matched.add("high_rating");
        }
        if (product.sales() >= 10000) {
            base += 0.5;
            reasons.add("高销量");
            matched.add("high_sales");
        }
        if (maxPrice != null && product.price() <= maxPrice) {
            matched.add("budget_match");
        }
        if (maxPrice != null && product.price() > maxPrice) {
            base -= 3.0;
        }
        if (fullPref != null) {
            if (fullPref.brand() != null && product.brand() != null
                    && product.brand().equals(fullPref.brand())) {
                base += 1.0;
                matched.add("brand_match");
            }
            if (fullPref.minRating() != null && product.rating() >= fullPref.minRating()) {
                matched.add("min_rating_met");
            }
        }

        return product.withScoringResult(base, reasons, matched);
    }
}
