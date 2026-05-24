package com.ec26b.shoppingagent.api;

import com.ec26b.shoppingagent.api.ApiModels.*;
import com.ec26b.shoppingagent.service.ShoppingService;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/images")
public class ImageController {
    private final ShoppingService shoppingService;

    public ImageController(ShoppingService shoppingService) {
        this.shoppingService = shoppingService;
    }

    @PostMapping
    public ApiResponse<ImageDto> upload(
            Authentication authentication,
            @RequestPart("file") MultipartFile file,
            @RequestParam(defaultValue = "recognition") String scene
    ) {
        return ApiResponse.success(shoppingService.uploadImage(userId(authentication), file, scene));
    }

    @GetMapping
    public ApiResponse<PageData<ImageDto>> list(
            Authentication authentication,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize
    ) {
        return ApiResponse.success(shoppingService.imagePage(userId(authentication), page, pageSize));
    }

    @DeleteMapping("/{imageId}")
    public ApiResponse<Void> delete(Authentication authentication, @PathVariable long imageId) {
        shoppingService.deleteImage(userId(authentication), imageId);
        return ApiResponse.empty();
    }

    private long userId(Authentication authentication) {
        return (Long) authentication.getPrincipal();
    }
}
