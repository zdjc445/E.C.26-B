package com.ec26b.shoppingagent.voice;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class FallbackVoiceTranscriber implements VoiceTranscriber {

    private static final Logger log = LoggerFactory.getLogger(FallbackVoiceTranscriber.class);

    private final VoiceTranscriber primary;
    private final VoiceTranscriber fallback;

    public FallbackVoiceTranscriber(VoiceTranscriber primary, VoiceTranscriber fallback) {
        this.primary = primary;
        this.fallback = fallback;
    }

    @Override
    public TranscriptionResult transcribe(byte[] audio, String contentType) {
        try {
            return primary.transcribe(audio, contentType);
        } catch (RuntimeException ex) {
            log.warn("Ark voice transcription failed, falling back to mock: {}: {}",
                    ex.getClass().getSimpleName(), ex.getMessage());
            TranscriptionResult m = fallback.transcribe(audio, contentType);
            return new TranscriptionResult(m.text(), "mock", true,
                    "Ark 语音转写不可用，已回退 Mock 转写。");
        }
    }
}
