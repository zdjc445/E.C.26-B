import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shopping_agent_app/features/chat/chat_api.dart';
import 'package:shopping_agent_app/features/chat/chat_controller.dart';
import 'package:shopping_agent_app/features/chat/chat_models.dart';
import 'package:shopping_agent_app/features/chat/chat_screen.dart';

/// Fake ChatApi with controllable Completer-based sendMessage for testing
/// loading states.
class FakeChatApi extends ChatApi {
  FakeChatApi() : super(baseUrl: 'http://test');

  Completer<AgentReply>? _sendMessageCompleter;

  /// Set a completer that the next sendMessage() call will wait on.
  /// The test completes it after asserting the loading state.
  void stubSendMessage(Completer<AgentReply> c) {
    _sendMessageCompleter = c;
  }

  @override
  Future<ImageUploadResult> uploadImage(File imageFile) async {
    return const ImageUploadResult(
      imageId: 'test-image-id',
      fileName: 'test.jpg',
      contentType: 'image/jpeg',
      size: 100,
    );
  }

  @override
  Future<SessionResult> createSession() async {
    return const SessionResult(
      sessionId: 'test-session-id',
      createdAt: '2026-06-06T10:00:00+08:00',
    );
  }

  @override
  Future<AgentReply> sendMessage({
    required String sessionId,
    String? text,
    List<String>? imageIds,
    List<String>? selectedOptionIds,
  }) async {
    if (_sendMessageCompleter != null) {
      final c = _sendMessageCompleter!;
      _sendMessageCompleter = null;
      return c.future;
    }
    // Fast path for tests that don't need loading assertions
    final hasOptions =
        selectedOptionIds != null && selectedOptionIds.isNotEmpty;
    return _buildReply(hasOptions);
  }

  AgentReply _buildReply(bool hasOptions) {
    if (hasOptions) {
      return const AgentReply(
        replyId: 'reply-002',
        replyType: 'recommendation',
        text: '根据你的偏好，我给出以下推荐。',
        cards: [
          ReplyCard(
            cardType: 'recommendation',
            title: '推荐购买',
            productName: 'Mock 商品',
            platform: 'Mock 平台-mock',
            price: 199.00,
            reason: '符合你选择的偏好，适合作为当前演示推荐。',
          ),
        ],
      );
    }

    return const AgentReply(
      replyId: 'reply-001',
      replyType: 'clarification',
      text: '我已经收到你的需求。你更看重哪一点？',
      cards: [
        ReplyCard(
          cardType: 'clarification',
          title: '你更看重哪一点？',
          options: [
            ClarificationOption(optionId: 'lowest_price', label: '价格最低'),
            ClarificationOption(optionId: 'official_store', label: '官方店铺'),
            ClarificationOption(optionId: 'fast_delivery', label: '配送更快'),
          ],
        ),
      ],
    );
  }
}

Widget _wrapWithProviders(Widget child, {FakeChatApi? fakeApi}) {
  return ProviderScope(
    overrides: [
      chatApiProvider.overrideWithValue(fakeApi ?? FakeChatApi()),
    ],
    child: MaterialApp(home: child),
  );
}

void main() {
  group('ChatScreen', () {
    testWidgets('renders chat screen with input bar', (tester) async {
      await tester.pumpWidget(_wrapWithProviders(const ChatScreen()));

      expect(find.text('购物助手'), findsOneWidget);
      expect(find.byIcon(Icons.image_outlined), findsOneWidget);
      expect(find.byIcon(Icons.mic_none), findsOneWidget);
      expect(find.byIcon(Icons.send), findsOneWidget);
      expect(find.byType(TextField), findsOneWidget);
    });

    testWidgets('send button does nothing when input is empty',
        (tester) async {
      await tester.pumpWidget(_wrapWithProviders(const ChatScreen()));

      await tester.tap(find.byIcon(Icons.send));
      await tester.pump();

      expect(find.text('正在思考…'), findsNothing);
    });

    testWidgets('sending text shows user message and loading then '
        'clarification card', (tester) async {
      final fakeApi = FakeChatApi();
      final completer = Completer<AgentReply>();
      fakeApi.stubSendMessage(completer);

      await tester.pumpWidget(_wrapWithProviders(const ChatScreen(),
          fakeApi: fakeApi));

      // Enter text and send
      await tester.enterText(
          find.byType(TextField), '我想买一双白色运动鞋');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.send));
      await tester.pump();

      // User message appears
      expect(find.text('我想买一双白色运动鞋'), findsOneWidget);
      // Loading shows (Completer hasn't resolved yet)
      expect(find.text('正在思考…'), findsOneWidget);

      // Complete the fake reply
      completer.complete(const AgentReply(
        replyId: 'reply-001',
        replyType: 'clarification',
        text: '我已经收到你的需求。你更看重哪一点？',
        cards: [
          ReplyCard(
            cardType: 'clarification',
            title: '你更看重哪一点？',
            options: [
              ClarificationOption(optionId: 'lowest_price', label: '价格最低'),
              ClarificationOption(optionId: 'official_store', label: '官方店铺'),
              ClarificationOption(optionId: 'fast_delivery', label: '配送更快'),
            ],
          ),
        ],
      ));
      await tester.pumpAndSettle();

      // Clarification card options appear
      expect(find.text('价格最低'), findsOneWidget);
      expect(find.text('官方店铺'), findsOneWidget);
      expect(find.text('配送更快'), findsOneWidget);
    });

    testWidgets('tapping clarification option shows loading then '
        'recommendation card', (tester) async {
      final fakeApi = FakeChatApi();

      // First: send opening message (use fast-path, no Completer needed)
      await tester.pumpWidget(_wrapWithProviders(const ChatScreen(),
          fakeApi: fakeApi));
      await tester.enterText(
          find.byType(TextField), '我想买一双白色运动鞋');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.send));
      await tester.pumpAndSettle();

      // Clarification options visible
      expect(find.text('价格最低'), findsOneWidget);

      // Set up controlled second reply
      final completer = Completer<AgentReply>();
      fakeApi.stubSendMessage(completer);

      // Tap the first option
      await tester.tap(find.text('价格最低'));
      await tester.pump();

      // Loading appears (Completer hasn't resolved)
      expect(find.text('正在思考…'), findsOneWidget);

      // Complete with recommendation
      completer.complete(const AgentReply(
        replyId: 'reply-002',
        replyType: 'recommendation',
        text: '根据你的偏好，我给出以下推荐。',
        cards: [
          ReplyCard(
            cardType: 'recommendation',
            title: '推荐购买',
            productName: 'Mock 商品',
            platform: 'Mock 平台-mock',
            price: 199.00,
            reason: '符合你选择的偏好，适合作为当前演示推荐。',
          ),
        ],
      ));
      await tester.pumpAndSettle();

      // Recommendation card appears
      expect(find.text('Mock 平台-mock'), findsOneWidget);
      expect(find.text('Mock 商品'), findsOneWidget);
      expect(find.textContaining('199.00'), findsOneWidget);
    });

    testWidgets('voice button shows placeholder snackbar', (tester) async {
      await tester.pumpWidget(_wrapWithProviders(const ChatScreen()));

      await tester.tap(find.byIcon(Icons.mic_none));
      await tester.pump();

      expect(find.text('语音输入功能即将上线'), findsOneWidget);
    });

    testWidgets('image button exists', (tester) async {
      await tester.pumpWidget(_wrapWithProviders(const ChatScreen()));

      expect(find.byIcon(Icons.image_outlined), findsOneWidget);
    });

    testWidgets('recommendation card platform has mock suffix',
        (tester) async {
      final fakeApi = FakeChatApi();

      await tester.pumpWidget(_wrapWithProviders(const ChatScreen(),
          fakeApi: fakeApi));

      await tester.enterText(find.byType(TextField), 'test');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.send));
      await tester.pumpAndSettle();
      await tester.tap(find.text('价格最低'));
      await tester.pumpAndSettle();

      expect(find.text('Mock 平台-mock'), findsOneWidget);
    });
  });
}
