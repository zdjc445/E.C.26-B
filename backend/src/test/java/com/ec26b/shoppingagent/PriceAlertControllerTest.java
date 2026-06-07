package com.ec26b.shoppingagent;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Map;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PriceAlertControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Test
    void shouldCreateListAndDeleteAlert() throws Exception {
        var create = Map.of(
                "productId", "jd-001",
                "title", "Mock 运动鞋",
                "platform", "京东-mock",
                "targetPrice", 250.0,
                "note", "降到 250 提醒我");
        String resp = mockMvc.perform(post("/api/price-alerts")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(create)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.productId").value("jd-001"))
                .andReturn().getResponse().getContentAsString();
        long alertId = objectMapper.readTree(resp).at("/data/id").asLong();

        mockMvc.perform(get("/api/price-alerts"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.total").isNumber())
                .andExpect(jsonPath("$.data.alerts[0].targetPrice").value(250.0));

        mockMvc.perform(delete("/api/price-alerts/" + alertId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.deleted").value(true));
    }

    @Test
    void shouldRejectInvalidTargetPrice() throws Exception {
        var bad = Map.of(
                "productId", "jd-001",
                "title", "Mock 运动鞋",
                "platform", "京东-mock",
                "targetPrice", -1.0);
        mockMvc.perform(post("/api/price-alerts")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(bad)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(40001));
    }

    @Test
    void shouldCheckAlertAndMarkTriggered() throws Exception {
        // Use jd-001 from MockProductSourceProvider whose price = 299.
        var create = Map.of(
                "productId", "jd-001",
                "title", "Mock 运动鞋",
                "platform", "京东-mock",
                "targetPrice", 300.0);
        mockMvc.perform(post("/api/price-alerts")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(create)))
                .andExpect(status().isOk());

        mockMvc.perform(post("/api/price-alerts/check"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.checked").isNumber())
                .andExpect(jsonPath("$.data.triggered").isNumber());
    }
}
