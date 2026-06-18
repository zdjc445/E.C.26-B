package com.ec26b.shoppingagent.api;

import com.ec26b.shoppingagent.product.ProductSourceProvider;
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

    private final ProductSourceProvider productSourceProvider;

    public EcommerceController(ProductSourceProvider productSourceProvider) {
        this.productSourceProvider = productSourceProvider;
    }

    @GetMapping("/status")
    public ResponseEntity<ApiResponse<Map<String, Object>>> status() {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("activeProvider", productSourceProvider.sourceName());
        data.put("realProviderEnabled", false);
        data.put("realProviderActive", false);
        data.put("realProviderBaseUrl", null);
        data.put("samplePlatforms", java.util.List.of("京东", "淘宝", "天猫", "拼多多"));
        data.put("sampleCategories",
                java.util.List.of("运动鞋", "耳机", "吹风机", "背包"));
        data.put("fallbackPolicy",
                "默认读取公开样例商品，并扩展为四个平台的演示报价；不调用真实电商接口。");
        return ResponseEntity.ok(ApiResponse.success(data));
    }
}
