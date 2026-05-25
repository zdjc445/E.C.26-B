package com.ec26b.shoppingagent.ecommerce;

final class OfficialCredentialValue {
    private OfficialCredentialValue() {
    }

    static boolean present(String value) {
        return !missing(value);
    }

    static boolean missing(String value) {
        if (value == null || value.isBlank()) {
            return true;
        }
        String normalized = value.trim().toLowerCase();
        if (normalized.startsWith("<") && normalized.endsWith(">")) {
            return true;
        }
        if (normalized.contains("your-") || normalized.contains("replace-")) {
            return true;
        }
        return switch (normalized) {
            case "...", "xxx", "todo", "tbd", "placeholder", "change-me", "changeme", "change_me" -> true;
            default -> false;
        };
    }
}
