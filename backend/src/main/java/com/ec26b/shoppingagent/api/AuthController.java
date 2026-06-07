package com.ec26b.shoppingagent.api;

import com.ec26b.shoppingagent.auth.AuthService;
import com.ec26b.shoppingagent.auth.CurrentUser;
import com.ec26b.shoppingagent.auth.User;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.LinkedHashMap;
import java.util.Map;

@RestController
@RequestMapping("/api/auth")
public class AuthController {

    private final AuthService authService;
    private final CurrentUser currentUser;

    public AuthController(AuthService authService, CurrentUser currentUser) {
        this.authService = authService;
        this.currentUser = currentUser;
    }

    @PostMapping("/register")
    public ResponseEntity<ApiResponse<AuthService.AuthResult>> register(@RequestBody RegisterRequest request) {
        try {
            var result = authService.register(request.username(), request.password(), request.displayName());
            return ResponseEntity.ok(ApiResponse.success(result));
        } catch (AuthService.AuthException ex) {
            return ResponseEntity.status(ex.code() == 40101 ? 401 : 400)
                    .body(ApiResponse.error(ex.code(), ex.getMessage()));
        }
    }

    @PostMapping("/login")
    public ResponseEntity<ApiResponse<AuthService.AuthResult>> login(@RequestBody LoginRequest request) {
        try {
            var result = authService.login(request.username(), request.password());
            return ResponseEntity.ok(ApiResponse.success(result));
        } catch (AuthService.AuthException ex) {
            return ResponseEntity.status(ex.code() == 40101 ? 401 : 400)
                    .body(ApiResponse.error(ex.code(), ex.getMessage()));
        }
    }

    @GetMapping("/me")
    public ResponseEntity<ApiResponse<Map<String, Object>>> me(HttpServletRequest request) {
        var maybeAuth = currentUser.resolve(request);
        if (maybeAuth.isEmpty()) {
            return ResponseEntity.status(401)
                    .body(ApiResponse.error(40101, "未登录或登录已过期"));
        }
        var auth = maybeAuth.get();
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("userId", auth.userId());
        data.put("username", auth.username());
        data.put("role", auth.role());
        data.put("authEnabled", currentUser.authEnabled());
        if (auth.userId() > 0) {
            try {
                User user = authService.requireUserById(auth.userId());
                data.put("displayName", user.displayName());
                data.put("createdAt", user.createdAt().toString());
            } catch (AuthService.AuthException ignored) {
                // demo user without backing row — keep auth fields only
            }
        } else {
            data.put("displayName", "演示用户");
        }
        return ResponseEntity.ok(ApiResponse.success(data));
    }

    public record RegisterRequest(String username, String password, String displayName) {}

    public record LoginRequest(String username, String password) {}
}
