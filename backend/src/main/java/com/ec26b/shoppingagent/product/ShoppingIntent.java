package com.ec26b.shoppingagent.product;

import java.util.ArrayList;
import java.util.List;

public class ShoppingIntent {
    private final String keyword;
    private final Double maxPrice;
    private final String color;
    private final boolean officialStore;
    private final boolean fastDelivery;
    private final boolean lowestPrice;
    private final boolean highRating;
    private final boolean highSales;
    private final String brand;
    private final List<String> platforms;
    private final String sortBy;
    private final Double minRating;
    private final boolean needsClarification;
    private final String clarificationQuestion;
    private final String intentProvider;
    private final boolean intentFallbackUsed;
    private final List<String> notices;

    public ShoppingIntent(String keyword, Double maxPrice, String color,
                          boolean officialStore, boolean fastDelivery, boolean lowestPrice,
                          boolean highRating, boolean highSales,
                          String brand, List<String> platforms, String sortBy, Double minRating,
                          boolean needsClarification, String clarificationQuestion,
                          String intentProvider, boolean intentFallbackUsed, List<String> notices) {
        this.keyword = keyword;
        this.maxPrice = maxPrice;
        this.color = color;
        this.officialStore = officialStore;
        this.fastDelivery = fastDelivery;
        this.lowestPrice = lowestPrice;
        this.highRating = highRating;
        this.highSales = highSales;
        this.brand = brand;
        this.platforms = platforms != null ? List.copyOf(platforms) : List.of();
        this.sortBy = sortBy;
        this.minRating = minRating;
        this.needsClarification = needsClarification;
        this.clarificationQuestion = clarificationQuestion;
        this.intentProvider = intentProvider;
        this.intentFallbackUsed = intentFallbackUsed;
        this.notices = notices != null ? List.copyOf(notices) : List.of();
    }

    public ShoppingIntent(String keyword, Double maxPrice, String color,
                          boolean officialStore, boolean fastDelivery, boolean lowestPrice,
                          boolean highRating, boolean highSales,
                          boolean needsClarification, String clarificationQuestion,
                          String intentProvider, boolean intentFallbackUsed, List<String> notices) {
        this(keyword, maxPrice, color, officialStore, fastDelivery, lowestPrice, highRating, highSales,
                null, List.of(), null, null,
                needsClarification, clarificationQuestion, intentProvider, intentFallbackUsed, notices);
    }

    public String keyword() { return keyword; }
    public Double maxPrice() { return maxPrice; }
    public String color() { return color; }
    public boolean officialStore() { return officialStore; }
    public boolean fastDelivery() { return fastDelivery; }
    public boolean lowestPrice() { return lowestPrice; }
    public boolean highRating() { return highRating; }
    public boolean highSales() { return highSales; }
    public String brand() { return brand; }
    public List<String> platforms() { return platforms; }
    public String sortBy() { return sortBy; }
    public Double minRating() { return minRating; }
    public boolean needsClarification() { return needsClarification; }
    public String clarificationQuestion() { return clarificationQuestion; }
    public String intentProvider() { return intentProvider; }
    public boolean intentFallbackUsed() { return intentFallbackUsed; }
    public List<String> notices() { return notices; }

    public List<String> toPreferenceIds() {
        List<String> ids = new ArrayList<>();
        if (lowestPrice) ids.add("lowest_price");
        if (officialStore) ids.add("official_store");
        if (fastDelivery) ids.add("fast_delivery");
        if (highRating) ids.add("high_rating");
        if (highSales) ids.add("high_sales");
        return ids;
    }

    public UserPreference toUserPreference() {
        return new UserPreference(maxPrice, color, officialStore, fastDelivery,
                lowestPrice, highRating, highSales,
                brand, platforms, sortBy, minRating);
    }

    public static ShoppingIntent fromRule(String keyword, UserPreference pref) {
        return new ShoppingIntent(keyword, pref.maxPrice(), pref.color(),
                pref.officialStore(), pref.fastDelivery(), pref.lowestPrice(),
                pref.highRating(), pref.highSales(),
                pref.brand(), pref.platforms(), pref.sortBy(), pref.minRating(),
                false, null, "rule", false, List.of());
    }

    public static ShoppingIntent needsClarification(String provider) {
        return new ShoppingIntent("运动鞋", null, null,
                false, false, false, false, false,
                null, List.of(), null, null,
                true, "你能告诉我更多需求吗？例如预算、品牌或偏好？",
                provider, false, List.of());
    }
}
