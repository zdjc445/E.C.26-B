package com.ec26b.shoppingagent.api;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.Map;

@RestController
public class HealthController {

    private final String aiProvider;
    private final String chatHistoryStore;

    public HealthController(
            @Value("${app.ai.provider:mock}") String aiProvider,
            @Value("${chat.history-store:memory}") String chatHistoryStore) {
        this.aiProvider = aiProvider;
        this.chatHistoryStore = chatHistoryStore;
    }

    @GetMapping("/api/health")
    public Map<String, Object> health() {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("status", "ok");
        result.put("app", "shopping-agent");
        result.put("stage", "聊天式 AI 识别与多平台 Mock 推荐阶段");
        result.put("aiProvider", aiProvider);
        result.put("chatHistoryStore", chatHistoryStore);
        result.put("timestamp", OffsetDateTime.now().toString());
        return result;
    }
}
