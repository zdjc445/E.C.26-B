package com.ec26b.shoppingagent.chat;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

import java.sql.Timestamp;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

/**
 * Postgres-backed implementation of {@link ChatHistoryRepository}.
 *
 * <p>Activated with {@code chat.history-store=postgres}. Requires a running
 * Postgres instance with the V1 migration applied (see {@code db/migration}).
 */
@Component
@ConditionalOnProperty(name = "chat.history-store", havingValue = "postgres")
public class PostgresChatHistoryRepository implements ChatHistoryRepository {

    private final JdbcTemplate jdbc;
    private final ObjectMapper objectMapper;

    public PostgresChatHistoryRepository(JdbcTemplate jdbc, ObjectMapper objectMapper) {
        this.jdbc = jdbc;
        this.objectMapper = objectMapper;
    }

    @Override
    public ChatStore.ChatSession createSession() {
        var now = OffsetDateTime.now();
        String sessionId = UUID.randomUUID().toString();
        jdbc.update("INSERT INTO chat_sessions(session_id, title, created_at, updated_at) "
                        + "VALUES (?, ?, ?, ?)",
                sessionId, "新对话", Timestamp.from(now.toInstant()), Timestamp.from(now.toInstant()));
        return new ChatStore.ChatSession(sessionId, "新对话", now, now, new ArrayList<>());
    }

    @Override
    public Optional<ChatStore.ChatSession> findById(String sessionId) {
        var sessions = jdbc.query(
                "SELECT session_id, title, created_at, updated_at FROM chat_sessions WHERE session_id = ?",
                (rs, i) -> new Object[] {
                        rs.getString(1), rs.getString(2),
                        rs.getTimestamp(3).toInstant().atOffset(ZoneOffset.UTC),
                        rs.getTimestamp(4).toInstant().atOffset(ZoneOffset.UTC)
                },
                sessionId);
        if (sessions.isEmpty()) return Optional.empty();
        var sessRow = sessions.get(0);
        var messages = jdbc.query(
                "SELECT message_id, role, text, image_ids, selected_option_ids, agent_reply, created_at "
                + "FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC",
                (rs, i) -> {
                    var imageIds = decodeList(rs.getString(4));
                    var optionIds = decodeList(rs.getString(5));
                    var reply = decodeReply(rs.getString(6));
                    return new ChatStore.MessageRecord(
                            rs.getString(1), rs.getString(2), rs.getString(3),
                            imageIds, optionIds,
                            rs.getTimestamp(7).toInstant().atOffset(ZoneOffset.UTC),
                            reply);
                },
                sessionId);
        return Optional.of(new ChatStore.ChatSession(
                (String) sessRow[0], (String) sessRow[1],
                (OffsetDateTime) sessRow[2], (OffsetDateTime) sessRow[3],
                new ArrayList<>(messages)));
    }

    @Override
    public void addMessage(String sessionId, ChatStore.MessageRecord msg) {
        jdbc.update("INSERT INTO chat_messages(message_id, session_id, role, text, image_ids, "
                        + "selected_option_ids, agent_reply, created_at) "
                        + "VALUES (?, ?, ?, ?, to_jsonb(?::json), to_jsonb(?::json), to_jsonb(?::json), ?)",
                msg.messageId(), sessionId, msg.role(), msg.text(),
                encode(msg.imageIds()), encode(msg.selectedOptionIds()), encode(msg.agentReply()),
                Timestamp.from(msg.createdAt().toInstant()));
        var now = OffsetDateTime.now();
        jdbc.update("UPDATE chat_sessions SET updated_at = ? WHERE session_id = ?",
                Timestamp.from(now.toInstant()), sessionId);
        // Auto-title for first user text
        if ("user".equals(msg.role())) {
            Integer count = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM chat_messages WHERE session_id = ? AND role = 'user'",
                    Integer.class, sessionId);
            if (count != null && count == 1) {
                String title = autoTitle(msg);
                jdbc.update("UPDATE chat_sessions SET title = ? WHERE session_id = ? AND title = '新对话'",
                        title, sessionId);
            }
        }
    }

    @Override
    public List<ChatStore.SessionSummary> listSessions() {
        return jdbc.query(
                "SELECT s.session_id, s.title, s.created_at, s.updated_at, "
                + "  COALESCE((SELECT COUNT(*) FROM chat_messages m WHERE m.session_id = s.session_id), 0) "
                + "FROM chat_sessions s ORDER BY s.updated_at DESC",
                (rs, i) -> new ChatStore.SessionSummary(
                        rs.getString(1), rs.getString(2),
                        rs.getTimestamp(3).toInstant().atOffset(ZoneOffset.UTC),
                        rs.getTimestamp(4).toInstant().atOffset(ZoneOffset.UTC),
                        rs.getInt(5)));
    }

    @Override
    public Optional<ChatStore.SessionSummary> renameSession(String sessionId, String newTitle) {
        int rows = jdbc.update("UPDATE chat_sessions SET title = ?, updated_at = ? WHERE session_id = ?",
                newTitle, Timestamp.from(OffsetDateTime.now().toInstant()), sessionId);
        if (rows == 0) return Optional.empty();
        return findById(sessionId).map(ChatStore.SessionSummary::from);
    }

    @Override
    public boolean deleteSession(String sessionId) {
        return jdbc.update("DELETE FROM chat_sessions WHERE session_id = ?", sessionId) > 0;
    }

    private List<String> decodeList(String json) {
        if (json == null || json.isBlank()) return List.of();
        try {
            return objectMapper.readValue(json, new TypeReference<List<String>>() {});
        } catch (Exception e) {
            return List.of();
        }
    }

    private MockAgent.AgentReply decodeReply(String json) {
        if (json == null || json.isBlank() || "null".equals(json)) return null;
        try {
            return objectMapper.readValue(json, MockAgent.AgentReply.class);
        } catch (Exception e) {
            return null;
        }
    }

    private String encode(Object value) {
        if (value == null) return "null";
        try {
            return objectMapper.writeValueAsString(value);
        } catch (Exception e) {
            return "null";
        }
    }

    private String autoTitle(ChatStore.MessageRecord msg) {
        boolean hasText = msg.text() != null && !msg.text().isBlank();
        boolean hasImages = msg.imageIds() != null && !msg.imageIds().isEmpty();
        if (!hasText && hasImages) return "图片购物需求";
        if (hasText) {
            String cleaned = msg.text().replaceAll("\\s+", " ").trim();
            return cleaned.length() <= 18 ? cleaned : cleaned.substring(0, 18);
        }
        return "新对话";
    }
}
