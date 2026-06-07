package com.ec26b.shoppingagent;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HealthControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void shouldReturnHealthWithRealConfigValues() throws Exception {
        mockMvc.perform(get("/api/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ok"))
                .andExpect(jsonPath("$.app").value("shopping-agent"))
                .andExpect(jsonPath("$.stage", containsString("聊天式 AI")))
                .andExpect(jsonPath("$.aiProvider").value("mock"))
                .andExpect(jsonPath("$.chatHistoryStore").value("memory"))
                .andExpect(jsonPath("$.authEnabled").value(false))
                .andExpect(jsonPath("$.ecommerceProvider").value("mock"))
                .andExpect(jsonPath("$.voiceProvider").value("mock"))
                .andExpect(jsonPath("$.timestamp").isNotEmpty());
    }
}
