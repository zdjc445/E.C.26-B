import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/network/api_client.dart';
import 'chat_api.dart';
import 'chat_models.dart';

/// Provider for ChatApi, resolves base URL from apiBaseUrlProvider.
final chatApiProvider = Provider<ChatApi>((ref) {
  final baseUrl = ref.watch(apiBaseUrlProvider);
  return ChatApi(baseUrl: baseUrl);
});

/// Provider for chat state notifier.
final chatControllerProvider =
    ChangeNotifierProvider<ChatController>((ref) {
  return ChatController(ref.watch(chatApiProvider));
});

/// Manages chat message list, session lifecycle, and API calls.
class ChatController extends ChangeNotifier {
  final ChatApi _api;

  ChatController(this._api);

  final List<ChatMessage> _messages = [];
  String? _sessionId;
  bool _sending = false;

  List<ChatMessage> get messages => List.unmodifiable(_messages);
  bool get sending => _sending;

  /// Send a text message with optional image IDs and local image paths.
  Future<void> sendTextMessage(String text,
      {List<String>? imageIds, List<String>? imagePaths}) async {
    if (text.trim().isEmpty &&
        (imageIds == null || imageIds.isEmpty)) {
      return;
    }
    if (_sending) {
      return;
    }

    // Add user message
    final userMsg = ChatMessage(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      role: ChatRole.user,
      text: text.trim().isEmpty ? null : text.trim(),
      imageIds: imageIds ?? [],
      imagePaths: imagePaths ?? [],
    );
    _messages.add(userMsg);

    // Add loading placeholder
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
        sessionId: _sessionId!,
        text: text.trim().isEmpty ? null : text.trim(),
        imageIds: imageIds,
      );

      // Remove loading, add real reply
      _messages.removeWhere((m) => m.id == loadingMsg.id);
      final assistantMsg = ChatMessage(
        id: reply.replyId,
        role: ChatRole.assistant,
        text: reply.text,
        agentReply: reply,
      );
      _messages.add(assistantMsg);
    } catch (e) {
      _messages.removeWhere((m) => m.id == loadingMsg.id);
      final errorMsg = ChatMessage(
        id: 'error_${userMsg.id}',
        role: ChatRole.assistant,
        text: '抱歉，暂时无法处理你的请求，请稍后重试。',
      );
      _messages.add(errorMsg);
    } finally {
      _sending = false;
      notifyListeners();
    }
  }

  /// Send a clarification option selection.
  Future<void> selectOption(String optionId) async {
    if (_sending || _sessionId == null) {
      return;
    }

    // Add user message showing selection
    final optionLabel = _optionLabel(optionId);
    final userMsg = ChatMessage(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      role: ChatRole.user,
      text: optionLabel,
    );
    _messages.add(userMsg);

    // Add loading placeholder
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
        sessionId: _sessionId!,
        selectedOptionIds: [optionId],
      );

      _messages.removeWhere((m) => m.id == loadingMsg.id);
      final assistantMsg = ChatMessage(
        id: reply.replyId,
        role: ChatRole.assistant,
        text: reply.text,
        agentReply: reply,
      );
      _messages.add(assistantMsg);
    } catch (e) {
      _messages.removeWhere((m) => m.id == loadingMsg.id);
      final errorMsg = ChatMessage(
        id: 'error_${userMsg.id}',
        role: ChatRole.assistant,
        text: '抱歉，暂时无法处理你的请求，请稍后重试。',
      );
      _messages.add(errorMsg);
    } finally {
      _sending = false;
      notifyListeners();
    }
  }

  /// Upload a local image file and return its imageId.
  Future<String?> uploadImage(File imageFile) async {
    try {
      final result = await _api.uploadImage(imageFile);
      return result.imageId;
    } catch (e) {
      return null;
    }
  }

  Future<void> _ensureSession() async {
    if (_sessionId != null) {
      return;
    }
    final result = await _api.createSession();
    _sessionId = result.sessionId;
  }

  String _optionLabel(String optionId) {
    return switch (optionId) {
      'lowest_price' => '价格最低',
      'official_store' => '官方店铺',
      'fast_delivery' => '配送更快',
      _ => optionId,
    };
  }
}
