package com.ec26b.shoppingagent.api;

import com.ec26b.shoppingagent.api.ApiModels.ApiResponse;
import com.ec26b.shoppingagent.api.ApiModels.AiRuntimeHealth;
import com.ec26b.shoppingagent.api.ApiModels.DatasetHealth;
import com.ec26b.shoppingagent.api.ApiModels.EcommerceDiagnosticsPayload;
import com.ec26b.shoppingagent.api.ApiModels.EcommerceStatusPayload;
import com.ec26b.shoppingagent.api.ApiModels.HealthPayload;
import com.ec26b.shoppingagent.api.ApiModels.PersistenceHealth;
import com.ec26b.shoppingagent.ai.AiRecognitionProvider;
import com.ec26b.shoppingagent.ai.AiRefineProvider;
import com.ec26b.shoppingagent.ecommerce.OfficialProductSourceProvider;
import com.ec26b.shoppingagent.persistence.ShoppingStateRepository;
import com.ec26b.shoppingagent.service.MockCatalog;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.OffsetDateTime;
import java.util.Arrays;
import java.util.List;
import java.util.Map;

@RestController
public class HealthController {
    private final OfficialProductSourceProvider officialProductSource;
    private final MockCatalog catalog;
    private final AiRecognitionProvider recognitionProvider;
    private final AiRefineProvider refineProvider;
    private final ShoppingStateRepository stateRepository;
    private final Environment environment;
    private final boolean persistenceFailFast;

    public HealthController(
            OfficialProductSourceProvider officialProductSource,
            MockCatalog catalog,
            AiRecognitionProvider recognitionProvider,
            AiRefineProvider refineProvider,
            ShoppingStateRepository stateRepository,
            Environment environment,
            @Value("${app.persistence.fail-fast:false}") boolean persistenceFailFast
    ) {
        this.officialProductSource = officialProductSource;
        this.catalog = catalog;
        this.recognitionProvider = recognitionProvider;
        this.refineProvider = refineProvider;
        this.stateRepository = stateRepository;
        this.environment = environment;
        this.persistenceFailFast = persistenceFailFast;
    }

    @GetMapping("/api/health")
    public ApiResponse<HealthPayload> health() {
        return ApiResponse.success(new HealthPayload(
                "ok",
                activeProfile(),
                new DatasetHealth(
                        catalog.products().size(),
                        catalog.platformProducts().size(),
                        catalog.recognitionSampleCount(),
                        catalog.priceHistoryCount(),
                        catalog.reviewSummaryCount(),
                        catalog.categories(),
                        catalog.platforms()
                ),
                new AiRuntimeHealth(
                        recognitionProvider.providerName(),
                        refineProvider.providerName()
                ),
                new PersistenceHealth(persistenceMode(), persistenceFailFast),
                officialProductSource.status(),
                OffsetDateTime.now()
        ));
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
            @RequestParam(required = false) Boolean selfOperatedOnly,
            @RequestParam(required = false) String sortBy
    ) {
        Map<String, Object> filters = new java.util.LinkedHashMap<>();
        putIfPresent(filters, "minPrice", minPrice);
        putIfPresent(filters, "maxPrice", maxPrice);
        putIfPresent(filters, "withCoupon", withCoupon);
        putIfPresent(filters, "officialOnly", officialOnly);
        putIfPresent(filters, "selfOperatedOnly", selfOperatedOnly);
        return ApiResponse.success(officialProductSource.diagnostics(query, pageSize, platforms, filters, sortBy));
    }

    private void putIfPresent(Map<String, Object> filters, String key, Object value) {
        if (value != null && (!(value instanceof String text) || !text.isBlank())) {
            filters.put(key, value);
        }
    }

    private String activeProfile() {
        String[] profiles = environment.getActiveProfiles();
        if (profiles.length == 0) {
            return "default";
        }
        return String.join(",", profiles);
    }

    private String persistenceMode() {
        String name = stateRepository.getClass().getSimpleName();
        if (name.contains("Postgres")) {
            return "postgres";
        }
        if (name.contains("Noop")) {
            return "memory";
        }
        if (name.contains("Recording")) {
            return "recording";
        }
        return Arrays.stream(name.split("\\$"))
                .reduce((first, second) -> second)
                .orElse(name);
    }
}
