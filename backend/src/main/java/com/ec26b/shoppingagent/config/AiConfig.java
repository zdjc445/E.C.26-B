package com.ec26b.shoppingagent.config;

import com.ec26b.shoppingagent.ai.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

@Configuration
public class AiConfig {

    @Bean
    public MockRecognitionProvider mockRecognitionProvider() {
        return new MockRecognitionProvider();
    }

    @Bean
    public ArkClient arkClient(ObjectMapper objectMapper,
                               @Value("${app.ai.ark.api-key:}") String apiKey,
                               @Value("${app.ai.ark.endpoint-id:}") String endpointId,
                               @Value("${app.ai.ark.base-url:https://ark.cn-beijing.volces.com/api/v3}") String baseUrl) {
        return new ArkClient(objectMapper, apiKey, endpointId, baseUrl);
    }

    @Bean
    public ArkRecognitionProvider arkRecognitionProvider(ArkClient arkClient, ObjectMapper objectMapper) {
        return new ArkRecognitionProvider(arkClient, objectMapper);
    }

    @Bean
    @Primary
    public AiRecognitionProvider aiRecognitionProvider(
            @Value("${app.ai.provider:mock}") String provider,
            MockRecognitionProvider mockProvider,
            ArkRecognitionProvider arkProvider) {
        if ("ark".equalsIgnoreCase(provider)) {
            return new FallbackRecognitionProvider(arkProvider, mockProvider);
        }
        return mockProvider;
    }
}
