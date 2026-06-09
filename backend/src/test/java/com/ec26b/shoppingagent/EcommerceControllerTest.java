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

@SpringBootTest(properties = {
        "app.ecommerce.real-provider-enabled=true",
        "app.ecommerce.real-provider-base-url=https://example.invalid",
        "app.ecommerce.real-provider-api-key=test-key"
})
@AutoConfigureMockMvc
class EcommerceControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void shouldReturnPublicDatasetStatus() throws Exception {
        mockMvc.perform(get("/api/ecommerce/status"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0))
                .andExpect(jsonPath("$.data.activeProvider").value("mock-data"))
                .andExpect(jsonPath("$.data.realProviderEnabled").value(false))
                .andExpect(jsonPath("$.data.realProviderActive").value(false))
                .andExpect(jsonPath("$.data.mockDataPlatforms", hasItem("京东")))
                .andExpect(jsonPath("$.data.mockDataCategories", hasItem("运动鞋")))
                .andExpect(jsonPath("$.data.mockDataCategories", hasItem("耳机")));
    }
}
