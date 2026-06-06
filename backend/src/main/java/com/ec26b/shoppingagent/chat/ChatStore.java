package com.ec26b.shoppingagent.chat;

import org.springframework.stereotype.Component;

import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

@Component
public class ChatStore {

    private final Map<String, ChatSession> sessions = new ConcurrentHashMap<>();

    public ChatSession createSession() {
        var now = OffsetDateTime.now();
        var session = new ChatSession(
                UUID.randomUUID().toString(),
                "新对话",
                now,
                now,
                new ArrayList<>()
        );
        sessions.put(session.sessionId(), session);
        return session;
    }

    public Optional<ChatSession> findById(String sessionId) {
        return Optional.ofNullable(sessions.get(sessionId));
    }

    public void addMessage(String sessionId, MessageRecord msg) {
        var session = sessions.get(sessionId);
        if (session != null) {
            session.messages().add(msg);
            // Update updatedAt
            var updated = new ChatSession(
                    session.sessionId(), session.title(),
                    session.createdAt(), OffsetDateTime.now(),
                    session.messages()
            );
            sessions.put(sessionId, updated);

            // Auto-title for first user text
            if ("新对话".equals(updated.title())) {
                var firstUserMsg = updated.messages().stream()
                        .filter(m -> "user".equals(m.role()))
                        .findFirst();
                if (firstUserMsg.isPresent()) {
                    String autoTitle = generateTitle(firstUserMsg.get());
                    var titled = new ChatSession(
                            updated.sessionId(), autoTitle,
                            updated.createdAt(), updated.updatedAt(),
                            updated.messages()
                    );
                    sessions.put(sessionId, titled);
                }
            }
        }
    }

    public List<ChatSession> listSessions() {
        return sessions.values().stream()
                .sorted(Comparator.comparing(ChatSession::updatedAt).reversed())
                .toList();
    }

    public Optional<ChatSession> renameSession(String sessionId, String newTitle) {
        var session = sessions.get(sessionId);
        if (session == null) {
            return Optional.empty();
        }
        var renamed = new ChatSession(
                session.sessionId(), newTitle,
                session.createdAt(), session.updatedAt(),
                session.messages()
        );
        sessions.put(sessionId, renamed);
        return Optional.of(renamed);
    }

    public boolean deleteSession(String sessionId) {
        return sessions.remove(sessionId) != null;
    }

    private String generateTitle(MessageRecord firstUserMsg) {
        boolean hasText = firstUserMsg.text() != null && !firstUserMsg.text().isBlank();
        boolean hasImages = firstUserMsg.imageIds() != null && !firstUserMsg.imageIds().isEmpty();

        if (!hasText && hasImages) {
            return "图片购物需求";
        }

        if (hasText) {
            String cleaned = firstUserMsg.text().replaceAll("\\s+", " ").trim();
            if (cleaned.length() <= 18) {
                return cleaned;
            }
            return cleaned.substring(0, 18);
        }

        return "新对话";
    }

    /** Summary record for listing (no messages). */
    public record SessionSummary(
            String sessionId,
            String title,
            OffsetDateTime createdAt,
            OffsetDateTime updatedAt,
            int messageCount
    ) {
        public static SessionSummary from(ChatSession s) {
            return new SessionSummary(
                    s.sessionId(), s.title(), s.createdAt(),
                    s.updatedAt(), s.messages().size()
            );
        }
    }

    public record ChatSession(
            String sessionId,
            String title,
            OffsetDateTime createdAt,
            OffsetDateTime updatedAt,
            List<MessageRecord> messages
    ) {}

    public record MessageRecord(
            String messageId,
            String role,
            String text,
            List<String> imageIds,
            List<String> selectedOptionIds,
            OffsetDateTime createdAt,
            MockAgent.AgentReply agentReply
    ) {}
}
