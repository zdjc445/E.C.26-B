import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/network/api_client.dart';
import 'chat_api.dart';
import 'chat_models.dart';
import 'recognition_api.dart';

/// Provider for ChatApi.
final chatApiProvider = Provider<ChatApi>((ref) {
  final baseUrl = ref.watch(apiBaseUrlProvider);
  return ChatApi(baseUrl: baseUrl);
});

/// Provider for RecognitionApi so tests can override it.
final recognitionApiProvider = Provider<RecognitionApi>((ref) {
  final baseUrl = ref.watch(apiBaseUrlProvider);
  return RecognitionApi(baseUrl: baseUrl);
});

/// Provider for chat state notifier.
final chatControllerProvider =
    ChangeNotifierProvider<ChatController>((ref) {
  return ChatController(ref.watch(chatApiProvider));
});

/// Manages chat message list, session lifecycle, history, and API calls.
class ChatController extends ChangeNotifier {
  final ChatApi _api;

  ChatController(this._api);

  final List<ChatMessage> _messages = [];
  String? _currentSessionId;
  bool _sending = false;

  List<ChatSessionSummary> _sessions = [];
  bool _loadingSessions = false;

  List<ChatMessage> get messages => List.unmodifiable(_messages);
  String? get currentSessionId => _currentSessionId;
  bool get sending => _sending;
  List<ChatSessionSummary> get sessions => List.unmodifiable(_sessions);
  bool get loadingSessions => _loadingSessions;

  // ── Session list ──────────────────────────────────────────

  Future<void> loadSessions() async {
    _loadingSessions = true;
    notifyListeners();
    try {
      _sessions = await _api.listSessions();
    } catch (_) {
      // silently keep previous list
    } finally {
      _loadingSessions = false;
      notifyListeners();
    }
  }

  // ── New conversation ──────────────────────────────────────

  void newConversation() {
    _currentSessionId = null;
    _messages.clear();
    notifyListeners();
  }

  // ── Switch to existing session ────────────────────────────

  Future<void> switchToSession(String sessionId) async {
    _currentSessionId = sessionId;
    _messages.clear();
    notifyListeners();

    try {
      final rawMessages = await _api.getMessages(sessionId);
      _messages.addAll(rawMessages.map(_fromHistoryMessage));
    } catch (_) {
      // keep empty if load fails
    }
    notifyListeners();
  }

  // ── Delete session ────────────────────────────────────────

  Future<void> deleteSession(String sessionId) async {
    try {
      await _api.deleteSession(sessionId);
    } catch (_) {
      return;
    }
    if (_currentSessionId == sessionId) {
      newConversation();
    }
    await loadSessions();
  }

  // ── Rename session ────────────────────────────────────────

  Future<void> renameSession(String sessionId, String newTitle) async {
    try {
      await _api.renameSession(sessionId, newTitle);
    } catch (_) {
      return;
    }
    await loadSessions();
  }

  // ── Send text message ─────────────────────────────────────

  Future<void> sendTextMessage(String text,
      {List<String>? imageIds, List<String>? imagePaths}) async {
    if (text.trim().isEmpty && (imageIds == null || imageIds.isEmpty)) {
      return;
    }
    if (_sending) return;

    final userMsg = ChatMessage(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      role: ChatRole.user,
      text: text.trim().isEmpty ? null : text.trim(),
      imageIds: imageIds ?? [],
      imagePaths: imagePaths ?? [],
    );
    _messages.add(userMsg);

    final loadingMsg = ChatMessage(
      id: 'loading_${userMsg.id}',
      role: ChatRole.assistant,
      isLoading: true,
    );
    _messages.add(loadingMsg);
    _sending = true;
    notifyListeners();

    try {
      await _ensureSession();
      final reply = await _api.sendMessage(
        sessionId: _currentSessionId!,
        text: text.trim().isEmpty ? null : text.trim(),
        imageIds: imageIds,
      );

      _messages.removeWhere((m) => m.id == loadingMsg.id);
      _messages.add(ChatMessage(
        id: reply.replyId,
        role: ChatRole.assistant,
        text: reply.text,
        agentReply: reply,
      ));
    } catch (_) {
      _messages.removeWhere((m) => m.id == loadingMsg.id);
      _messages.add(ChatMessage(
        id: 'error_${userMsg.id}',
        role: ChatRole.assistant,
        text: '抱歉，暂时无法处理你的请求，请稍后重试。',
      ));
    } finally {
      _sending = false;
      notifyListeners();
      // refresh session list for updated title/count
      await loadSessions();
    }
  }

  // ── Select option ─────────────────────────────────────────

  Future<void> selectOption(String optionId) async {
    if (_sending || _currentSessionId == null) return;

    final optionLabel = _optionLabel(optionId);
    final userMsg = ChatMessage(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      role: ChatRole.user,
      text: optionLabel,
    );
    _messages.add(userMsg);

    final loadingMsg = ChatMessage(
      id: 'loading_${userMsg.id}',
      role: ChatRole.assistant,
      isLoading: true,
    );
    _messages.add(loadingMsg);
    _sending = true;
    notifyListeners();

    try {
      final reply = await _api.sendMessage(
        sessionId: _currentSessionId!,
        selectedOptionIds: [optionId],
      );

      _messages.removeWhere((m) => m.id == loadingMsg.id);
      _messages.add(ChatMessage(
        id: reply.replyId,
        role: ChatRole.assistant,
        text: reply.text,
        agentReply: reply,
      ));
    } catch (_) {
      _messages.removeWhere((m) => m.id == loadingMsg.id);
      _messages.add(ChatMessage(
        id: 'error_${userMsg.id}',
        role: ChatRole.assistant,
        text: '抱歉，暂时无法处理你的请求，请稍后重试。',
      ));
    } finally {
      _sending = false;
      notifyListeners();
      await loadSessions();
    }
  }

  // ── Upload image ──────────────────────────────────────────

  Future<String?> uploadImage(File imageFile) async {
    try {
      final result = await _api.uploadImage(imageFile);
      return result.imageId;
    } catch (_) {
      return null;
    }
  }

  // ── Internals ─────────────────────────────────────────────

  Future<void> _ensureSession() async {
    if (_currentSessionId != null) return;
    final result = await _api.createSession();
    _currentSessionId = result.sessionId;
  }

  String _optionLabel(String optionId) {
    return switch (optionId) {
      'lowest_price' => '价格最低',
      'official_store' => '官方店铺',
      'fast_delivery' => '配送更快',
      _ => optionId,
    };
  }

  /// Update a recognition card in-place after user correction.
  void updateRecognitionCard(
      String recognitionId, Map<String, dynamic> updated) {
    for (var i = 0; i < _messages.length; i++) {
      final msg = _messages[i];
      if (msg.agentReply == null) continue;
      for (var j = 0; j < msg.agentReply!.cards.length; j++) {
        final card = msg.agentReply!.cards[j];
        if (card.recognitionId == recognitionId) {
          final newCards = List<ReplyCard>.from(msg.agentReply!.cards);
          newCards[j] = ReplyCard(
            cardType: card.cardType,
            title: card.title,
            imageId: card.imageId,
            category: updated['category'] as String? ?? card.category,
            brand: updated['brand'] as String? ?? card.brand,
            model: updated['model'] as String? ?? card.model,
            keywords: card.keywords,
            attributes: updated['attributes'] as Map<String, dynamic>? ??
                card.attributes,
            confidence: card.confidence,
            aiProvider: card.aiProvider,
            fallbackUsed: card.fallbackUsed,
            explanation: updated['explanation'] as String? ??
                card.explanation,
            recognitionId: card.recognitionId,
          );
          final newReply = AgentReply(
            replyId: msg.agentReply!.replyId,
            replyType: msg.agentReply!.replyType,
            text: msg.agentReply!.text,
            cards: newCards,
          );
          _messages[i] = msg.copyWith(agentReply: newReply);
          notifyListeners();
          return;
        }
      }
    }
  }

  /// Restore a UI ChatMessage from backend history message map.
  ChatMessage _fromHistoryMessage(Map<String, dynamic> m) {
    final role = m['role'] == 'assistant' ? ChatRole.assistant : ChatRole.user;
    final text = m['text'] as String?;
    final imageIds =
        (m['imageIds'] as List?)?.map((e) => e.toString()).toList() ?? [];
    // Restore agentReply if present (for assistant messages)
    AgentReply? agentReply;
    if (m['agentReply'] != null) {
      agentReply = AgentReply.fromJson(m['agentReply'] as Map<String, dynamic>);
    }
    return ChatMessage(
      id: m['messageId'] as String,
      role: role,
      text: text,
      imageIds: imageIds,
      agentReply: agentReply,
    );
  }
}
