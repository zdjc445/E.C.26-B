package com.ec26b.shoppingagent.api;

import com.ec26b.shoppingagent.auth.AuthService;
import com.ec26b.shoppingagent.auth.CurrentUser;
import com.ec26b.shoppingagent.favorite.Favorite;
import com.ec26b.shoppingagent.favorite.FavoriteRepository;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/favorites")
public class FavoriteController {

    private final FavoriteRepository repository;
    private final CurrentUser currentUser;

    public FavoriteController(FavoriteRepository repository, CurrentUser currentUser) {
        this.repository = repository;
        this.currentUser = currentUser;
    }

    @PostMapping
    public ResponseEntity<ApiResponse<Favorite>> add(@RequestBody FavoriteRequest request,
                                                    HttpServletRequest http) {
        try {
            var auth = currentUser.require(http);
            if (request.productId() == null || request.productId().isBlank()
                    || request.title() == null || request.title().isBlank()) {
                return ResponseEntity.badRequest()
                        .body(ApiResponse.error(40001, "productId / title 不能为空"));
            }
            var payload = new FavoriteRepository.FavoritePayload(
                    request.productId(), request.title(), request.platform(),
                    request.price() == null ? 0 : request.price(),
                    request.shopName(), request.brand(),
                    request.imageUrl(), request.productUrl());
            return ResponseEntity.ok(ApiResponse.success(repository.add(auth.userId(), payload)));
        } catch (AuthService.AuthException ex) {
            return ResponseEntity.status(401)
                    .body(ApiResponse.error(ex.code(), ex.getMessage()));
        }
    }

    @GetMapping
    public ResponseEntity<ApiResponse<Map<String, Object>>> list(HttpServletRequest http) {
        try {
            var auth = currentUser.require(http);
            List<Favorite> items = repository.listByUser(auth.userId());
            return ResponseEntity.ok(ApiResponse.success(
                    Map.of("favorites", items, "total", items.size())));
        } catch (AuthService.AuthException ex) {
            return ResponseEntity.status(401)
                    .body(ApiResponse.error(ex.code(), ex.getMessage()));
        }
    }

    @DeleteMapping("/{productId}")
    public ResponseEntity<ApiResponse<Map<String, Object>>> delete(@PathVariable String productId,
                                                                  HttpServletRequest http) {
        try {
            var auth = currentUser.require(http);
            boolean removed = repository.delete(auth.userId(), productId);
            if (!removed) {
                return ResponseEntity.status(404)
                        .body(ApiResponse.error(40404, "收藏不存在"));
            }
            return ResponseEntity.ok(ApiResponse.success(Map.of("deleted", true)));
        } catch (AuthService.AuthException ex) {
            return ResponseEntity.status(401)
                    .body(ApiResponse.error(ex.code(), ex.getMessage()));
        }
    }

    public record FavoriteRequest(
            String productId,
            String title,
            String platform,
            Double price,
            String shopName,
            String brand,
            String imageUrl,
            String productUrl) {}
}
