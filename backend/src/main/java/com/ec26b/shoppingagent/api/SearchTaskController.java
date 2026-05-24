package com.ec26b.shoppingagent.api;

import com.ec26b.shoppingagent.api.ApiModels.*;
import com.ec26b.shoppingagent.service.ShoppingService;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/search-tasks")
public class SearchTaskController {
    private final ShoppingService shoppingService;

    public SearchTaskController(ShoppingService shoppingService) {
        this.shoppingService = shoppingService;
    }

    @PostMapping
    public ApiResponse<SearchTaskDto> create(Authentication authentication, @RequestBody CreateSearchTaskRequest request) {
        return ApiResponse.success(shoppingService.createSearchTask(userId(authentication), request));
    }

    @GetMapping
    public ApiResponse<PageData<SearchTaskSummaryDto>> history(
            Authentication authentication,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize
    ) {
        return ApiResponse.success(shoppingService.searchHistory(userId(authentication), page, pageSize));
    }

    @GetMapping("/{searchTaskId}")
    public ApiResponse<SearchTaskDto> get(Authentication authentication, @PathVariable long searchTaskId) {
        return ApiResponse.success(shoppingService.searchTask(userId(authentication), searchTaskId));
    }

    @PostMapping("/{searchTaskId}/refine")
    public ApiResponse<RefineSearchTaskPayload> refine(
            Authentication authentication,
            @PathVariable long searchTaskId,
            @RequestBody RefineSearchTaskRequest request
    ) {
        return ApiResponse.success(shoppingService.refineSearchTask(userId(authentication), searchTaskId, request));
    }

    private long userId(Authentication authentication) {
        return (Long) authentication.getPrincipal();
    }
}
