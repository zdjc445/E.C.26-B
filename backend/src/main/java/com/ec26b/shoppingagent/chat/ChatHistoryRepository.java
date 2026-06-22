package com.ec26b.shoppingagent.chat;

import java.util.List;
import java.util.Optional;

/**
 * Abstraction for chat history persistence.
 *
 * <p>{@code app.persistence.store=memory} (default) uses the in-memory implementation
 * and requires no database. {@code app.persistence.store=postgres} enables Postgres
 * persistence via Flyway-managed schema.
 */
public interface ChatHistoryRepository {

    ChatStore.ChatSession createSession();

    Optional<ChatStore.ChatSession> findById(String sessionId);

    void addMessage(String sessionId, ChatStore.MessageRecord msg);

    List<ChatStore.SessionSummary> listSessions();

    Optional<ChatStore.SessionSummary> renameSession(String sessionId, String newTitle);

    boolean deleteSession(String sessionId);
}
