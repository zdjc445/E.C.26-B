package com.ec26b.shoppingagent.ai;

public interface AiRecognitionProvider {
    RecognitionResult recognize(ImagePayload image);

    String providerName();
}
