package com.ec26b.shoppingagent.api;

import com.ec26b.shoppingagent.alert.PriceAlert;
import com.ec26b.shoppingagent.alert.PriceAlertRepository;
import com.ec26b.shoppingagent.auth.AuthService;
import com.ec26b.shoppingagent.auth.CurrentUser;
import com.ec26b.shoppingagent.product.MockProductSourceProvider;
import com.ec26b.shoppingagent.product.ProductOffer;
import com.ec26b.shoppingagent.product.ProductSearchQuery;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/price-alerts")
public class PriceAlertController {

    private final PriceAlertRepository repository;
    private final CurrentUser currentUser;
    private final MockProductSourceProvider productSource;

    public PriceAlertController(PriceAlertRepository repository, CurrentUser currentUser,
                                MockProductSourceProvider productSource) {
        this.repository = repository;
        this.currentUser = currentUser;
        this.productSource = productSource;
    }

    @PostMapping
    public ResponseEntity<ApiResponse<PriceAlert>> create(@RequestBody PriceAlertRequest request,
                                                          HttpServletRequest http) {
        try {
            var auth = currentUser.require(http);
            if (request.productId() == null || request.productId().isBlank()
                    || request.title() == null || request.title().isBlank()) {
                return ResponseEntity.badRequest()
                        .body(ApiResponse.error(40001, "productId / title 不能为空"));
            }
            if (request.targetPrice() == null || request.targetPrice() <= 0) {
                return ResponseEntity.badRequest()
                        .body(ApiResponse.error(40001, "targetPrice 必须大于 0"));
            }
            var payload = new PriceAlertRepository.PriceAlertPayload(
                    request.productId(), request.title(), request.platform(),
                    request.targetPrice(), request.note());
            return ResponseEntity.ok(ApiResponse.success(repository.create(auth.userId(), payload)));
        } catch (AuthService.AuthException ex) {
            return ResponseEntity.status(401)
                    .body(ApiResponse.error(ex.code(), ex.getMessage()));
        }
    }

    @GetMapping
    public ResponseEntity<ApiResponse<Map<String, Object>>> list(HttpServletRequest http) {
        try {
            var auth = currentUser.require(http);
            List<PriceAlert> alerts = repository.listByUser(auth.userId());
            return ResponseEntity.ok(ApiResponse.success(
                    Map.of("alerts", alerts, "total", alerts.size())));
        } catch (AuthService.AuthException ex) {
            return ResponseEntity.status(401)
                    .body(ApiResponse.error(ex.code(), ex.getMessage()));
        }
    }

    @DeleteMapping("/{alertId}")
    public ResponseEntity<ApiResponse<Map<String, Object>>> delete(@PathVariable long alertId,
                                                                  HttpServletRequest http) {
        try {
            var auth = currentUser.require(http);
            boolean removed = repository.delete(auth.userId(), alertId);
            if (!removed) {
                return ResponseEntity.status(404)
                        .body(ApiResponse.error(40404, "提醒不存在"));
            }
            return ResponseEntity.ok(ApiResponse.success(Map.of("deleted", true)));
        } catch (AuthService.AuthException ex) {
            return ResponseEntity.status(401)
                    .body(ApiResponse.error(ex.code(), ex.getMessage()));
        }
    }

    /**
     * Evaluates current Mock prices against the user's alerts and updates
     * triggered status. Demo-only — production would poll real platform APIs.
     */
    @PostMapping("/check")
    public ResponseEntity<ApiResponse<Map<String, Object>>> check(HttpServletRequest http) {
        try {
            var auth = currentUser.require(http);
            List<PriceAlert> alerts = repository.listByUser(auth.userId());
            int triggeredCount = 0;
            List<Map<String, Object>> evaluated = new java.util.ArrayList<>();
            for (PriceAlert a : alerts) {
                ProductOffer offer = findOfferByProductId(a.productId());
                if (offer == null) {
                    evaluated.add(rowOf(a, null, false, "current price not found in mock catalog"));
                    continue;
                }
                boolean triggered = offer.price() <= a.targetPrice();
                if (triggered) triggeredCount++;
                repository.markObserved(auth.userId(), a.id(), offer.price(), triggered);
                evaluated.add(rowOf(a, offer.price(), triggered, null));
            }
            return ResponseEntity.ok(ApiResponse.success(Map.of(
                    "checked", alerts.size(),
                    "triggered", triggeredCount,
                    "results", evaluated)));
        } catch (AuthService.AuthException ex) {
            return ResponseEntity.status(401)
                    .body(ApiResponse.error(ex.code(), ex.getMessage()));
        }
    }

    private ProductOffer findOfferByProductId(String productId) {
        for (String keyword : List.of("运动鞋", "耳机", "吹风机", "背包", "智能手表")) {
            var sr = productSource.search(new ProductSearchQuery(keyword, List.of(), null));
            for (var p : sr.products()) {
                if (p.productId().equals(productId)) return p;
            }
        }
        return null;
    }

    private Map<String, Object> rowOf(PriceAlert a, Double observed, boolean triggered, String note) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("alertId", a.id());
        m.put("productId", a.productId());
        m.put("title", a.title());
        m.put("targetPrice", a.targetPrice());
        m.put("observedPrice", observed);
        m.put("triggered", triggered);
        if (note != null) m.put("note", note);
        return m;
    }

    public record PriceAlertRequest(
            String productId,
            String title,
            String platform,
            Double targetPrice,
            String note) {}
}
