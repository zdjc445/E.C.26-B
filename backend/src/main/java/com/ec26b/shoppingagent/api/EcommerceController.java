package com.ec26b.shoppingagent.api;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Exposes ecommerce data source status for the client profile page.
 */
@RestController
@RequestMapping("/api/ecommerce")
public class EcommerceController {

    @GetMapping("/status")
    public ResponseEntity<ApiResponse<Map<String, Object>>> status() {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("activeProvider", "mock");
        data.put("realProviderEnabled", false);
        data.put("realProviderActive", false);
        data.put("realProviderBaseUrl", null);
        data.put("mockPlatforms", java.util.List.of("京东-mock", "拼多多-mock", "淘宝-mock"));
        data.put("mockCategories", java.util.List.of("运动鞋", "耳机", "吹风机", "背包", "智能手表"));
        data.put("fallbackPolicy",
                "商品数据固定使用 MockProductSourceProvider，不调用真实电商接口。");
        return ResponseEntity.ok(ApiResponse.success(data));
    }
}
