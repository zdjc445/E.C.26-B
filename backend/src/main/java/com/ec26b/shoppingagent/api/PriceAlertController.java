package com.ec26b.shoppingagent.api;

import com.ec26b.shoppingagent.api.ApiModels.*;
import com.ec26b.shoppingagent.service.ShoppingService;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/price-alerts")
public class PriceAlertController {
    private final ShoppingService shoppingService;

    public PriceAlertController(ShoppingService shoppingService) {
        this.shoppingService = shoppingService;
    }

    @PostMapping
    public ApiResponse<PriceAlertDto> create(Authentication authentication, @RequestBody CreatePriceAlertRequest request) {
        return ApiResponse.success(shoppingService.createPriceAlert(userId(authentication), request));
    }

    @GetMapping
    public ApiResponse<PageData<PriceAlertDto>> list(
            Authentication authentication,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize
    ) {
        return ApiResponse.success(shoppingService.priceAlerts(userId(authentication), page, pageSize));
    }

    @PatchMapping("/{priceAlertId}")
    public ApiResponse<PriceAlertDto> update(Authentication authentication, @PathVariable long priceAlertId, @RequestBody UpdatePriceAlertRequest request) {
        return ApiResponse.success(shoppingService.updatePriceAlert(userId(authentication), priceAlertId, request));
    }

    @DeleteMapping("/{priceAlertId}")
    public ApiResponse<Void> delete(Authentication authentication, @PathVariable long priceAlertId) {
        shoppingService.deletePriceAlert(userId(authentication), priceAlertId);
        return ApiResponse.empty();
    }

    private long userId(Authentication authentication) {
        return (Long) authentication.getPrincipal();
    }
}
