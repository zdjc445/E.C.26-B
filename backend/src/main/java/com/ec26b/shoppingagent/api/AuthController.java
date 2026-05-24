package com.ec26b.shoppingagent.api;

import com.ec26b.shoppingagent.api.ApiModels.*;
import com.ec26b.shoppingagent.service.ShoppingService;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/auth")
public class AuthController {
    private final ShoppingService shoppingService;

    public AuthController(ShoppingService shoppingService) {
        this.shoppingService = shoppingService;
    }

    @PostMapping("/register")
    public ApiResponse<AuthPayload> register(@RequestBody RegisterRequest request) {
        return ApiResponse.success(shoppingService.register(request));
    }

    @PostMapping("/login")
    public ApiResponse<AuthPayload> login(@RequestBody LoginRequest request) {
        return ApiResponse.success(shoppingService.login(request));
    }

    @PostMapping("/refresh")
    public ApiResponse<RefreshTokenPayload> refresh(@RequestBody RefreshTokenRequest request) {
        return ApiResponse.success(shoppingService.refresh(request));
    }

    @PostMapping("/logout")
    public ApiResponse<Void> logout(@RequestBody RefreshTokenRequest request) {
        shoppingService.logout(request);
        return ApiResponse.empty();
    }

    @GetMapping("/me")
    public ApiResponse<UserDto> me(Authentication authentication) {
        return ApiResponse.success(shoppingService.currentUser(userId(authentication)));
    }

    private long userId(Authentication authentication) {
        return (Long) authentication.getPrincipal();
    }
}
