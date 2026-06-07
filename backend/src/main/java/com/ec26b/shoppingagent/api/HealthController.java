package com.ec26b.shoppingagent.api;

import com.ec26b.shoppingagent.auth.CurrentUser;
import com.ec26b.shoppingagent.product.RealEcommerceProvider;
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
    private final CurrentUser currentUser;
    private final RealEcommerceProvider realProvider;
    private final String voiceProvider;
    private final String stage;

    public HealthController(
            @Value("${app.ai.provider:mock}") String aiProvider,
            @Value("${chat.history-store:memory}") String chatHistoryStore,
            @Value("${app.voice.provider:mock}") String voiceProvider,
            CurrentUser currentUser,
            RealEcommerceProvider realProvider) {
        this.aiProvider = aiProvider;
        this.chatHistoryStore = chatHistoryStore;
        this.voiceProvider = voiceProvider;
        this.currentUser = currentUser;
        this.realProvider = realProvider;
        this.stage = "聊天式 AI 识别 + 多平台 Mock 推荐 + 7 维度自然语言筛选 + 动态建议卡"
                + " + 持久化 + 认证 + 收藏 + 价格提醒 + 语音转写阶段";
    }

    @GetMapping("/api/health")
    public Map<String, Object> health() {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("status", "ok");
        result.put("app", "shopping-agent");
        result.put("stage", stage);
        result.put("aiProvider", aiProvider);
        result.put("chatHistoryStore", chatHistoryStore);
        result.put("authEnabled", currentUser.authEnabled());
        result.put("ecommerceProvider", realProvider.enabled() ? "real" : "mock");
        result.put("voiceProvider", voiceProvider);
        result.put("timestamp", OffsetDateTime.now().toString());
        return result;
    }
}
