package com.ec26b.shoppingagent.api;

import com.ec26b.shoppingagent.image.ImageStore;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Map;
import java.util.UUID;

@RestController
public class ImageController {

    private final ImageStore imageStore;
    private final Path uploadDir;

    public ImageController(ImageStore imageStore,
                           @Value("${app.upload-dir:../uploads}") String uploadDirPath) {
        this.imageStore = imageStore;
        this.uploadDir = Paths.get(uploadDirPath).toAbsolutePath().normalize();
    }

    @PostMapping("/api/images/upload")
    public ResponseEntity<ApiResponse<Map<String, Object>>> upload(
            @RequestParam(value = "file", required = false) MultipartFile file) {

        if (file == null || file.isEmpty()) {
            return ResponseEntity.badRequest()
                    .body(ApiResponse.error(40001, "文件为空或缺失"));
        }

        try {
            Files.createDirectories(uploadDir);

            String imageId = UUID.randomUUID().toString();
            String originalName = file.getOriginalFilename();
            String ext = safeExtension(originalName);
            String storedName = imageId + ext;

            Path dest = uploadDir.resolve(storedName);
            file.transferTo(dest.toFile());

            var meta = imageStore.save(imageId, storedName, originalName,
                    file.getContentType(), file.getSize());

            Map<String, Object> data = Map.of(
                    "imageId", meta.imageId(),
                    "fileName", meta.storedFileName(),
                    "contentType", meta.contentType() != null ? meta.contentType() : "application/octet-stream",
                    "size", meta.size()
            );

            return ResponseEntity.ok(ApiResponse.success(data));

        } catch (IOException e) {
            return ResponseEntity.internalServerError()
                    .body(ApiResponse.error(50000, "文件保存失败"));
        }
    }

    private static String safeExtension(String originalName) {
        if (originalName == null) {
            return "";
        }
        int dotIndex = originalName.lastIndexOf('.');
        if (dotIndex < 0 || dotIndex == originalName.length() - 1) {
            return "";
        }
        String ext = originalName.substring(dotIndex);
        if (ext.length() > 11) {
            return "";
        }
        for (int i = 1; i < ext.length(); i++) {
            if (!Character.isLetterOrDigit(ext.charAt(i))) {
                return "";
            }
        }
        return ext;
    }
}
