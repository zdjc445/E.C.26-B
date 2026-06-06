package com.ec26b.shoppingagent.api;

import com.ec26b.shoppingagent.ai.*;
import com.ec26b.shoppingagent.image.ImageStore;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Map;

@RestController
public class RecognitionController {

    private final AiRecognitionProvider aiProvider;
    private final RecognitionStore recognitionStore;
    private final ImageStore imageStore;
    private final Path uploadDir;

    public RecognitionController(AiRecognitionProvider aiProvider,
                                 RecognitionStore recognitionStore,
                                 ImageStore imageStore,
                                 @Value("${app.upload-dir:../uploads}") String uploadDirPath) {
        this.aiProvider = aiProvider;
        this.recognitionStore = recognitionStore;
        this.imageStore = imageStore;
        this.uploadDir = Paths.get(uploadDirPath).toAbsolutePath().normalize();
    }

    @PostMapping("/api/recognition")
    public ResponseEntity<ApiResponse<RecognitionResult>> recognize(
            @RequestBody Map<String, String> body) {

        String imageId = body.get("imageId");
        if (imageId == null || imageId.isBlank()) {
            return ResponseEntity.badRequest()
                    .body(ApiResponse.error(40001, "imageId 不能为空"));
        }

        var metaOpt = imageStore.findById(imageId);
        if (metaOpt.isEmpty()) {
            return ResponseEntity.status(404)
                    .body(ApiResponse.error(40004, "图片不存在"));
        }

        var meta = metaOpt.get();
        Path filePath = uploadDir.resolve(meta.storedFileName());
        if (!Files.exists(filePath)) {
            return ResponseEntity.status(404)
                    .body(ApiResponse.error(40004, "图片文件不存在"));
        }

        byte[] imageBytes;
        try {
            imageBytes = Files.readAllBytes(filePath);
        } catch (IOException e) {
            return ResponseEntity.internalServerError()
                    .body(ApiResponse.error(50000, "读取图片文件失败"));
        }

        var payload = new ImagePayload(
                imageId, meta.contentType(), imageBytes, meta.originalFileName());
        RecognitionResult result = aiProvider.recognize(payload);
        recognitionStore.save(result);

        return ResponseEntity.ok(ApiResponse.success(result));
    }

    @PatchMapping("/api/recognition/{recognitionId}/attributes")
    public ResponseEntity<ApiResponse<RecognitionResult>> updateAttributes(
            @PathVariable String recognitionId,
            @RequestBody Map<String, Object> body) {

        var opt = recognitionStore.findById(recognitionId);
        if (opt.isEmpty()) {
            return ResponseEntity.status(404)
                    .body(ApiResponse.error(40004, "识别结果不存在"));
        }

        var result = opt.get();

        if (body.containsKey("category") && body.get("category") instanceof String s) {
            result.setCategory(s);
        }
        if (body.containsKey("brand") && body.get("brand") instanceof String s) {
            result.setBrand(s);
        }
        if (body.containsKey("model") && body.get("model") instanceof String s) {
            result.setModel(s);
        }
        if (body.containsKey("attributes") && body.get("attributes") instanceof Map<?, ?> attrs) {
            @SuppressWarnings("unchecked")
            Map<String, Object> attrMap = (Map<String, Object>) attrs;
            result.setAttributes(attrMap);
        }

        result.addNotice("用户已修正识别属性");
        recognitionStore.save(result);

        return ResponseEntity.ok(ApiResponse.success(result));
    }
}
