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
    private final boolean needsClarification;
    private final String clarificationQuestion;
    private final String intentProvider;
    private final boolean intentFallbackUsed;
    private final List<String> notices;

    public ShoppingIntent(String keyword, Double maxPrice, String color,
                          boolean officialStore, boolean fastDelivery, boolean lowestPrice,
                          boolean highRating, boolean highSales,
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
        this.needsClarification = needsClarification;
        this.clarificationQuestion = clarificationQuestion;
        this.intentProvider = intentProvider;
        this.intentFallbackUsed = intentFallbackUsed;
        this.notices = notices != null ? List.copyOf(notices) : List.of();
    }

    public String keyword() { return keyword; }
    public Double maxPrice() { return maxPrice; }
    public String color() { return color; }
    public boolean officialStore() { return officialStore; }
    public boolean fastDelivery() { return fastDelivery; }
    public boolean lowestPrice() { return lowestPrice; }
    public boolean highRating() { return highRating; }
    public boolean highSales() { return highSales; }
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
        return ids;
    }

    public UserPreference toUserPreference() {
        return new UserPreference(maxPrice, color, officialStore, fastDelivery,
                lowestPrice, highRating, highSales);
    }

    public static ShoppingIntent fromRule(String keyword, UserPreference pref) {
        return new ShoppingIntent(keyword, pref.maxPrice(), pref.color(),
                pref.officialStore(), pref.fastDelivery(), pref.lowestPrice(),
                pref.highRating(), pref.highSales(),
                false, null, "rule", false, List.of());
    }

    public static ShoppingIntent needsClarification(String provider) {
        return new ShoppingIntent("运动鞋", null, null,
                false, false, false, false, false,
                true, "你能告诉我更多需求吗？例如预算、品牌或偏好？",
                provider, false, List.of());
    }
}
