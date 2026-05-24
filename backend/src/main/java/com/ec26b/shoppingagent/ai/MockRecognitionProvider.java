package com.ec26b.shoppingagent.ai;

import com.ec26b.shoppingagent.service.MockCatalog;

public class MockRecognitionProvider implements AiRecognitionProvider {
    private final MockCatalog mockCatalog;

    public MockRecognitionProvider(MockCatalog mockCatalog) {
        this.mockCatalog = mockCatalog;
    }

    @Override
    public RecognitionResult recognize(ImagePayload image) {
        MockCatalog.RecognitionSample sample = mockCatalog.recognitionSampleFor(image.imageUrl(), image.imageId());
        return new RecognitionResult(
                sample.category(),
                sample.brand(),
                sample.model(),
                sample.keywords(),
                sample.attributes(),
                sample.confidence(),
                providerName(),
                false,
                "使用 mock/sample_dataset 识别样例生成结构化识物结果。",
                java.util.List.of()
        );
    }

    @Override
    public String providerName() {
        return "mock";
    }
}
