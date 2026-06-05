package com.ec26b.shoppingagent.api;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.OffsetDateTime;
import java.util.Map;

@RestController
public class HealthController {

    @GetMapping("/api/health")
    public Map<String, Object> health() {
        return Map.of(
            "status", "ok",
            "app", "shopping-agent",
            "stage", "skeleton",
            "aiProvider", "mock",
            "timestamp", OffsetDateTime.now().toString()
        );
    }
}
