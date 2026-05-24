package com.ec26b.shoppingagent.api;

import com.ec26b.shoppingagent.api.ApiModels.*;
import com.ec26b.shoppingagent.service.ShoppingService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class ProductController {
    private final ShoppingService shoppingService;

    public ProductController(ShoppingService shoppingService) {
        this.shoppingService = shoppingService;
    }

    @GetMapping("/products/{productId}")
    public ApiResponse<ProductDto> product(@PathVariable long productId) {
        return ApiResponse.success(shoppingService.product(productId));
    }

    @GetMapping("/platform-products/{platformProductId}")
    public ApiResponse<PlatformProductDto> platformProduct(@PathVariable long platformProductId) {
        return ApiResponse.success(shoppingService.platformProduct(platformProductId));
    }

    @GetMapping("/platform-products/{platformProductId}/price-history")
    public ApiResponse<PriceHistoryDto> priceHistory(@PathVariable long platformProductId, @RequestParam(defaultValue = "90") int days) {
        return ApiResponse.success(shoppingService.priceHistory(platformProductId, days));
    }

    @GetMapping("/platform-products/{platformProductId}/review-summary")
    public ApiResponse<ReviewSummaryDto> reviewSummary(@PathVariable long platformProductId) {
        return ApiResponse.success(shoppingService.reviewSummary(platformProductId));
    }
}
