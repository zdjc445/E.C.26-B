package com.ec26b.shoppingagent.chat;

import org.springframework.stereotype.Component;

import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

@Component
public class ChatStore {

    private final Map<String, ChatSession> sessions = new ConcurrentHashMap<>();

    public ChatSession createSession() {
        var session = new ChatSession(
                UUID.randomUUID().toString(),
                OffsetDateTime.now(),
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
        }
    }

    public List<MessageRecord> getMessages(String sessionId) {
        var session = sessions.get(sessionId);
        if (session == null) {
            return List.of();
        }
        return List.copyOf(session.messages());
    }

    public record ChatSession(
            String sessionId,
            OffsetDateTime createdAt,
            List<MessageRecord> messages
    ) {}

    public record MessageRecord(
            String messageId,
            String role,        // "user" or "assistant"
            String text,
            List<String> imageIds,
            List<String> selectedOptionIds,
            OffsetDateTime createdAt
    ) {}
}
