package com.ec26b.shoppingagent.api;

import com.ec26b.shoppingagent.api.ApiModels.*;
import com.ec26b.shoppingagent.service.ShoppingService;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/recognitions")
public class RecognitionController {
    private final ShoppingService shoppingService;

    public RecognitionController(ShoppingService shoppingService) {
        this.shoppingService = shoppingService;
    }

    @PostMapping
    public ApiResponse<RecognitionDto> create(Authentication authentication, @RequestBody CreateRecognitionRequest request) {
        return ApiResponse.success(shoppingService.createRecognition(userId(authentication), request));
    }

    @GetMapping("/{recognitionId}")
    public ApiResponse<RecognitionDto> get(Authentication authentication, @PathVariable long recognitionId) {
        return ApiResponse.success(shoppingService.recognition(userId(authentication), recognitionId));
    }

    @PatchMapping("/{recognitionId}/attributes")
    public ApiResponse<RecognitionDto> update(Authentication authentication, @PathVariable long recognitionId, @RequestBody UpdateRecognitionAttributesRequest request) {
        return ApiResponse.success(shoppingService.updateRecognition(userId(authentication), recognitionId, request));
    }

    private long userId(Authentication authentication) {
        return (Long) authentication.getPrincipal();
    }
}
