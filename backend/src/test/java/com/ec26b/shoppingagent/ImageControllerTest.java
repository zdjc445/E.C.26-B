package com.ec26b.shoppingagent;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.hamcrest.Matchers.nullValue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ImageControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void shouldUploadImageAndReturnImageId() throws Exception {
        var file = new MockMultipartFile(
                "file", "test.jpg", "image/jpeg", "fake-image-content".getBytes());

        mockMvc.perform(multipart("/api/images/upload").file(file))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0))
                .andExpect(jsonPath("$.data.imageId").isNotEmpty())
                .andExpect(jsonPath("$.data.fileName").isNotEmpty())
                .andExpect(jsonPath("$.data.contentType").value("image/jpeg"))
                .andExpect(jsonPath("$.data.size").value(18));
    }

    @Test
    void shouldReturnErrorForEmptyFile() throws Exception {
        var file = new MockMultipartFile(
                "file", "empty.jpg", "image/jpeg", new byte[0]);

        mockMvc.perform(multipart("/api/images/upload").file(file))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(40001))
                .andExpect(jsonPath("$.data").value(nullValue()));
    }

    @Test
    void shouldSanitizeUnsafeOriginalFileNameExtension() throws Exception {
        var file = new MockMultipartFile(
                "file", "photo.jpg/evil", "image/jpeg", "fake-image-content".getBytes());

        mockMvc.perform(multipart("/api/images/upload").file(file))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0))
                .andExpect(jsonPath("$.data.fileName").value(not(containsString("/"))))
                .andExpect(jsonPath("$.data.fileName").value(not(containsString("\\"))));
    }
}
