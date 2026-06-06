package com.ec26b.shoppingagent.ai;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class FallbackRecognitionProvider implements AiRecognitionProvider {
    private static final Logger log = LoggerFactory.getLogger(FallbackRecognitionProvider.class);

    private final AiRecognitionProvider primary;
    private final AiRecognitionProvider fallback;

    public FallbackRecognitionProvider(AiRecognitionProvider primary, AiRecognitionProvider fallback) {
        this.primary = primary;
        this.fallback = fallback;
    }

    @Override
    public RecognitionResult recognize(ImagePayload image) {
        try {
            return primary.recognize(image);
        } catch (RuntimeException ex) {
            log.warn("AI recognition provider {} failed, falling back to {}: {}: {}",
                    primary.providerName(), fallback.providerName(),
                    ex.getClass().getSimpleName(), ex.getMessage());
            RecognitionResult result = fallback.recognize(image);
            result.setFallbackUsed(true);
            result.setAiProvider(fallback.providerName());
            result.addNotice("Ark 识别不可用，已回退 mock/sample_dataset。");
            return result;
        }
    }

    @Override
    public String providerName() {
        return primary.providerName() + "+fallback";
    }
}
