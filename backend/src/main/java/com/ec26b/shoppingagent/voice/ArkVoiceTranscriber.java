package com.ec26b.shoppingagent.voice;

import com.ec26b.shoppingagent.ai.ArkClient;
import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.stereotype.Component;

import java.util.Base64;
import java.util.List;
import java.util.Map;

/**
 * Best-effort transcription via the Ark multimodal endpoint.
 *
 * <p>Sends the audio as a base64-encoded data URL and asks the model to return
 * a short Chinese transcript. If the model is not configured or refuses, the
 * caller (see {@link FallbackVoiceTranscriber}) will fall back to the mock
 * transcriber. Real STT-specific endpoints can replace this implementation.
 */
@Component
public class ArkVoiceTranscriber implements VoiceTranscriber {

    private final ArkClient arkClient;

    public ArkVoiceTranscriber(ArkClient arkClient) {
        this.arkClient = arkClient;
    }

    @Override
    public TranscriptionResult transcribe(byte[] audio, String contentType) {
        if (!arkClient.isEnabled()) {
            throw new IllegalStateException("Ark voice provider is not configured");
        }
        String mime = (contentType == null || contentType.isBlank())
                ? "audio/m4a" : contentType;
        String base64 = Base64.getEncoder().encodeToString(audio);
        List<Map<String, Object>> messages = List.of(
                Map.of("role", "system", "content",
                        "你是中文语音转写助手。请把用户语音转成简洁的购物自然语言。只输出 JSON：{\"text\":\"...\"}。"),
                Map.of("role", "user", "content", List.of(
                        Map.of("type", "text", "text", "请把这段语音转成购物文字。"),
                        Map.of("type", "input_audio", "input_audio",
                                Map.of("data", "data:" + mime + ";base64," + base64,
                                        "format", mime.replace("audio/", "")))
                )));
        JsonNode json = arkClient.chatJson(messages);
        String text = json.path("text").asText("");
        if (text.isBlank()) {
            throw new IllegalStateException("Ark voice response missing text");
        }
        return new TranscriptionResult(text.trim(), "ark", false, null);
    }
}
