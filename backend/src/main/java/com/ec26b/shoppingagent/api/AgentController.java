package com.ec26b.shoppingagent.api;

import com.ec26b.shoppingagent.api.ApiModels.*;
import com.ec26b.shoppingagent.service.ShoppingService;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/agent/recommendations")
public class AgentController {
    private final ShoppingService shoppingService;

    public AgentController(ShoppingService shoppingService) {
        this.shoppingService = shoppingService;
    }

    @PostMapping
    public ApiResponse<RecommendationDto> create(Authentication authentication, @RequestBody CreateRecommendationRequest request) {
        return ApiResponse.success(shoppingService.createRecommendation(userId(authentication), request));
    }

    @GetMapping("/{recommendationId}")
    public ApiResponse<RecommendationDto> get(Authentication authentication, @PathVariable long recommendationId) {
        return ApiResponse.success(shoppingService.recommendation(userId(authentication), recommendationId));
    }

    @GetMapping("/{recommendationId}/report")
    public ApiResponse<RecommendationReportDto> report(Authentication authentication, @PathVariable long recommendationId) {
        return ApiResponse.success(shoppingService.recommendationReport(userId(authentication), recommendationId));
    }

    private long userId(Authentication authentication) {
        return (Long) authentication.getPrincipal();
    }
}
