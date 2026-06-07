package com.ec26b.shoppingagent;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class EcommerceControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void shouldReturnMockStatusByDefault() throws Exception {
        mockMvc.perform(get("/api/ecommerce/status"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0))
                .andExpect(jsonPath("$.data.activeProvider").value("mock"))
                .andExpect(jsonPath("$.data.realProviderEnabled").value(false))
                .andExpect(jsonPath("$.data.realProviderActive").value(false))
                .andExpect(jsonPath("$.data.mockPlatforms", hasItem("京东-mock")))
                .andExpect(jsonPath("$.data.mockPlatforms", hasItem("拼多多-mock")))
                .andExpect(jsonPath("$.data.mockPlatforms", hasItem("淘宝-mock")))
                .andExpect(jsonPath("$.data.mockCategories", hasItem("背包")))
                .andExpect(jsonPath("$.data.mockCategories", hasItem("智能手表")));
    }
}
