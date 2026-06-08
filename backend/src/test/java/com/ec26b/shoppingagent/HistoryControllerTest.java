package com.ec26b.shoppingagent;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;
import java.util.Map;

import static org.hamcrest.Matchers.hasSize;
import static org.hamcrest.Matchers.nullValue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HistoryControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    private String createSession() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk())
                .andReturn();
        return objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();
    }

    private String uploadTestImage() throws Exception {
        var file = new MockMultipartFile(
                "file", "shoe.jpg", "image/jpeg", "test-image-bytes".getBytes());
        var result = mockMvc.perform(multipart("/api/images/upload").file(file))
                .andExpect(status().isOk())
                .andReturn();
        return objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("imageId").asText();
    }

    @Test
    void shouldCreateSessionWithDefaultTitle() throws Exception {
        var result = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk())
                .andReturn();
        String sessionId = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();
        mockMvc.perform(get("/api/chat/sessions/{sessionId}/messages", sessionId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.sessionId").value(sessionId));
    }

    @Test
    void shouldAutoTitleFromFirstText() throws Exception {
        String sessionId = createSession();
        var body = Map.of("text", "我想买一双白色运动鞋");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sessionId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk());
        mockMvc.perform(get("/api/chat/sessions"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.sessions[0].title").value("我想买一双白色运动鞋"));
    }

    @Test
    void shouldAutoTitleImageOnly() throws Exception {
        String sessionId = createSession();
        String imageId = uploadTestImage();
        var body = Map.of("imageIds", List.of(imageId));
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sessionId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk());
        mockMvc.perform(get("/api/chat/sessions"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.sessions[0].title").value("图片购物需求"));
    }

    @Test
    void shouldListSessionsOrderedByUpdatedAtDesc() throws Exception {
        String s1 = createSession();
        String s2 = createSession();
        var body = Map.of("text", "hello");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", s1)
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk());
        mockMvc.perform(get("/api/chat/sessions"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.sessions.length()").isNumber());
    }

    @Test
    void shouldGetMessagesAndRestoreClarificationReply() throws Exception {
        String sessionId = createSession();
        var body = Map.of("text", "你好");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sessionId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk());

        mockMvc.perform(get("/api/chat/sessions/{sessionId}/messages", sessionId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.messages", hasSize(2)))
                .andExpect(jsonPath("$.data.messages[0].role").value("user"))
                .andExpect(jsonPath("$.data.messages[1].role").value("assistant"))
                .andExpect(jsonPath("$.data.messages[1].agentReply.replyType").value("clarification"))
                .andExpect(jsonPath("$.data.messages[1].agentReply.cards[0].cardType").value("product_group_list"))
                .andExpect(jsonPath("$.data.messages[1].agentReply.cards[1].cardType").value("clarification"));
    }

    @Test
    void shouldGetMessagesAndRestoreRecommendationReply() throws Exception {
        String sessionId = createSession();
        // First message
        var body1 = Map.of("text", "hello");
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sessionId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body1)))
                .andExpect(status().isOk());
        // Select option
        var body2 = Map.of("selectedOptionIds", List.of("lowest_price"));
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sessionId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body2)))
                .andExpect(status().isOk());

        mockMvc.perform(get("/api/chat/sessions/{sessionId}/messages", sessionId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.messages", hasSize(4)))
                .andExpect(jsonPath("$.data.messages[3].agentReply.replyType").value("product_recommendation"))
                .andExpect(jsonPath("$.data.messages[3].agentReply.cards[0].cardType").value("product_group_list"))
                .andExpect(jsonPath("$.data.messages[3].agentReply.cards[1].cardType").value("clarification"));
    }

    @Test
    void shouldGetMessagesAndRestoreRecognitionReply() throws Exception {
        String sessionId = createSession();
        String imageId = uploadTestImage();
        var body = Map.of("imageIds", List.of(imageId));
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sessionId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk());

        mockMvc.perform(get("/api/chat/sessions/{sessionId}/messages", sessionId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.messages[1].agentReply.replyType").value("product_recommendation"))
                .andExpect(jsonPath("$.data.messages[1].agentReply.cards.length()").value(2))
                .andExpect(jsonPath("$.data.messages[1].agentReply.cards[0].cardType").value("product_group_list"))
                .andExpect(jsonPath("$.data.messages[1].agentReply.cards[1].cardType").value("clarification"));
    }

    @Test
    void shouldRenameSessionSuccessfully() throws Exception {
        String sessionId = createSession();
        var renameBody = Map.of("title", "白色运动鞋推荐");
        mockMvc.perform(patch("/api/chat/sessions/{sessionId}", sessionId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(renameBody)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.title").value("白色运动鞋推荐"));
    }

    @Test
    void shouldReturnErrorForEmptyRenameTitle() throws Exception {
        String sessionId = createSession();
        var renameBody = Map.of("title", "   ");
        mockMvc.perform(patch("/api/chat/sessions/{sessionId}", sessionId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(renameBody)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(40001))
                .andExpect(jsonPath("$.data").value(nullValue()));
    }

    @Test
    void shouldDeleteSessionSuccessfully() throws Exception {
        String sessionId = createSession();
        mockMvc.perform(delete("/api/chat/sessions/{sessionId}", sessionId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.deleted").value(true));
    }

    @Test
    void shouldReturn404ForDeletingNonexistentSession() throws Exception {
        mockMvc.perform(delete("/api/chat/sessions/nonexistent"))
                .andExpect(status().is(404))
                .andExpect(jsonPath("$.code").value(40004))
                .andExpect(jsonPath("$.data").value(nullValue()));
    }

    @Test
    void shouldReturn404ForMessagesOfDeletedSession() throws Exception {
        String sessionId = createSession();
        mockMvc.perform(delete("/api/chat/sessions/{sessionId}", sessionId))
                .andExpect(status().isOk());
        mockMvc.perform(get("/api/chat/sessions/{sessionId}/messages", sessionId))
                .andExpect(status().is(404))
                .andExpect(jsonPath("$.code").value(40004))
                .andExpect(jsonPath("$.data").value(nullValue()));
    }
}
