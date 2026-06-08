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

import static org.hamcrest.Matchers.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RecognitionControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

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
    void shouldRecognizeUploadedImage() throws Exception {
        String imageId = uploadTestImage();

        var body = Map.of("imageId", imageId);
        mockMvc.perform(post("/api/recognition")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0))
                .andExpect(jsonPath("$.data.recognitionId").isNotEmpty())
                .andExpect(jsonPath("$.data.imageId").value(imageId))
                .andExpect(jsonPath("$.data.category").isNotEmpty())
                .andExpect(jsonPath("$.data.aiProvider").value("mock"))
                .andExpect(jsonPath("$.data.fallbackUsed").value(false));
    }

    @Test
    void shouldReturnErrorForMissingImageId() throws Exception {
        var body = Map.of("imageId", "");
        mockMvc.perform(post("/api/recognition")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(40001))
                .andExpect(jsonPath("$.data").value(nullValue()));
    }

    @Test
    void shouldReturnErrorForNonexistentImageId() throws Exception {
        var body = Map.of("imageId", "nonexistent-id");
        mockMvc.perform(post("/api/recognition")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().is(404))
                .andExpect(jsonPath("$.code").value(40004))
                .andExpect(jsonPath("$.data").value(nullValue()));
    }

    @Test
    void shouldUpdateRecognitionAttributes() throws Exception {
        String imageId = uploadTestImage();
        var body = Map.of("imageId", imageId);
        var result = mockMvc.perform(post("/api/recognition")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andReturn();
        String recId = objectMapper.readTree(result.getResponse().getContentAsString())
                .get("data").get("recognitionId").asText();

        var patchBody = Map.of(
                "category", "耳机",
                "brand", "用户修正品牌",
                "model", "用户修正型号",
                "attributes", Map.of("color", "深蓝色", "type", "入耳式")
        );
        mockMvc.perform(patch("/api/recognition/{recognitionId}/attributes", recId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(patchBody)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.category").value("耳机"))
                .andExpect(jsonPath("$.data.brand").value("用户修正品牌"))
                .andExpect(jsonPath("$.data.model").value("用户修正型号"))
                .andExpect(jsonPath("$.data.attributes.color").value("深蓝色"))
                .andExpect(jsonPath("$.data.attributes.type").value("入耳式"))
                .andExpect(jsonPath("$.data.notices[0]").value("用户已修正识别属性"));
    }

    @Test
    void shouldReturnErrorForNonexistentRecognitionIdOnPatch() throws Exception {
        var body = Map.of("category", "test");
        mockMvc.perform(patch("/api/recognition/nonexistent/attributes")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().is(404))
                .andExpect(jsonPath("$.code").value(40004))
                .andExpect(jsonPath("$.data").value(nullValue()));
    }

    @Test
    void shouldReturnRecognitionCardInChatWithImageIds() throws Exception {
        // Create session
        var sessionResult = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk())
                .andReturn();
        String sessionId = objectMapper.readTree(sessionResult.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();

        // Upload image first
        String imageId = uploadTestImage();

        // Send message with imageIds
        var msgBody = Map.of("imageIds", List.of(imageId));
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sessionId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(msgBody)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0))
                .andExpect(jsonPath("$.data.replyType").value("product_recommendation"))
                .andExpect(jsonPath("$.data.cards.length()").value(2))
                .andExpect(jsonPath("$.data.cards[0].cardType").value("product_group_list"))
                .andExpect(jsonPath("$.data.cards[0].category").isNotEmpty())
                .andExpect(jsonPath("$.data.cards[0].recognitionId").isNotEmpty())
                .andExpect(jsonPath("$.data.cards[0].groups.length()").value(greaterThanOrEqualTo(1)))
                .andExpect(jsonPath("$.data.cards[1].cardType").value("clarification"));
    }

    @Test
    void shouldReturnErrorForInvalidImageIdInChatMessage() throws Exception {
        var sessionResult = mockMvc.perform(post("/api/chat/sessions"))
                .andExpect(status().isOk())
                .andReturn();
        String sessionId = objectMapper.readTree(sessionResult.getResponse().getContentAsString())
                .get("data").get("sessionId").asText();

        var msgBody = Map.of("imageIds", List.of("nonexistent-image-id"));
        mockMvc.perform(post("/api/chat/sessions/{sessionId}/messages", sessionId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(msgBody)))
                .andExpect(status().is(404))
                .andExpect(jsonPath("$.code").value(40004))
                .andExpect(jsonPath("$.message").value("图片不存在"))
                .andExpect(jsonPath("$.data").value(nullValue()));
    }
}
