package com.ec26b.shoppingagent.ai;

import java.util.List;
import java.util.Map;

public record RecognitionResult(
        String category,
        String brand,
        String model,
        List<String> keywords,
        Map<String, Object> attributes,
        double confidence,
        String provider,
        boolean fallbackUsed,
        String explanation,
        List<String> notices
) {
    public static RecognitionResult of(
            String category,
            String brand,
            String model,
            List<String> keywords,
            Map<String, Object> attributes,
            double confidence,
            String provider,
            boolean fallbackUsed,
            String explanation
    ) {
        return new RecognitionResult(category, brand, model, keywords, attributes, confidence, provider, fallbackUsed, explanation, List.of());
    }

    public RecognitionResult withRuntime(String provider, boolean fallbackUsed, String notice) {
        List<String> mergedNotices = notice == null || notice.isBlank()
                ? notices == null ? List.of() : notices
                : java.util.stream.Stream.concat(
                        notices == null ? java.util.stream.Stream.empty() : notices.stream(),
                        java.util.stream.Stream.of(notice)
                ).toList();
        return new RecognitionResult(category, brand, model, keywords, attributes, confidence, provider, fallbackUsed, explanation, mergedNotices);
    }
}
