package com.ec26b.shoppingagent.voice;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class MockVoiceTranscriber implements VoiceTranscriber {

    private final String fallbackText;

    public MockVoiceTranscriber(@Value("${app.voice.transcript-fallback:推荐运动鞋}") String fallbackText) {
        this.fallbackText = fallbackText == null || fallbackText.isBlank()
                ? "推荐运动鞋" : fallbackText;
    }

    @Override
    public TranscriptionResult transcribe(byte[] audio, String contentType) {
        // Mock: deterministic demo transcript. Real STT can replace this provider.
        return new TranscriptionResult(fallbackText, "mock", false,
                "当前为 Mock 语音转写，结果固定，可用于演示。");
    }
}
