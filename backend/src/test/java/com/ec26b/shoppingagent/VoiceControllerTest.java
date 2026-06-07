package com.ec26b.shoppingagent;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class VoiceControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void shouldTranscribeWithMockProvider() throws Exception {
        var file = new MockMultipartFile("file", "demo.m4a", "audio/m4a",
                new byte[]{0, 1, 2, 3});
        mockMvc.perform(multipart("/api/voice/transcribe").file(file))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0))
                .andExpect(jsonPath("$.data.text").value("推荐运动鞋"))
                .andExpect(jsonPath("$.data.provider").value("mock"))
                .andExpect(jsonPath("$.data.fallbackUsed").value(false));
    }

    @Test
    void shouldRejectEmptyAudio() throws Exception {
        var file = new MockMultipartFile("file", "empty.m4a", "audio/m4a", new byte[0]);
        mockMvc.perform(multipart("/api/voice/transcribe").file(file))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(40001));
    }
}
