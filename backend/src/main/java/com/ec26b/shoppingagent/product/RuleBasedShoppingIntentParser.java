package com.ec26b.shoppingagent.product;

import org.springframework.stereotype.Component;

/**
 * Rule-based intent parser — wraps keyword extraction + preference parsing.
 * No AI, uses taxonomy retrieval + preference parsing.
 */
@Component
public class RuleBasedShoppingIntentParser implements ShoppingIntentParser {

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
        return CategoryResolver.defaultResolver().isSupportedCategory(category);
    }

    public static String resolveKeyword(String recognitionCategory, String parsedKeyword) {
        String normalizedRecognitionCategory = CategoryResolver.defaultResolver().resolveName(recognitionCategory);
        if (normalizedRecognitionCategory != null) return normalizedRecognitionCategory;
        String normalizedParsedKeyword = CategoryResolver.defaultResolver().resolveName(parsedKeyword);
        if (normalizedParsedKeyword != null) return normalizedParsedKeyword;
        return "运动鞋";
    }

    /**
     * Returns a supported category if the text explicitly mentions one,
     * or null if no supported category is found. Never returns a default.
     */
    public static String parseExplicitKeyword(String text) {
        return CategoryResolver.defaultResolver().resolveName(text);
    }

    static String extractKeyword(String text) {
        String explicit = parseExplicitKeyword(text);
        return explicit != null ? explicit : "运动鞋";
    }
}
