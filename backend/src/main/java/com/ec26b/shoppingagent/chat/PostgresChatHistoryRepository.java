package com.ec26b.shoppingagent.chat;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Optional;

/**
 * Postgres-backed implementation skeleton.
 *
 * <p>Activated with {@code chat.history-store=postgres}. Requires a running
 * Postgres instance and Flyway migrations. Currently throws an informative
 * error — implement the JDBC / JPA wiring when Postgres integration is scheduled.
 */
@Component
@ConditionalOnProperty(name = "chat.history-store", havingValue = "postgres")
public class PostgresChatHistoryRepository implements ChatHistoryRepository {

    public PostgresChatHistoryRepository() {
        // placeholder — JDBC / JPA wiring will be added in a later iteration
    }

    @Override
    public ChatStore.ChatSession createSession() {
        throw new UnsupportedOperationException(
                "Postgres chat history not yet implemented. "
                + "Set chat.history-store=memory or implement JDBC wiring."
        );
    }

    @Override
    public Optional<ChatStore.ChatSession> findById(String sessionId) {
        throw new UnsupportedOperationException(
                "Postgres chat history not yet implemented."
        );
    }

    @Override
    public void addMessage(String sessionId, ChatStore.MessageRecord msg) {
        throw new UnsupportedOperationException(
                "Postgres chat history not yet implemented."
        );
    }

    @Override
    public List<ChatStore.SessionSummary> listSessions() {
        throw new UnsupportedOperationException(
                "Postgres chat history not yet implemented."
        );
    }

    @Override
    public Optional<ChatStore.SessionSummary> renameSession(String sessionId, String newTitle) {
        throw new UnsupportedOperationException(
                "Postgres chat history not yet implemented."
        );
    }

    @Override
    public boolean deleteSession(String sessionId) {
        throw new UnsupportedOperationException(
                "Postgres chat history not yet implemented."
        );
    }
}
