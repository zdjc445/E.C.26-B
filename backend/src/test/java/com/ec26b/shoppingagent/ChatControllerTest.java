package com.ec26b.shoppingagent;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;
import java.util.Map;

import static org.hamcrest.Matchers.nullValue;
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

        var body = Map.of("text", "我想买一双白色运动鞋");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sessionId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0))
                .andExpect(jsonPath("$.data.replyType").value("clarification"))
                .andExpect(jsonPath("$.data.text").isNotEmpty())
                .andExpect(jsonPath("$.data.cards[0].cardType").value("clarification"))
                .andExpect(jsonPath("$.data.cards[0].options.length()").value(3))
                .andExpect(jsonPath("$.data.cards[0].productName").doesNotExist())
                .andExpect(jsonPath("$.data.cards[0].platform").doesNotExist())
                .andExpect(jsonPath("$.data.cards[0].price").doesNotExist())
                .andExpect(jsonPath("$.data.cards[0].reason").doesNotExist());
    }

    @Test
    void shouldReturnRecommendationAfterSelectingOption() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk())
                .andReturn();
        String sessionId = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();

        var body1 = Map.of("text", "我想买一双白色运动鞋");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sessionId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body1)))
                .andExpect(status().isOk());

        var body2 = Map.of("selectedOptionIds", List.of("lowest_price"));
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sessionId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body2)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0))
                .andExpect(jsonPath("$.data.replyType").value("recommendation"))
                .andExpect(jsonPath("$.data.cards[0].cardType").value("recommendation"))
                .andExpect(jsonPath("$.data.cards[0].productName").isNotEmpty())
                .andExpect(jsonPath("$.data.cards[0].platform").value("Mock 平台-mock"))
                .andExpect(jsonPath("$.data.cards[0].price").isNumber());
    }

    @Test
    void shouldReturnErrorForEmptyMessage() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk())
                .andReturn();
        String sessionId = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();

        var body = Map.of(
                "text", "",
                "imageIds", List.of(),
                "selectedOptionIds", List.of()
        );
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
}
