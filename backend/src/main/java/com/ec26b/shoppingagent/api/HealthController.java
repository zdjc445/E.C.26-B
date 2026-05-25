package com.ec26b.shoppingagent.api;

import com.ec26b.shoppingagent.api.ApiModels.ApiResponse;
import com.ec26b.shoppingagent.api.ApiModels.EcommerceDiagnosticsPayload;
import com.ec26b.shoppingagent.api.ApiModels.EcommerceStatusPayload;
import com.ec26b.shoppingagent.ecommerce.OfficialProductSourceProvider;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@RestController
public class HealthController {
    private final OfficialProductSourceProvider officialProductSource;

    public HealthController(OfficialProductSourceProvider officialProductSource) {
        this.officialProductSource = officialProductSource;
    }

    @GetMapping("/api/health")
    public ApiResponse<Map<String, String>> health() {
        return ApiResponse.success(Map.of("status", "ok"));
    }

    @GetMapping("/api/ecommerce/status")
    public ApiResponse<EcommerceStatusPayload> ecommerceStatus() {
        return ApiResponse.success(officialProductSource.status());
    }

    @GetMapping("/api/ecommerce/diagnostics")
    public ApiResponse<EcommerceDiagnosticsPayload> ecommerceDiagnostics(
            @RequestParam(defaultValue = "吹风机") String query,
            @RequestParam(defaultValue = "3") int pageSize,
            @RequestParam(required = false) List<String> platforms,
            @RequestParam(required = false) String minPrice,
            @RequestParam(required = false) String maxPrice,
            @RequestParam(required = false) Boolean withCoupon,
            @RequestParam(required = false) Boolean officialOnly,
            @RequestParam(required = false) Boolean selfOperatedOnly
    ) {
        Map<String, Object> filters = new java.util.LinkedHashMap<>();
        putIfPresent(filters, "minPrice", minPrice);
        putIfPresent(filters, "maxPrice", maxPrice);
        putIfPresent(filters, "withCoupon", withCoupon);
        putIfPresent(filters, "officialOnly", officialOnly);
        putIfPresent(filters, "selfOperatedOnly", selfOperatedOnly);
        return ApiResponse.success(officialProductSource.diagnostics(query, pageSize, platforms, filters));
    }

    private void putIfPresent(Map<String, Object> filters, String key, Object value) {
        if (value != null && (!(value instanceof String text) || !text.isBlank())) {
            filters.put(key, value);
        }
    }
}
