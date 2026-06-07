package com.ec26b.shoppingagent.config;

import com.ec26b.shoppingagent.voice.ArkVoiceTranscriber;
import com.ec26b.shoppingagent.voice.FallbackVoiceTranscriber;
import com.ec26b.shoppingagent.voice.MockVoiceTranscriber;
import com.ec26b.shoppingagent.voice.VoiceTranscriber;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

@Configuration
public class VoiceConfig {

    @Bean
    @Primary
    public VoiceTranscriber voiceTranscriber(
            @Value("${app.voice.provider:mock}") String provider,
            MockVoiceTranscriber mockTranscriber,
            ArkVoiceTranscriber arkTranscriber) {
        if ("ark".equalsIgnoreCase(provider)) {
            return new FallbackVoiceTranscriber(arkTranscriber, mockTranscriber);
        }
        return mockTranscriber;
    }
}
