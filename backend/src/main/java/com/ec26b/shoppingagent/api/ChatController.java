package com.ec26b.shoppingagent.api;

import com.ec26b.shoppingagent.ai.*;
import com.ec26b.shoppingagent.chat.ChatHistoryRepository;
import com.ec26b.shoppingagent.chat.ChatStore;
import com.ec26b.shoppingagent.chat.MockAgent;
import com.ec26b.shoppingagent.image.ImageStore;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@RestController
public class ChatController {

    private final ChatHistoryRepository repo;
    private final MockAgent mockAgent;
    private final AiRecognitionProvider aiProvider;
    private final RecognitionStore recognitionStore;
    private final ImageStore imageStore;
    private final Path uploadDir;

    public ChatController(ChatHistoryRepository repo, MockAgent mockAgent,
                          AiRecognitionProvider aiProvider,
                          RecognitionStore recognitionStore,
                          ImageStore imageStore,
                          @Value("${app.upload-dir:../uploads}") String uploadDirPath) {
        this.repo = repo;
        this.mockAgent = mockAgent;
        this.aiProvider = aiProvider;
        this.recognitionStore = recognitionStore;
        this.imageStore = imageStore;
        this.uploadDir = Paths.get(uploadDirPath).toAbsolutePath().normalize();
    }

    // ── Create session ───────────────────────────────────────────

    @PostMapping("/api/chat/sessions")
    public ResponseEntity<ApiResponse<Map<String, Object>>> createSession() {
        var session = repo.createSession();
        Map<String, Object> data = Map.of(
                "sessionId", session.sessionId(),
                "createdAt", session.createdAt().toString()
        );
        return ResponseEntity.ok(ApiResponse.success(data));
    }

    // ── List sessions ────────────────────────────────────────────

    @GetMapping("/api/chat/sessions")
    public ResponseEntity<ApiResponse<Map<String, Object>>> listSessions() {
        var summaries = repo.listSessions();
        return ResponseEntity.ok(ApiResponse.success(Map.of("sessions", summaries)));
    }

    // ── Send message ─────────────────────────────────────────────

    @PostMapping("/api/chat/sessions/{sessionId}/messages")
    public ResponseEntity<ApiResponse<MockAgent.AgentReply>> sendMessage(
            @PathVariable String sessionId,
            @RequestBody ChatMessageRequest request) {

        var sessionOpt = repo.findById(sessionId);
        if (sessionOpt.isEmpty()) {
            return ResponseEntity.status(404)
                    .body(ApiResponse.error(40004, "会话不存在"));
        }

        boolean hasText = request.text() != null && !request.text().isBlank();
        boolean hasImages = request.imageIds() != null && !request.imageIds().isEmpty();
        boolean hasOptions = request.selectedOptionIds() != null && !request.selectedOptionIds().isEmpty();

        if (!hasText && !hasImages && !hasOptions) {
            return ResponseEntity.badRequest()
                    .body(ApiResponse.error(40001, "text、imageIds、selectedOptionIds 至少需要一个有效内容"));
        }

        // Validate images before proceeding
        if (hasImages && !hasOptions) {
            String imageId = request.imageIds().get(0);
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
                return ResponseEntity.status(500)
                        .body(ApiResponse.error(50000, "读取图片文件失败"));
            }
            var payload = new ImagePayload(imageId, meta.contentType(), imageBytes, meta.originalFileName());
            RecognitionResult recResult = aiProvider.recognize(payload);
            recognitionStore.save(recResult);

            var userMsg = new ChatStore.MessageRecord(
                    UUID.randomUUID().toString(),
                    "user",
                    request.text(),
                    request.imageIds() != null ? request.imageIds() : List.of(),
                    request.selectedOptionIds() != null ? request.selectedOptionIds() : List.of(),
                    OffsetDateTime.now(),
                    null
            );
            repo.addMessage(sessionId, userMsg);

            MockAgent.AgentReply reply = mockAgent.processWithRecognition(sessionOpt.get(),
                    request.text(), request.imageIds(), request.selectedOptionIds(),
                    recResult, request.profile());

            var assistantMsg = new ChatStore.MessageRecord(
                    reply.replyId(),
                    "assistant",
                    reply.text(),
                    List.of(),
                    List.of(),
                    OffsetDateTime.now(),
                    reply
            );
            repo.addMessage(sessionId, assistantMsg);
            return ResponseEntity.ok(ApiResponse.success(reply));
        }

        var userMsg = new ChatStore.MessageRecord(
                UUID.randomUUID().toString(),
                "user",
                request.text(),
                request.imageIds() != null ? request.imageIds() : List.of(),
                request.selectedOptionIds() != null ? request.selectedOptionIds() : List.of(),
                OffsetDateTime.now(),
                null
        );
        repo.addMessage(sessionId, userMsg);

        MockAgent.AgentReply reply = mockAgent.process(sessionOpt.get(), request.text(),
                request.imageIds(), request.selectedOptionIds(), request.profile());

        var assistantMsg = new ChatStore.MessageRecord(
                reply.replyId(),
                "assistant",
                reply.text(),
                List.of(),
                List.of(),
                OffsetDateTime.now(),
                reply
        );
        repo.addMessage(sessionId, assistantMsg);

        return ResponseEntity.ok(ApiResponse.success(reply));
    }

    // ── Get session messages ─────────────────────────────────────

    @GetMapping("/api/chat/sessions/{sessionId}/messages")
    public ResponseEntity<ApiResponse<Map<String, Object>>> getMessages(
            @PathVariable String sessionId) {

        var sessionOpt = repo.findById(sessionId);
        if (sessionOpt.isEmpty()) {
            return ResponseEntity.status(404)
                    .body(ApiResponse.error(40004, "会话不存在"));
        }

        var session = sessionOpt.get();
        List<Map<String, Object>> messages = session.messages().stream()
                .map(this::toMessageMap)
                .toList();

        Map<String, Object> data = Map.of(
                "sessionId", session.sessionId(),
                "messages", messages
        );
        return ResponseEntity.ok(ApiResponse.success(data));
    }

    // ── Rename session ───────────────────────────────────────────

    @PatchMapping("/api/chat/sessions/{sessionId}")
    public ResponseEntity<ApiResponse<?>> renameSession(
            @PathVariable String sessionId,
            @RequestBody Map<String, String> body) {

        String title = body.getOrDefault("title", "");
        String trimmed = title.trim();

        if (trimmed.isEmpty()) {
            return ResponseEntity.badRequest()
                    .body(ApiResponse.error(40001, "标题不能为空"));
        }
        if (trimmed.length() > 40) {
            return ResponseEntity.badRequest()
                    .body(ApiResponse.error(40001, "标题最多 40 个字符"));
        }

        var updated = repo.renameSession(sessionId, trimmed);
        if (updated.isEmpty()) {
            return ResponseEntity.status(404)
                    .body(ApiResponse.error(40004, "会话不存在"));
        }
        return ResponseEntity.ok(ApiResponse.success(updated.get()));
    }

    // ── Delete session ───────────────────────────────────────────

    @DeleteMapping("/api/chat/sessions/{sessionId}")
    public ResponseEntity<ApiResponse<Map<String, Object>>> deleteSession(
            @PathVariable String sessionId) {

        boolean deleted = repo.deleteSession(sessionId);
        if (!deleted) {
            return ResponseEntity.status(404)
                    .body(ApiResponse.error(40004, "会话不存在"));
        }
        return ResponseEntity.ok(ApiResponse.success(Map.of("deleted", true)));
    }

    // ── Helpers ──────────────────────────────────────────────────

    private Map<String, Object> toMessageMap(ChatStore.MessageRecord m) {
        var map = new java.util.LinkedHashMap<String, Object>();
        map.put("messageId", m.messageId());
        map.put("role", m.role());
        map.put("text", m.text());
        map.put("imageIds", m.imageIds());
        map.put("selectedOptionIds", m.selectedOptionIds());
        map.put("createdAt", m.createdAt().toString());
        if (m.agentReply() != null) {
            map.put("agentReply", m.agentReply());
        }
        return map;
    }

    public record ChatMessageRequest(
            String text,
            List<String> imageIds,
            List<String> selectedOptionIds,
            Map<String, Object> profile
    ) {}
}
