package com.ec26b.shoppingagent.voice;

public interface VoiceTranscriber {
    TranscriptionResult transcribe(byte[] audio, String contentType);

    record TranscriptionResult(String text, String provider, boolean fallbackUsed, String notice) {}
}
