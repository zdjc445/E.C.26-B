package com.ec26b.shoppingagent.chat;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Optional;

/**
 * Default in-memory implementation — requires no database.
 */
@Component
@ConditionalOnProperty(name = "chat.history-store", havingValue = "memory", matchIfMissing = true)
public class InMemoryChatHistoryRepository implements ChatHistoryRepository {

    private final ChatStore store;

    public InMemoryChatHistoryRepository(ChatStore store) {
        this.store = store;
    }

    @Override
    public ChatStore.ChatSession createSession() {
        return store.createSession();
    }

    @Override
    public Optional<ChatStore.ChatSession> findById(String sessionId) {
        return store.findById(sessionId);
    }

    @Override
    public void addMessage(String sessionId, ChatStore.MessageRecord msg) {
        store.addMessage(sessionId, msg);
    }

    @Override
    public List<ChatStore.SessionSummary> listSessions() {
        return store.listSessions().stream()
                .map(ChatStore.SessionSummary::from)
                .toList();
    }

    @Override
    public Optional<ChatStore.SessionSummary> renameSession(String sessionId, String newTitle) {
        return store.renameSession(sessionId, newTitle)
                .map(ChatStore.SessionSummary::from);
    }

    @Override
    public boolean deleteSession(String sessionId) {
        return store.deleteSession(sessionId);
    }
}
