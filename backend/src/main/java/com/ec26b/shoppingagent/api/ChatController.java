package com.ec26b.shoppingagent.api;

import com.ec26b.shoppingagent.chat.ChatStore;
import com.ec26b.shoppingagent.chat.MockAgent;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@RestController
public class ChatController {

    private final ChatStore chatStore;
    private final MockAgent mockAgent;

    public ChatController(ChatStore chatStore, MockAgent mockAgent) {
        this.chatStore = chatStore;
        this.mockAgent = mockAgent;
    }

    @PostMapping("/api/chat/sessions")
    public ResponseEntity<ApiResponse<Map<String, Object>>> createSession() {
        var session = chatStore.createSession();
        Map<String, Object> data = Map.of(
                "sessionId", session.sessionId(),
                "createdAt", session.createdAt().toString()
        );
        return ResponseEntity.ok(ApiResponse.success(data));
    }

    @PostMapping("/api/chat/sessions/{sessionId}/messages")
    public ResponseEntity<ApiResponse<MockAgent.AgentReply>> sendMessage(
            @PathVariable String sessionId,
            @RequestBody ChatMessageRequest request) {

        var sessionOpt = chatStore.findById(sessionId);
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

        // Record user message
        var userMsg = new ChatStore.MessageRecord(
                UUID.randomUUID().toString(),
                "user",
                request.text(),
                request.imageIds() != null ? request.imageIds() : List.of(),
                request.selectedOptionIds() != null ? request.selectedOptionIds() : List.of(),
                OffsetDateTime.now()
        );
        chatStore.addMessage(sessionId, userMsg);

        // Generate agent reply
        var session = sessionOpt.get();
        var reply = mockAgent.process(session, request.text(),
                request.imageIds(), request.selectedOptionIds());

        // Record assistant message
        var assistantMsg = new ChatStore.MessageRecord(
                reply.replyId(),
                "assistant",
                reply.text(),
                List.of(),
                List.of(),
                OffsetDateTime.now()
        );
        chatStore.addMessage(sessionId, assistantMsg);

        return ResponseEntity.ok(ApiResponse.success(reply));
    }

    public record ChatMessageRequest(
            String text,
            List<String> imageIds,
            List<String> selectedOptionIds
    ) {}
}
