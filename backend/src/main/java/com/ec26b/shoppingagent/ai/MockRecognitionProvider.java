package com.ec26b.shoppingagent.ai;

import java.util.List;
import java.util.Map;

public class MockRecognitionProvider implements AiRecognitionProvider {

    @Override
    public RecognitionResult recognize(ImagePayload image) {
        return new RecognitionResult(
                image.imageId(),
                "运动鞋",
                "Mock 品牌",
                "Mock 型号",
                List.of("运动鞋", "白色", "跑步鞋"),
                Map.of("color", "白色", "style", "通勤运动鞋"),
                0.82,
                providerName(),
                false,
                "当前为演示识别结果。",
                List.of()
        );
    }

    @Override
    public String providerName() {
        return "mock";
    }
}
