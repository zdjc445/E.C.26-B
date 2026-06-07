package com.ec26b.shoppingagent.api;

import com.ec26b.shoppingagent.product.RealEcommerceProvider;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Exposes ecommerce data source status so the client can show degraded-mode
 * badges (mock vs real, fallback reasons).
 */
@RestController
@RequestMapping("/api/ecommerce")
public class EcommerceController {

    private final RealEcommerceProvider realProvider;
    private final boolean realProviderConfigured;
    private final String realProviderBaseUrl;

    public EcommerceController(RealEcommerceProvider realProvider,
                               @Value("${app.ecommerce.real-provider-enabled:false}") boolean realProviderConfigured,
                               @Value("${app.ecommerce.real-provider-base-url:}") String realProviderBaseUrl) {
        this.realProvider = realProvider;
        this.realProviderConfigured = realProviderConfigured;
        this.realProviderBaseUrl = realProviderBaseUrl == null ? "" : realProviderBaseUrl;
    }

    @GetMapping("/status")
    public ResponseEntity<ApiResponse<Map<String, Object>>> status() {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("activeProvider", realProvider.enabled() ? "real" : "mock");
        data.put("realProviderEnabled", realProviderConfigured);
        data.put("realProviderActive", realProvider.enabled());
        data.put("realProviderBaseUrl",
                realProviderBaseUrl.isBlank() ? null : realProviderBaseUrl);
        data.put("mockPlatforms", java.util.List.of("京东-mock", "拼多多-mock", "淘宝-mock"));
        data.put("mockCategories", java.util.List.of("运动鞋", "耳机", "吹风机", "背包", "智能手表"));
        data.put("fallbackPolicy",
                "real provider 不可用或返回空时回退到 MockProductSourceProvider，保证演示路径稳定。");
        return ResponseEntity.ok(ApiResponse.success(data));
    }
}
