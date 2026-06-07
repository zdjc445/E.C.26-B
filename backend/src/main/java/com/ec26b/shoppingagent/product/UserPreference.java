package com.ec26b.shoppingagent.product;

import java.util.ArrayList;
import java.util.List;

public record UserPreference(
        Double maxPrice,
        String color,
        boolean officialStore,
        boolean fastDelivery,
        boolean lowestPrice,
        boolean highRating,
        boolean highSales,
        String brand,
        List<String> platforms,
        String sortBy,
        Double minRating
) {

    public UserPreference {
        platforms = platforms == null ? List.of() : List.copyOf(platforms);
    }

    public UserPreference(Double maxPrice, String color,
                          boolean officialStore, boolean fastDelivery,
                          boolean lowestPrice, boolean highRating, boolean highSales) {
        this(maxPrice, color, officialStore, fastDelivery, lowestPrice, highRating, highSales,
                null, List.of(), null, null);
    }

    public List<String> toPreferenceIds() {
        List<String> ids = new ArrayList<>();
        if (lowestPrice) ids.add("lowest_price");
        if (officialStore) ids.add("official_store");
        if (fastDelivery) ids.add("fast_delivery");
        if (highRating) ids.add("high_rating");
        if (highSales) ids.add("high_sales");
        return ids;
    }

    public static UserPreference empty() {
        return new UserPreference(null, null, false, false, false, false, false,
                null, List.of(), null, null);
    }
}
