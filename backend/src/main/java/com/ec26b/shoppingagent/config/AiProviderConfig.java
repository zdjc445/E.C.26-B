package com.ec26b.shoppingagent.config;

import com.ec26b.shoppingagent.ai.AiRecognitionProvider;
import com.ec26b.shoppingagent.ai.AiRefineProvider;
import com.ec26b.shoppingagent.ai.ArkClient;
import com.ec26b.shoppingagent.ai.ArkRecognitionProvider;
import com.ec26b.shoppingagent.ai.ArkRefineProvider;
import com.ec26b.shoppingagent.ai.FallbackRecognitionProvider;
import com.ec26b.shoppingagent.ai.FallbackRefineProvider;
import com.ec26b.shoppingagent.ai.MockRecognitionProvider;
import com.ec26b.shoppingagent.ai.RuleBasedRefineProvider;
import com.ec26b.shoppingagent.service.MockCatalog;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class AiProviderConfig {
    @Bean
    public AiRecognitionProvider aiRecognitionProvider(
            MockCatalog mockCatalog,
            ObjectMapper objectMapper,
            @Value("${app.ai.provider:mock}") String provider,
            @Value("${app.ai.ark.api-key:}") String apiKey,
            @Value("${app.ai.ark.endpoint-id:}") String endpointId,
            @Value("${app.ai.ark.base-url:}") String baseUrl
    ) {
        MockRecognitionProvider mock = new MockRecognitionProvider(mockCatalog);
        if ("ark".equalsIgnoreCase(provider)) {
            ArkClient arkClient = new ArkClient(objectMapper, apiKey, endpointId, baseUrl);
            return new FallbackRecognitionProvider(new ArkRecognitionProvider(arkClient, objectMapper), mock);
        }
        return mock;
    }

    @Bean
    public AiRefineProvider aiRefineProvider(
            ObjectMapper objectMapper,
            @Value("${app.ai.provider:mock}") String provider,
            @Value("${app.ai.ark.api-key:}") String apiKey,
            @Value("${app.ai.ark.endpoint-id:}") String endpointId,
            @Value("${app.ai.ark.base-url:}") String baseUrl
    ) {
        RuleBasedRefineProvider rule = new RuleBasedRefineProvider();
        if ("ark".equalsIgnoreCase(provider)) {
            ArkClient arkClient = new ArkClient(objectMapper, apiKey, endpointId, baseUrl);
            return new FallbackRefineProvider(new ArkRefineProvider(arkClient, objectMapper), rule);
        }
        return rule;
    }
}
