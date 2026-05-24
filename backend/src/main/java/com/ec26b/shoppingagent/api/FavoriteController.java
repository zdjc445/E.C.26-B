package com.ec26b.shoppingagent.api;

import com.ec26b.shoppingagent.api.ApiModels.*;
import com.ec26b.shoppingagent.service.ShoppingService;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/favorites")
public class FavoriteController {
    private final ShoppingService shoppingService;

    public FavoriteController(ShoppingService shoppingService) {
        this.shoppingService = shoppingService;
    }

    @PostMapping
    public ApiResponse<FavoriteDto> create(Authentication authentication, @RequestBody CreateFavoriteRequest request) {
        return ApiResponse.success(shoppingService.createFavorite(userId(authentication), request));
    }

    @GetMapping
    public ApiResponse<PageData<FavoriteDto>> list(
            Authentication authentication,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize
    ) {
        return ApiResponse.success(shoppingService.favorites(userId(authentication), page, pageSize));
    }

    @DeleteMapping("/{favoriteId}")
    public ApiResponse<Void> delete(Authentication authentication, @PathVariable long favoriteId) {
        shoppingService.deleteFavorite(userId(authentication), favoriteId);
        return ApiResponse.empty();
    }

    private long userId(Authentication authentication) {
        return (Long) authentication.getPrincipal();
    }
}
