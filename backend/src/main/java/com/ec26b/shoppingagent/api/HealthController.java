package com.ec26b.shoppingagent.api;

import com.ec26b.shoppingagent.api.ApiModels.ApiResponse;
import com.ec26b.shoppingagent.api.ApiModels.EcommerceDiagnosticsPayload;
import com.ec26b.shoppingagent.api.ApiModels.EcommerceStatusPayload;
import com.ec26b.shoppingagent.ecommerce.OfficialProductSourceProvider;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

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
            @RequestParam(defaultValue = "3") int pageSize
    ) {
        return ApiResponse.success(officialProductSource.diagnostics(query, pageSize));
    }
}
