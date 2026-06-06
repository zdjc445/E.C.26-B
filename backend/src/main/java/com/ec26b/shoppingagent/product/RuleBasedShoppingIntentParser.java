package com.ec26b.shoppingagent.product;

import org.springframework.stereotype.Component;

import java.util.List;

/**
 * Rule-based intent parser — wraps keyword extraction + preference parsing.
 * No AI, pure regex and keyword matching.
 */
@Component
public class RuleBasedShoppingIntentParser implements ShoppingIntentParser {

    private static final List<String> SUPPORTED_CATEGORIES =
            List.of("运动鞋", "耳机", "吹风机");

    private final UserPreferenceParser preferenceParser;

    public RuleBasedShoppingIntentParser(UserPreferenceParser preferenceParser) {
        this.preferenceParser = preferenceParser;
    }

    @Override
    public ShoppingIntent parse(String text) {
        if (text == null || text.isBlank()) {
            return ShoppingIntent.needsClarification(providerName());
        }
        String keyword = extractKeyword(text);
        UserPreference pref = preferenceParser.parse(text);
        return ShoppingIntent.fromRule(keyword, pref);
    }

    @Override
    public String providerName() {
        return "rule";
    }

    public static boolean isSupportedCategory(String category) {
        return category != null && SUPPORTED_CATEGORIES.contains(category);
    }

    public static String resolveKeyword(String recognitionCategory, String parsedKeyword) {
        if (isSupportedCategory(recognitionCategory)) return recognitionCategory;
        if (isSupportedCategory(parsedKeyword)) return parsedKeyword;
        return "运动鞋";
    }

    /**
     * Returns a supported category if the text explicitly mentions one,
     * or null if no supported category is found. Never returns a default.
     */
    public static String parseExplicitKeyword(String text) {
        if (text == null) return null;
        if (text.contains("运动鞋")) return "运动鞋";
        if (text.contains("耳机")) return "耳机";
        if (text.contains("吹风机")) return "吹风机";
        return null;
    }

    static String extractKeyword(String text) {
        if (text == null) return "运动鞋";
        if (text.contains("运动鞋")) return "运动鞋";
        if (text.contains("耳机")) return "耳机";
        if (text.contains("吹风机")) return "吹风机";
        return "运动鞋";
    }
}
