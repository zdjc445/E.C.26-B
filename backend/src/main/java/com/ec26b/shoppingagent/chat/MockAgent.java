package com.ec26b.shoppingagent.chat;

import com.ec26b.shoppingagent.ai.RecognitionResult;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@Component
public class MockAgent {

    /**
     * Decides the reply type:
     * - If selectedOptionIds present → recommendation
     * - If imageIds present (and no options) → recognition + clarification
     * - Otherwise → clarification
     */
    public AgentReply process(ChatStore.ChatSession session, String text,
                              List<String> imageIds, List<String> selectedOptionIds) {

        boolean hasOptions = selectedOptionIds != null && !selectedOptionIds.isEmpty();
        boolean hasImages = imageIds != null && !imageIds.isEmpty();

        if (hasOptions) {
            return buildRecommendation(selectedOptionIds);
        }
        if (hasImages) {
            return buildRecognitionReply(imageIds);
        }
        return buildClarification();
    }

    /**
     * Process recognition with a pre-existing result.
     */
    public AgentReply processWithRecognition(ChatStore.ChatSession session, String text,
                                             List<String> imageIds, List<String> selectedOptionIds,
                                             RecognitionResult recResult) {
        boolean hasOptions = selectedOptionIds != null && !selectedOptionIds.isEmpty();

        if (hasOptions) {
            return buildRecommendation(selectedOptionIds);
        }
        return buildRecognitionReplyWithResult(recResult);
    }

    private AgentReply buildRecognitionReply(List<String> imageIds) {
        // Return a mock recognition card + clarification
        List<Card> cards = new ArrayList<>();
        cards.add(new Card(
                "recognition",
                "识别结果",
                null, null, null, null, null,
                imageIds.get(0),
                "运动鞋", "Mock 品牌", "Mock 型号",
                List.of("运动鞋", "白色", "跑步鞋"),
                Map.of("color", "白色", "style", "通勤运动鞋"),
                0.82, "mock", false,
                "当前为演示识别结果。",
                null
        ));
        cards.add(new Card(
                "clarification",
                "你更看重哪一点？",
                null, null, null, null,
                List.of(
                        new Option("lowest_price", "价格最低"),
                        new Option("official_store", "官方店铺"),
                        new Option("fast_delivery", "配送更快")
                ),
                null, null, null, null, null, null, 0, null, false, null, null
        ));

        return new AgentReply(
                UUID.randomUUID().toString(),
                "recognition",
                "我已经识别了你的商品图片。你更看重哪一点？",
                cards
        );
    }

    private AgentReply buildRecognitionReplyWithResult(RecognitionResult rec) {
        List<Card> cards = new ArrayList<>();
        cards.add(new Card(
                "recognition",
                "识别结果",
                null, null, null, null, null,
                rec.getImageId(),
                rec.getCategory(), rec.getBrand(), rec.getModel(),
                rec.getKeywords(), rec.getAttributes(),
                rec.getConfidence(), rec.getAiProvider(), rec.isFallbackUsed(),
                rec.getExplanation(),
                rec.getRecognitionId()
        ));
        cards.add(new Card(
                "clarification",
                "你更看重哪一点？",
                null, null, null, null,
                List.of(
                        new Option("lowest_price", "价格最低"),
                        new Option("official_store", "官方店铺"),
                        new Option("fast_delivery", "配送更快")
                ),
                null, null, null, null, null, null, 0, null, false, null, null
        ));

        return new AgentReply(
                UUID.randomUUID().toString(),
                "recognition",
                "我已经识别了你的商品图片。你更看重哪一点？",
                cards
        );
    }

    private AgentReply buildClarification() {
        return new AgentReply(
                UUID.randomUUID().toString(),
                "clarification",
                "我已经收到你的需求。你更看重哪一点？",
                List.of(new Card(
                        "clarification",
                        "你更看重哪一点？",
                        null, null, null, null,
                        List.of(
                                new Option("lowest_price", "价格最低"),
                                new Option("official_store", "官方店铺"),
                                new Option("fast_delivery", "配送更快")
                        ),
                        null, null, null, null, null, null, 0, null, false, null, null
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
                        rec.productName(), rec.platform(), rec.price(), rec.reason(),
                        null,
                        null, null, null, null, null, null, 0, null, false, null, null
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
            List<Option> options,
            // recognition fields
            String imageId,
            String category,
            String brand,
            String model,
            List<String> keywords,
            Map<String, Object> attributes,
            double confidence,
            String aiProvider,
            boolean fallbackUsed,
            String explanation,
            String recognitionId
    ) {}

    public record Option(String optionId, String label) {}

    private record Recommendation(String productName, String platform, Double price, String reason) {}
}
