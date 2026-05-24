package com.ec26b.shoppingagent.api;

import com.ec26b.shoppingagent.api.ApiModels.*;
import com.ec26b.shoppingagent.service.ShoppingService;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/comparisons")
public class ComparisonController {
    private final ShoppingService shoppingService;

    public ComparisonController(ShoppingService shoppingService) {
        this.shoppingService = shoppingService;
    }

    @PostMapping
    public ApiResponse<ComparisonDto> create(Authentication authentication, @RequestBody CreateComparisonRequest request) {
        return ApiResponse.success(shoppingService.createComparison(userId(authentication), request));
    }

    private long userId(Authentication authentication) {
        return (Long) authentication.getPrincipal();
    }
}
