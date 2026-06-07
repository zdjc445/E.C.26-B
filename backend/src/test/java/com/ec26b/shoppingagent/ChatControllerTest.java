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
    void shouldExposeCategoryInFilterSummary() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sessionId = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();

        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sessionId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of("text", "推荐耳机"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.cards[0].cardType").value("product_list"))
                .andExpect(jsonPath("$.data.cards[0].filterSummary", hasItem("品类：耳机")));
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

    @Test
    void shouldRefineRecognitionCategoryWithBudgetAndColor() {
        // Build a session with a recognition card whose category="耳机"
        var session = chatStore.createSession();
        var recCard = MockAgent.Card.recognition(
                "img-001", "耳机", "Mock 品牌", "Mock 型号",
                List.of("耳机", "蓝牙"), Map.of("color", "黑色"),
                0.85, "mock", false, "演示识别结果。", "rec-test-003");
        var agentReply = new MockAgent.AgentReply(
                "reply-rec", "recognition", "识别结果", List.of(recCard));
        chatStore.addMessage(session.sessionId(),
                new ChatStore.MessageRecord("msg-1", "user", "帮我看看",
                        List.of("img-001"), List.of(), OffsetDateTime.now(), null));
        chatStore.addMessage(session.sessionId(),
                new ChatStore.MessageRecord("msg-2", "assistant", "识别结果",
                        List.of(), List.of(), OffsetDateTime.now(), agentReply));

        // Refine with budget and color — must use 耳机 from recognition
        var reply = mockAgent.process(session, "只看300以内的黑色款",
                List.of(), List.of());

        assertEquals("product_recommendation", reply.replyType());
        var filterSummary = reply.cards().get(0).filterSummary();
        assertTrue(filterSummary.contains("品类：耳机"));
        assertTrue(filterSummary.contains("预算≤300元"));
        assertTrue(filterSummary.contains("颜色：黑色"));
        var products = reply.cards().get(0).products();
        assertTrue(products.size() > 0, "should have matching products");
        for (var p : products) {
            assertTrue(p.title().contains("耳机"),
                    "product should be 耳机 but got: " + p.title());
            assertTrue(p.price() <= 300.0,
                    "price should be <= 300 but was " + p.price());
            boolean hasColor = p.title().contains("黑色")
                    || p.tags().stream().anyMatch(t -> t.contains("黑色"));
            assertTrue(hasColor,
                    "product " + p.productId() + " should match color 黑色");
        }
    }

    // ── Explanation fields ───────────────────────────────────

    @Test
    void shouldIncludeExplanationInRecommendationCard() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();
        var body = Map.of("text", "我想买300以内的耳机，价格低一点");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.replyType").value("product_recommendation"))
                .andExpect(jsonPath("$.data.cards[0].cardType").value("product_list"))
                .andExpect(jsonPath("$.data.cards[1].cardType").value("comparison"))
                .andExpect(jsonPath("$.data.cards[2].cardType").value("recommendation"))
                .andExpect(jsonPath("$.data.cards[2].decisionScore").isNumber())
                .andExpect(jsonPath("$.data.cards[2].decisionSignals.length()").value(5))
                .andExpect(jsonPath("$.data.cards[2].evidence").isArray())
                .andExpect(jsonPath("$.data.cards[2].risks").isArray())
                .andExpect(jsonPath("$.data.cards[2].productAnalyses").isArray());
    }

    @Test
    void shouldApplyPreferenceParsingToInfluenceSignals() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();
        // Text with low-price preference
        var body = Map.of("text", "便宜一点的吹风机");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.cards[2].decisionSignals.length()").value(5))
                .andExpect(jsonPath("$.data.cards[2].decisionSignals[0].key").isString());
    }

    @Test
    void shouldNotIncludeRecommendationCardWhenOverBudget() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();
        var body = Map.of("text", "50以内的耳机");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.cards[0].cardType").value("product_list"))
                .andExpect(jsonPath("$.data.cards[1].cardType").value("comparison"))
                // No recommendation card when empty
                .andExpect(jsonPath("$.data.cards.length()").value(2));
    }

    @Test
    void shouldRestoreExplanationInHistory() throws Exception {
        var sessionResult = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(sessionResult.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();
        var body = Map.of("text", "推荐耳机");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk());
        // GET history — third card is recommendation with explanation
        mockMvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                        .get("/api/chat/sessions/{sessionId}/messages", sid))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.messages[1].agentReply.cards[2].decisionScore").isNumber())
                .andExpect(jsonPath("$.data.messages[1].agentReply.cards[2].decisionSignals").isArray());
    }

    // ── Expanded Mock data tests ─────────────────────────────

    @Test
    void shouldReturnAtLeast12ProductsForShoes() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();
        var body = Map.of("text", "推荐运动鞋");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.cards[0].products.length()").value(12))
                .andExpect(jsonPath("$.data.cards[0].products[*].title",
                        everyItem(containsString("运动鞋"))));
    }

    @Test
    void shouldReturnAtLeast12ProductsForHeadphones() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();
        var body = Map.of("text", "买耳机");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.cards[0].products.length()").value(12));
    }

    @Test
    void shouldReturnAtLeast12ProductsForHairdryer() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();
        var body = Map.of("text", "推荐吹风机");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.cards[0].products.length()").value(12));
    }

    @Test
    void shouldFilterShoesByBudget200() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();
        var body = Map.of("text", "200以内的运动鞋");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.cards[0].products[*].price",
                        everyItem(lessThanOrEqualTo(200.0))));
    }

    @Test
    void shouldFilterHeadphonesByBudget150() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();
        var body = Map.of("text", "150以内的耳机");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.cards[0].products[*].price",
                        everyItem(lessThanOrEqualTo(150.0))));
    }

    @Test
    void shouldFilterHairdryerByBudget120() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();
        var body = Map.of("text", "120以内的吹风机");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.cards[0].products[*].price",
                        everyItem(lessThanOrEqualTo(120.0))));
    }

    @Test
    void shouldReturnStableCardsForUltraLowBudgetHeadphones() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();
        var body = Map.of("text", "30以内的耳机");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.cards[0].cardType").value("product_list"))
                .andExpect(jsonPath("$.data.cards[1].cardType").value("comparison"))
                .andExpect(jsonPath("$.data.cards.length()").value(2));
    }

    // ── Multi-turn refinement tests ─────────────────────────

    @Test
    void shouldRefineWithBudgetAndColorInSameSession() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();

        // Turn 1: "推荐耳机"
        var body1 = Map.of("text", "推荐耳机");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body1)))
                .andExpect(status().isOk());

        // Turn 2: "只看300以内的黑色款"
        var body2 = Map.of("text", "只看300以内的黑色款");
        var mvcResult = mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body2)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.replyType").value("product_recommendation"))
                .andExpect(jsonPath("$.data.cards[0].filterSummary",
                        hasItems("品类：耳机", "预算≤300元", "颜色：黑色")))
                .andExpect(jsonPath("$.data.cards[0].products[*].title",
                        everyItem(containsString("耳机"))))
                .andExpect(jsonPath("$.data.cards[0].products[*].price",
                        everyItem(lessThanOrEqualTo(300.0))))
                .andReturn();

        // Verify color filtering: every product title or tags contains "黑色"
        var json = objectMapper.readTree(mvcResult.getResponse().getContentAsString());
        for (var p : json.at("/data/cards/0/products")) {
            String title = p.path("title").asText();
            boolean hasColor = title.contains("黑色");
            for (var t : p.path("tags")) {
                if (t.asText().contains("黑色")) { hasColor = true; break; }
            }
            assertTrue(hasColor,
                    "product " + p.path("productId").asText() + " should match color 黑色");
        }
    }

    @Test
    void shouldRefineWithNestedBudgetThenColor() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();

        // Turn 1: "500以内的耳机"
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of("text", "500以内的耳机"))))
                .andExpect(status().isOk());

        // Turn 2: "300以内"
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of("text", "300以内"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.cards[0].products[*].price",
                        everyItem(lessThanOrEqualTo(300.0))));

        // Turn 3: "黑色款" — must inherit maxPrice=300, not 500
        var mvcResult = mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of("text", "黑色款"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.cards[0].products[*].price",
                        everyItem(lessThanOrEqualTo(300.0))))
                .andReturn();

        var json = objectMapper.readTree(mvcResult.getResponse().getContentAsString());
        for (var p : json.at("/data/cards/0/products")) {
            String title = p.path("title").asText();
            boolean hasColor = title.contains("黑色");
            for (var t : p.path("tags")) {
                if (t.asText().contains("黑色")) { hasColor = true; break; }
            }
            assertTrue(hasColor,
                    "product " + p.path("productId").asText() + " should match color 黑色");
        }
    }

    @Test
    void shouldFilterColorOnNoContext() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();

        var mvcResult = mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of("text", "300以内黑色款"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.cards[0].products[*].title",
                        everyItem(containsString("运动鞋"))))
                .andExpect(jsonPath("$.data.cards[0].products[*].price",
                        everyItem(lessThanOrEqualTo(300.0))))
                .andReturn();

        var json = objectMapper.readTree(mvcResult.getResponse().getContentAsString());
        for (var p : json.at("/data/cards/0/products")) {
            String title = p.path("title").asText();
            boolean hasColor = title.contains("黑色");
            for (var t : p.path("tags")) {
                if (t.asText().contains("黑色")) { hasColor = true; break; }
            }
            assertTrue(hasColor,
                    "product " + p.path("productId").asText() + " should match color 黑色");
        }
    }

    @Test
    void shouldRefineHairdryerWithBudgetInSameSession() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();

        var body1 = Map.of("text", "推荐吹风机");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body1)))
                .andExpect(status().isOk());

        var body2 = Map.of("text", "120以内");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body2)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.cards[0].products[*].title",
                        everyItem(containsString("吹风机"))))
                .andExpect(jsonPath("$.data.cards[0].products[*].price",
                        everyItem(lessThanOrEqualTo(120.0))));
    }

    @Test
    void shouldUseRecognitionCategoryForRefinement() throws Exception {
        var sessionResult = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(sessionResult.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();

        // Upload image + recognition → card with category="运动鞋" (MockRecognitionProvider default)
        var file = new org.springframework.mock.web.MockMultipartFile(
                "file", "shoe.jpg", "image/jpeg", "test-image-bytes".getBytes());
        var upResult = mockMvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                        .multipart("/api/images/upload").file(file))
                .andExpect(status().isOk()).andReturn();
        String imageId = objectMapper.readTree(upResult.getResponse().getContentAsString())
                .get("data").get("imageId").asText();
        var imgBody = Map.of("imageIds", List.of(imageId));
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(imgBody)))
                .andExpect(status().isOk());

        // Refine: "只看300以内的黑色款" → should use 运动鞋 from recognition
        var body2 = Map.of("text", "只看300以内的黑色款");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body2)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.cards[0].products[*].title",
                        everyItem(containsString("运动鞋"))))
                .andExpect(jsonPath("$.data.cards[0].products[*].price",
                        everyItem(lessThanOrEqualTo(300.0))));
    }

    @Test
    void shouldDefaultToShoesWhenNoContext() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();

        var body = Map.of("text", "300以内黑色款");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.replyType").value("product_recommendation"))
                .andExpect(jsonPath("$.data.cards[0].products[*].title",
                        everyItem(containsString("运动鞋"))));
    }

    @Test
    void shouldReturnStableCardsForOverlyStrictRefinement() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();

        var body1 = Map.of("text", "推荐耳机");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body1)))
                .andExpect(status().isOk());

        var body2 = Map.of("text", "30以内的黑色耳机");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body2)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.cards[0].cardType").value("product_list"))
                .andExpect(jsonPath("$.data.cards[0].filterSummary",
                        hasItems("品类：耳机", "预算≤30元", "颜色：黑色")))
                .andExpect(jsonPath("$.data.cards[1].cardType").value("comparison"))
                .andExpect(jsonPath("$.data.cards.length()").value(2));
    }

    // ── Brand, platform, sort, minRating natural-language filtering ──

    @Test
    void shouldFilterByBrandInNaturalLanguage() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();
        var body = Map.of("text", "我想买耐克的运动鞋");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.replyType").value("product_recommendation"))
                .andExpect(jsonPath("$.data.cards[0].products[*].title",
                        everyItem(containsString("耐克"))));
    }

    @Test
    void shouldFilterByPlatformInNaturalLanguage() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();
        var body = Map.of("text", "只看京东的耳机");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.cards[0].products[*].platform",
                        everyItem(is("京东-mock"))));
    }

    @Test
    void shouldSortByPriceAscInNaturalLanguage() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();
        var body = Map.of("text", "耳机按价格从低到高");
        var resp = mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk()).andReturn();
        var json = objectMapper.readTree(resp.getResponse().getContentAsString());
        var products = json.at("/data/cards/0/products");
        double prev = -1;
        for (var p : products) {
            double price = p.path("price").asDouble();
            assertTrue(price >= prev, "products should be sorted ascending by price");
            prev = price;
        }
    }

    @Test
    void shouldFilterByMinRatingInNaturalLanguage() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();
        var body = Map.of("text", "评分4.8以上的耳机");
        var resp = mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk()).andReturn();
        var json = objectMapper.readTree(resp.getResponse().getContentAsString());
        for (var p : json.at("/data/cards/0/products")) {
            assertTrue(p.path("rating").asDouble() >= 4.8);
        }
    }

    @Test
    void shouldExposeBrandPlatformAndRatingInFilterSummary() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();
        var body = Map.of("text", "只看京东索尼评分4.8以上的耳机");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.cards[0].filterSummary",
                        hasItems("品类：耳机", "品牌：索尼", "平台：京东", "评分≥4.8")));
    }

    @Test
    void shouldExposePriceHistoryAndMatchedPreferences() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();
        var body = Map.of("text", "300以内的耳机，便宜一点");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.cards[0].products[0].priceHistory").isArray())
                .andExpect(jsonPath("$.data.cards[0].products[0].matchedPreferences").isArray());
    }

    @Test
    void shouldExposePlatformAveragePrice() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of("text", "推荐运动鞋"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.cards[1].platformStats.京东-mock.averagePrice").isNumber())
                .andExpect(jsonPath("$.data.cards[1].platformStats.京东-mock.lowestPrice").isNumber());
    }

    @Test
    void shouldDynamicallySuggestForRecognitionCategory() throws Exception {
        var sessionResult = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(sessionResult.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();

        var file = new org.springframework.mock.web.MockMultipartFile(
                "file", "shoe.jpg", "image/jpeg", "test-image-bytes".getBytes());
        var upResult = mockMvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                        .multipart("/api/images/upload").file(file))
                .andExpect(status().isOk()).andReturn();
        String imageId = objectMapper.readTree(upResult.getResponse().getContentAsString())
                .get("data").get("imageId").asText();

        // Image with category=运动鞋 (mock provider default)
        var imgBody = Map.of("imageIds", List.of(imageId));
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(imgBody)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.cards[1].cardType").value("clarification"))
                .andExpect(jsonPath("$.data.cards[1].options[*].optionId",
                        hasItem("lowest_price")))
                .andExpect(jsonPath("$.data.cards[1].options[*].optionId",
                        hasItem("style_similar")))
                .andExpect(jsonPath("$.data.cards[1].options[*].optionId",
                        hasItem("price_history")));
    }

    @Test
    void shouldRecommendBackpackCategoryViaText() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of("text", "推荐背包"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.cards[0].products.length()").value(12));
    }

    @Test
    void shouldRecommendSmartwatchCategoryViaText() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of("text", "推荐智能手表"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.cards[0].products.length()").value(12))
                .andExpect(jsonPath("$.data.cards[0].products[*].title",
                        everyItem(containsString("手表"))));
    }

    @Test
    void shouldInheritPlatformFilterAcrossTurns() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk()).andReturn();
        String sid = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();

        // Turn 1: 只看京东的耳机
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of("text", "只看京东的耳机"))))
                .andExpect(status().isOk());

        // Turn 2: 300以内 — should still only show JD
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sid)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of("text", "300以内"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.cards[0].products[*].platform",
                        everyItem(is("京东-mock"))))
                .andExpect(jsonPath("$.data.cards[0].products[*].price",
                        everyItem(lessThanOrEqualTo(300.0))));
    }
}
