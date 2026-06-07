package com.ec26b.shoppingagent.chat;

import com.ec26b.shoppingagent.ai.ArkClient;
import com.ec26b.shoppingagent.product.ArkRecommendationExplainer;
import com.ec26b.shoppingagent.product.MockProductSourceProvider;
import com.ec26b.shoppingagent.product.RecommendationExplainer;
import com.ec26b.shoppingagent.product.RecommendationScorer;
import com.ec26b.shoppingagent.product.ShoppingIntent;
import com.ec26b.shoppingagent.product.ShoppingIntentParser;
import com.ec26b.shoppingagent.product.UserPreferenceParser;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MockAgentFilterSummaryTest {

    @Test
    void shouldHideDefaultFilterSummaryValues() {
        MockAgent agent = newAgent(new ShoppingIntent("耳机", 300.0, null,
                false, false, false, false, false,
                null, List.of("京东-mock", "拼多多-mock", "淘宝-mock"),
                "recommended", 0.0,
                false, null, "ark", false, List.of()));

        var reply = agent.process(emptySession(), "推荐耳机", List.of(), List.of());

        assertEquals(List.of("品类：耳机", "预算≤300元"),
                reply.cards().get(0).filterSummary());
    }

    @Test
    void shouldKeepExplicitFilterSummaryValues() {
        MockAgent agent = newAgent(new ShoppingIntent("耳机", 9999.0, null,
                false, false, false, true, false,
                "索尼", List.of("京东-mock"), "price_asc", 4.8,
                false, null, "ark", false, List.of()));

        var reply = agent.process(emptySession(), "只看京东索尼评分4.8以上的耳机按价格从低到高",
                List.of(), List.of());

        assertEquals(List.of("品类：耳机", "品牌：索尼", "平台：京东", "评分≥4.8", "排序：价格从低到高"),
                reply.cards().get(0).filterSummary());
    }

    private MockAgent newAgent(ShoppingIntent intent) {
        ObjectMapper objectMapper = new ObjectMapper();
        return new MockAgent(
                new MockProductSourceProvider(new RecommendationScorer()),
                new FixedShoppingIntentParser(intent),
                new RecommendationExplainer(),
                new ArkRecommendationExplainer(new ArkClient(objectMapper, "", "", null), objectMapper),
                new UserPreferenceParser(),
                "mock");
    }

    private ChatStore.ChatSession emptySession() {
        OffsetDateTime now = OffsetDateTime.now();
        return new ChatStore.ChatSession("test-session", "新对话", now, now, new ArrayList<>());
    }

    private record FixedShoppingIntentParser(ShoppingIntent intent) implements ShoppingIntentParser {
        @Override
        public ShoppingIntent parse(String text) {
            return intent;
        }

        @Override
        public String providerName() {
            return intent.intentProvider();
        }
    }
}
