package com.ec26b.shoppingagent.product;

import java.util.List;

public record UserPreference(
        Double maxPrice,
        String color,
        boolean officialStore,
        boolean fastDelivery,
        boolean lowestPrice,
        boolean highRating,
        boolean highSales
) {
    public List<String> toPreferenceIds() {
        List<String> ids = new java.util.ArrayList<>();
        if (lowestPrice) ids.add("lowest_price");
        if (officialStore) ids.add("official_store");
        if (fastDelivery) ids.add("fast_delivery");
        return ids;
    }

    public static UserPreference empty() {
        return new UserPreference(null, null, false, false, false, false, false);
    }
}
