package com.ec26b.shoppingagent;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Map;
import java.util.UUID;

import static org.hamcrest.Matchers.notNullValue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    private String uniqueUsername() {
        return "user_" + UUID.randomUUID().toString().substring(0, 8);
    }

    @Test
    void shouldRegisterAndIssueJwt() throws Exception {
        String username = uniqueUsername();
        var body = Map.of("username", username, "password", "secret123", "displayName", "演示用户");
        mockMvc.perform(post("/api/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0))
                .andExpect(jsonPath("$.data.token").value(notNullValue()))
                .andExpect(jsonPath("$.data.username").value(username))
                .andExpect(jsonPath("$.data.expiresInSeconds").isNumber());
    }

    @Test
    void shouldFailDuplicateRegistration() throws Exception {
        String username = uniqueUsername();
        var body = Map.of("username", username, "password", "secret123");
        mockMvc.perform(post("/api/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk());

        mockMvc.perform(post("/api/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value(40901));
    }

    @Test
    void shouldLoginWithCorrectPassword() throws Exception {
        String username = uniqueUsername();
        var register = Map.of("username", username, "password", "secret123");
        mockMvc.perform(post("/api/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(register)))
                .andExpect(status().isOk());
        mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(register)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.token").value(notNullValue()));
    }

    @Test
    void shouldRejectLoginWithBadPassword() throws Exception {
        String username = uniqueUsername();
        var register = Map.of("username", username, "password", "secret123");
        mockMvc.perform(post("/api/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(register)))
                .andExpect(status().isOk());
        var wrong = Map.of("username", username, "password", "wrong-password");
        mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(wrong)))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value(40101));
    }

    @Test
    void meShouldReturnDemoUserWhenAuthDisabledAndNoToken() throws Exception {
        // auth.enabled defaults to false in tests
        mockMvc.perform(get("/api/auth/me"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0))
                .andExpect(jsonPath("$.data.username").value("demo"))
                .andExpect(jsonPath("$.data.authEnabled").value(false));
    }

    @Test
    void meShouldReturnAuthenticatedUserWithToken() throws Exception {
        String username = uniqueUsername();
        var body = Map.of("username", username, "password", "secret123", "displayName", "Foo");
        String response = mockMvc.perform(post("/api/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(body)))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
        String token = objectMapper.readTree(response).at("/data/token").asText();
        mockMvc.perform(get("/api/auth/me").header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.username").value(username))
                .andExpect(jsonPath("$.data.displayName").value("Foo"));
    }
}
