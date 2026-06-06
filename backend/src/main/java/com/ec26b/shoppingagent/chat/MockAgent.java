package com.ec26b.shoppingagent.chat;

import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;
import java.util.UUID;

@Component
public class MockAgent {

    /**
     * Decides the reply type:
     * - If selectedOptionIds is present and non-empty → recommendation
     * - Otherwise → clarification (need more info)
     */
    public AgentReply process(ChatStore.ChatSession session, String text,
                              List<String> imageIds, List<String> selectedOptionIds) {

        boolean hasOptions = selectedOptionIds != null && !selectedOptionIds.isEmpty();

        if (hasOptions) {
            return buildRecommendation(selectedOptionIds);
        }
        return buildClarification();
    }

    private AgentReply buildClarification() {
        return new AgentReply(
                UUID.randomUUID().toString(),
                "clarification",
                "我已经收到你的需求。你更看重哪一点？",
                List.of(new Card(
                        "clarification",
                        "你更看重哪一点？",
                        null,
                        null,
                        null,
                        null,
                        List.of(
                                new Option("lowest_price", "价格最低"),
                                new Option("official_store", "官方店铺"),
                                new Option("fast_delivery", "配送更快")
                        )
                ))
        );
    }

    private AgentReply buildRecommendation(List<String> selectedOptionIds) {
        String optionId = selectedOptionIds.get(0);
        Recommendation rec = switch (optionId) {
            case "lowest_price" -> new Recommendation(
                    "Mock 商品", "Mock 平台-mock", 199.00,
                    "符合你选择的偏好，适合作为当前演示推荐。"
            );
            case "official_store" -> new Recommendation(
                    "Mock 官方店铺商品", "Mock 官方店铺-mock", 239.00,
                    "适合更看重店铺可靠性的演示场景。"
            );
            case "fast_delivery" -> new Recommendation(
                    "Mock 快速配送商品", "Mock 快送平台-mock", 229.00,
                    "适合更看重配送速度的演示场景。"
            );
            default -> new Recommendation(
                    "Mock 商品", "Mock 平台-mock", 199.00,
                    "根据你的偏好给出的推荐。"
            );
        };

        return new AgentReply(
                UUID.randomUUID().toString(),
                "recommendation",
                "根据你的偏好，我给出以下推荐。",
                List.of(new Card(
                        "recommendation",
                        "推荐购买",
                        rec.productName(),
                        rec.platform(),
                        rec.price(),
                        rec.reason(),
                        null
                ))
        );
    }

    // ── response DTOs ──

    public record AgentReply(
            String replyId,
            String replyType,
            String text,
            List<Card> cards
    ) {}

    public record Card(
            String cardType,
            String title,
            String productName,
            String platform,
            Double price,
            String reason,
            List<Option> options
    ) {}

    public record Option(String optionId, String label) {}

    private record Recommendation(String productName, String platform, Double price, String reason) {}
}
