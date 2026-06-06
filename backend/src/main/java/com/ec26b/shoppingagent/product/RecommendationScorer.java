package com.ec26b.shoppingagent.product;

import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;

/**
 * Scores products based on user preferences and budget.
 * Pure rule-based, no AI.
 */
@Component
public class RecommendationScorer {

    public ProductOffer scoreProduct(ProductOffer product, List<String> preferences, Double maxPrice) {
        double base = 5.0;
        List<String> reasons = new ArrayList<>(product.reasons());

        for (String pref : preferences) {
            switch (pref) {
                case "lowest_price" -> {
                    if (product.price() < 250) {
                        base += 1.0;
                        reasons.add("价格优惠");
                    }
                }
                case "official_store" -> {
                    if (product.tags().contains("官方")
                            || product.tags().contains("旗舰店")
                            || product.tags().contains("自营")) {
                        base += 1.5;
                        reasons.add("官方/自营渠道");
                    }
                }
                case "fast_delivery" -> {
                    if (product.platform().contains("京东")) {
                        base += 1.0;
                        reasons.add("物流较快");
                    }
                }
            }
        }

        if (product.rating() >= 4.8) {
            base += 0.5;
            reasons.add("高评分");
        }
        if (product.sales() >= 10000) {
            base += 0.5;
            reasons.add("高销量");
        }
        if (maxPrice != null && product.price() > maxPrice) {
            base -= 3.0;
        }

        return new ProductOffer(
                product.productId(), product.title(), product.platform(),
                product.price(), product.originalPrice(), product.shopName(),
                product.imageUrl(), product.productUrl(),
                product.rating(), product.sales(), product.tags(),
                reasons, base
        );
    }
}
