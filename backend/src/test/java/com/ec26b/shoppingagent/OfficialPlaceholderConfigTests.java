package com.ec26b.shoppingagent;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import java.nio.charset.StandardCharsets;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "app.ecommerce.enabled=true",
        "app.ecommerce.pdd.enabled=true",
        "app.ecommerce.pdd.client-id=<pdd client id>",
        "app.ecommerce.pdd.client-secret=...",
        "app.ecommerce.jd.enabled=true",
        "app.ecommerce.jd.app-key=your-jd-key",
        "app.ecommerce.jd.app-secret=replace-me"
})
@AutoConfigureMockMvc
class OfficialPlaceholderConfigTests {
    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void statusTreatsPlaceholderCredentialsAsMissing() throws Exception {
        String content = mockMvc.perform(get("/api/ecommerce/status"))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString(StandardCharsets.UTF_8);
        JsonNode statusPayload = objectMapper.readTree(content).get("data");

        assertThat(statusPayload.get("enabled").asBoolean()).isTrue();
        assertThat(statusPayload.get("hasConfiguredClient").asBoolean()).isFalse();
        assertThat(provider(statusPayload, "拼多多").get("configured").asBoolean()).isFalse();
        assertThat(provider(statusPayload, "拼多多").get("missingConfig").toString()).contains("PDD_CLIENT_ID", "PDD_CLIENT_SECRET");
        assertThat(provider(statusPayload, "京东").get("configured").asBoolean()).isFalse();
        assertThat(provider(statusPayload, "京东").get("missingConfig").toString()).contains("JD_APP_KEY", "JD_APP_SECRET");
    }

    private JsonNode provider(JsonNode status, String platform) {
        for (JsonNode provider : status.get("providers")) {
            if (platform.equals(provider.get("platform").asText())) {
                return provider;
            }
        }
        throw new AssertionError("Provider not found: " + platform);
    }
}
