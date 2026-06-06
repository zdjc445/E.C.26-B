package com.ec26b.shoppingagent;

import com.ec26b.shoppingagent.chat.ChatStore;
import com.ec26b.shoppingagent.chat.MockAgent;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.hamcrest.Matchers.*;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ChatControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private MockAgent mockAgent;

    @Autowired
    private ChatStore chatStore;

    @Test
    void shouldCreateSessionAndReturnSessionId() throws Exception {
        mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0))
                .andExpect(jsonPath("$.data.sessionId").isNotEmpty())
                .andExpect(jsonPath("$.data.createdAt").isNotEmpty());
    }

    @Test
    void shouldReturnClarificationForFirstMessage() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk())
                .andReturn();
        String sessionId = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();

        var body = Map.of("text", "你好");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sessionId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.replyType").value("clarification"));
    }

    @Test
    void shouldReturnProductRecommendationForDirectShoppingText() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk())
                .andReturn();
        String sessionId = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();

        var body = Map.of("text", "我想买300以内的白色运动鞋，价格低一点");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sessionId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.replyType").value("product_recommendation"))
                .andExpect(jsonPath("$.data.cards[0].cardType").value("product_list"))
                .andExpect(jsonPath("$.data.cards[1].cardType").value("comparison"))
                .andExpect(jsonPath("$.data.cards[2].cardType").value("recommendation"));
    }

    @Test
    void shouldApplyBudgetFromDirectText() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk())
                .andReturn();
        String sessionId = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();

        var body = Map.of("text", "我想买200以内的运动鞋");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sessionId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.replyType").value("product_recommendation"))
                .andExpect(jsonPath("$.data.cards[0].products[*].price",
                        everyItem(lessThanOrEqualTo(200.0))));
    }

    @Test
    void shouldInheritBudgetFromHistoryOnOptionSelect() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk())
                .andReturn();
        String sessionId = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();

        // First: user sends text with budget
        var body1 = Map.of("text", "我想买200以内的运动鞋");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sessionId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body1)))
                .andExpect(status().isOk());

        // Second: click option (no text)
        var body2 = Map.of("selectedOptionIds", List.of("lowest_price"));
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sessionId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body2)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.replyType").value("product_recommendation"))
                .andExpect(jsonPath("$.data.cards[0].products[*].price",
                        everyItem(lessThanOrEqualTo(200.0))));
    }

    @Test
    void shouldReturnProductsFromThreeMockPlatforms() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk())
                .andReturn();
        String sessionId = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();

        var body = Map.of("text", "推荐运动鞋");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sessionId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.replyType").value("product_recommendation"))
                .andExpect(jsonPath("$.data.cards[1].platformStats",
                        hasKey("京东-mock")))
                .andExpect(jsonPath("$.data.cards[1].platformStats",
                        hasKey("拼多多-mock")))
                .andExpect(jsonPath("$.data.cards[1].platformStats",
                        hasKey("淘宝-mock")));
    }

    @Test
    void shouldAllPlatformNamesContainMock() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk())
                .andReturn();
        String sessionId = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();

        var body = Map.of("text", "推荐运动鞋");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sessionId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.cards[0].products[*].platform",
                        everyItem(containsString("-mock"))));
    }

    @Test
    void shouldReturnErrorForEmptyMessage() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk())
                .andReturn();
        String sessionId = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();

        var body = Map.of("text", "", "imageIds", List.of(), "selectedOptionIds", List.of());
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sessionId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(40001))
                .andExpect(jsonPath("$.data").value(nullValue()));
    }

    @Test
    void shouldReturnErrorForMissingSession() throws Exception {
        var body = Map.of("text", "hello");
        mockMvc.perform(post("/api/chat/sessions/nonexistent/messages")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().is(404))
                .andExpect(jsonPath("$.code").value(40004))
                .andExpect(jsonPath("$.data").value(nullValue()));
    }

    // ── Budget patterns ──────────────────────────────────────

    @Test
    void shouldParseBudgetNotExceed300() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();

        var body = Map.of("text", "不超过300的运动鞋");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.cards[0].products[*].price",
                        everyItem(lessThanOrEqualTo(300.0))));
    }

    @Test
    void shouldParseBudgetYusuan300() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();

        var body = Map.of("text", "预算300买运动鞋");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.cards[0].products[*].price",
                        everyItem(lessThanOrEqualTo(300.0))));
    }

    @Test
    void shouldParseBudget300YuanYiNei() throws Exception {
        String[] inputs = {"300以内", "300以下", "300元以内", "300块以内"};
        for (String input : inputs) {
            var result = mockMvc.perform(post("/api/chat/sessions"))
                    .andExpect(status().isOk()).andReturn();
            String sid = objectMapper.readTree(result.getResponse().getContentAsString())
                    .get("data").get("sessionId").asText();
            var body = Map.of("text", input + " 运动鞋");
            mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsString(body)))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.data.cards[0].products[*].price",
                            everyItem(lessThanOrEqualTo(300.0))));
        }
    }

    // ── Category inheritance from recognition ────────────────

    @Test
    void shouldInheritRecognitionCategoryOnOptionSelect() throws Exception {
        // Create session, upload image, send imageIds to get recognition
        var sessionResult = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(sessionResult.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();

        // Upload an image first (needed for the image validation in sendMessage)
        var file = new org.springframework.mock.web.MockMultipartFile(
                "file", "shoe.jpg", "image/jpeg", "test-image-bytes".getBytes());
        var upResult = mockMvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                        .multipart("/api/images/upload").file(file))
                .andExpect(status().isOk()).andReturn();
        String imageId = objectMapper.readTree(upResult.getResponse().getContentAsString())
                .get("data").get("imageId").asText();

        // Send imageIds — triggers recognition with category="运动鞋"
        var imgBody = Map.of("imageIds", List.of(imageId));
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(imgBody)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.replyType").value("recognition"));

        // Now click an option without text
        var optBody = Map.of("selectedOptionIds", List.of("lowest_price"));
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(optBody)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.replyType").value("product_recommendation"))
                .andExpect(jsonPath("$.data.cards[0].cardType").value("product_list"));
    }

    // ── Keyword → category consistency ──────────────────────

    @Test
    void shouldReturnHairdryerProductsForChuiFengJi() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();

        var body = Map.of("text", "推荐吹风机");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.cards[0].products[*].title",
                        everyItem(containsString("吹风机"))))
                .andExpect(jsonPath("$.data.cards[1].platformStats",
                        hasKey("京东-mock")))
                .andExpect(jsonPath("$.data.cards[1].platformStats",
                        hasKey("拼多多-mock")))
                .andExpect(jsonPath("$.data.cards[1].platformStats",
                        hasKey("淘宝-mock")));
    }

    @Test
    void shouldReturnHeadphoneProductsWhenKeywordIsEarphone() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();

        var body = Map.of("text", "买耳机");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.cards[0].products[*].title",
                        everyItem(containsString("耳机"))));
    }

    // ── Empty products with stable card structure ────────────

    @Test
    void shouldReturnStableCardsForOverBudget() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();

        var body = Map.of("text", "50以内的耳机");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.replyType").value("product_recommendation"))
                .andExpect(jsonPath("$.data.cards[0].cardType").value("product_list"))
                .andExpect(jsonPath("$.data.cards[1].cardType").value("comparison"))
                .andExpect(jsonPath("$.data.text").isNotEmpty());
    }

    // ── Recognition category inheritance with non-default category ─

    @Test
    void shouldUseRecognitionCategoryFromHistoryForProductSearch() {
        // Build a session with a recognition card whose category="耳机"
        var session = chatStore.createSession();
        var recCard = MockAgent.Card.recognition(
                "img-001", "耳机", "Mock 品牌", "Mock 型号",
                List.of("耳机", "蓝牙"), Map.of("color", "黑色"),
                0.85, "mock", false, "演示识别结果。", "rec-test-002");
        var agentReply = new MockAgent.AgentReply(
                "reply-rec", "recognition", "识别结果", List.of(recCard));
        var assistantMsg = new ChatStore.MessageRecord(
                "msg-2", "assistant", "识别结果",
                List.of(), List.of(), OffsetDateTime.now(), agentReply);
        chatStore.addMessage(session.sessionId(),
                new ChatStore.MessageRecord("msg-1", "user", "帮我看看",
                        List.of("img-001"), List.of(), OffsetDateTime.now(), null));
        chatStore.addMessage(session.sessionId(), assistantMsg);

        // Call process with only selectedOptionIds (no text, no images)
        var reply = mockAgent.process(session, "",
                List.of(), List.of("lowest_price"));

        assertEquals("product_recommendation", reply.replyType());
        // All products should be 耳机, not 运动鞋
        var products = reply.cards().get(0).products();
        assertTrue(products.size() > 0, "should have products from 耳机 category");
        for (var p : products) {
            assertTrue(p.title().contains("耳机"),
                    "product title should contain 耳机 but got: " + p.title());
        }
    }
}
