package com.ec26b.shoppingagent.ai;

public class FallbackRecognitionProvider implements AiRecognitionProvider {
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
            return fallback.recognize(image).withRuntime(fallback.providerName(), true, "Ark 识别不可用，已回退 mock/sample_dataset。");
        }
    }

    @Override
    public String providerName() {
        return primary.providerName() + "+fallback";
    }
}
