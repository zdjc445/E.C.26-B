import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shopping_agent_app/features/chat/chat_api.dart';
import 'package:shopping_agent_app/features/chat/chat_controller.dart';
import 'package:shopping_agent_app/features/chat/chat_models.dart';
import 'package:shopping_agent_app/features/chat/chat_screen.dart';
import 'package:shopping_agent_app/features/chat/recognition_api.dart';
import 'package:shopping_agent_app/features/profile/profile_screen.dart';

/// Fake RecognitionApi for testing correction flow without real HTTP.
class FakeRecognitionApi extends RecognitionApi {
  FakeRecognitionApi() : super(baseUrl: 'http://test');

  Map<String, dynamic>? _nextUpdateResult;

  void stubUpdateAttributes(Map<String, dynamic> result) {
    _nextUpdateResult = result;
  }

  @override
  Future<Map<String, dynamic>> updateAttributes(
      String recognitionId, Map<String, dynamic> payload) async {
    if (_nextUpdateResult != null) {
      final r = _nextUpdateResult!;
      _nextUpdateResult = null;
      return r;
    }
    return payload;
  }

  @override
  Future<Map<String, dynamic>> recognizeImage(String imageId) async {
    return {
      'recognitionId': 'rec-test-001',
      'imageId': imageId,
      'category': '运动鞋',
      'brand': 'Mock 品牌',
      'model': 'Mock 型号',
      'keywords': ['运动鞋', '白色'],
      'attributes': {'color': '白色'},
      'confidence': 0.82,
      'aiProvider': 'mock',
      'fallbackUsed': false,
      'explanation': '演示识别结果。',
    };
  }
}

/// Fake ChatApi with controllable Completer and history stubs.
class FakeChatApi extends ChatApi {
  FakeChatApi() : super(baseUrl: 'http://test');

  Completer<AgentReply>? _sendMessageCompleter;
  final List<ChatSessionSummary> _sessions = [];
  final Map<String, List<Map<String, dynamic>>> _storedMessages = {};
  int _sessionCounter = 0;

  void stubSendMessage(Completer<AgentReply> c) {
    _sendMessageCompleter = c;
  }

  void addHistoryMessages(
      String sessionId, List<Map<String, dynamic>> msgs) {
    _storedMessages[sessionId] = msgs;
    _sessions.insert(
      0,
      ChatSessionSummary(
        sessionId: sessionId,
        title: '历史会话',
        createdAt: '2026-06-06T10:00:00+08:00',
        updatedAt: '2026-06-06T10:05:00+08:00',
        messageCount: msgs.length,
      ),
    );
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
    _sessionCounter++;
    _sessions.insert(
      0,
      ChatSessionSummary(
        sessionId: 'test-session-$_sessionCounter',
        title: '新对话',
        createdAt: '2026-06-06T10:00:00+08:00',
        updatedAt: '2026-06-06T10:00:00+08:00',
        messageCount: 0,
      ),
    );
    return SessionResult(
        sessionId: 'test-session-$_sessionCounter',
        createdAt: '2026-06-06T10:00:00+08:00');
  }

  @override
  Future<List<ChatSessionSummary>> listSessions() async =>
      List.from(_sessions);

  @override
  Future<SessionResult> renameSession(
      String sessionId, String newTitle) async {
    return SessionResult(
        sessionId: sessionId,
        createdAt: '2026-06-06T10:00:00+08:00');
  }

  @override
  Future<void> deleteSession(String sessionId) async {
    _sessions.removeWhere((s) => s.sessionId == sessionId);
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
    final hasOptions =
        selectedOptionIds != null && selectedOptionIds.isNotEmpty;
    final hasImages = imageIds != null && imageIds.isNotEmpty;
    return _buildReply(hasOptions: hasOptions, hasImages: hasImages);
  }

  @override
  Future<List<Map<String, dynamic>>> getMessages(
      String sessionId) async {
    return _storedMessages[sessionId] ?? [];
  }

  AgentReply _buildReply(
      {bool hasOptions = false, bool hasImages = false}) {
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
    if (hasImages) {
      return AgentReply(
        replyId: 'reply-rec',
        replyType: 'recognition',
        text: '我已经识别了你的商品图片。',
        cards: const [
          ReplyCard(
            cardType: 'recognition',
            title: '识别结果',
            imageId: 'test-image-id',
            category: '运动鞋',
            brand: 'Mock 品牌',
            model: 'Mock 型号',
            keywords: ['运动鞋', '白色'],
            attributes: {'color': '白色'},
            confidence: 0.82,
            aiProvider: 'mock',
            fallbackUsed: false,
            explanation: '演示识别结果。',
            recognitionId: 'rec-test-001',
          ),
          ReplyCard(
            cardType: 'clarification',
            title: '你更看重哪一点？',
            options: [
              ClarificationOption(
                  optionId: 'lowest_price', label: '价格最低'),
              ClarificationOption(
                  optionId: 'official_store', label: '官方店铺'),
              ClarificationOption(
                  optionId: 'fast_delivery', label: '配送更快'),
            ],
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
            ClarificationOption(
                optionId: 'lowest_price', label: '价格最低'),
            ClarificationOption(
                optionId: 'official_store', label: '官方店铺'),
            ClarificationOption(
                optionId: 'fast_delivery', label: '配送更快'),
          ],
        ),
      ],
    );
  }
}

class _TestOverrides {
  final FakeChatApi chatApi;
  final FakeRecognitionApi recApi;

  _TestOverrides()
      : chatApi = FakeChatApi(),
        recApi = FakeRecognitionApi();
}

Widget _wrapChat(Widget child, {_TestOverrides? overrides}) {
  final o = overrides ?? _TestOverrides();
  return ProviderScope(
    overrides: [
      chatApiProvider.overrideWithValue(o.chatApi),
      recognitionApiProvider.overrideWithValue(o.recApi),
    ],
    child: MaterialApp(home: child),
  );
}

Widget _wrapWithRouter({_TestOverrides? overrides}) {
  final o = overrides ?? _TestOverrides();
  final router = GoRouter(
    initialLocation: '/home',
    routes: [
      GoRoute(path: '/home', builder: (c, s) => const ChatScreen()),
      GoRoute(path: '/me', builder: (c, s) => const ProfileScreen()),
    ],
  );
  return ProviderScope(
    overrides: [
      chatApiProvider.overrideWithValue(o.chatApi),
      recognitionApiProvider.overrideWithValue(o.recApi),
    ],
    child: MaterialApp.router(routerConfig: router),
  );
}

void main() {
  group('ChatScreen AppBar', () {
    testWidgets('has history, profile, image, mic, send buttons',
        (tester) async {
      await tester.pumpWidget(_wrapChat(const ChatScreen()));

      expect(find.byIcon(Icons.history), findsOneWidget);
      expect(find.text('我的'), findsOneWidget);
      expect(find.byIcon(Icons.image_outlined), findsOneWidget);
      expect(find.byIcon(Icons.mic_none), findsOneWidget);
      expect(find.byIcon(Icons.send), findsOneWidget);
    });

    testWidgets('image button opens bottom sheet', (tester) async {
      await tester.pumpWidget(_wrapChat(const ChatScreen()));
      await tester.tap(find.byIcon(Icons.image_outlined));
      await tester.pumpAndSettle();
      expect(find.text('拍照'), findsOneWidget);
      expect(find.text('从相册选择'), findsOneWidget);
    });
  });

  group('ProfileScreen', () {
    testWidgets('displays top sections on entry', (tester) async {
      await tester.pumpWidget(_wrapWithRouter());
      await tester.tap(find.text('我的'));
      await tester.pumpAndSettle();

      // Top content visible without scrolling
      expect(find.text('演示用户'), findsOneWidget);
      expect(find.text('未接入真实登录'), findsOneWidget);
      expect(find.text('购物偏好'), findsOneWidget);
      expect(find.text('通知与价格提醒'), findsOneWidget);
    });

    testWidgets('displays lower sections after scrolling',
        (tester) async {
      await tester.pumpWidget(_wrapWithRouter());
      await tester.tap(find.text('我的'));
      await tester.pumpAndSettle();

      // Scroll down to reveal lower sections
      await tester.scrollUntilVisible(find.text('接口状态'), 100);
      await tester.pumpAndSettle();

      expect(find.text('隐私与数据'), findsOneWidget);
      expect(find.text('接口状态'), findsOneWidget);
      expect(find.text('聊天式 Mock Agent 闭环阶段'), findsOneWidget);
    });
  });

  group('Chat messaging', () {
    testWidgets('sends text and shows clarification card',
        (tester) async {
      final ov = _TestOverrides();
      final completer = Completer<AgentReply>();
      ov.chatApi.stubSendMessage(completer);

      await tester.pumpWidget(_wrapChat(const ChatScreen(), overrides: ov));
      await tester.enterText(find.byType(TextField), 'test');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.send));
      await tester.pump();

      expect(find.text('正在思考…'), findsOneWidget);

      completer.complete(const AgentReply(
        replyId: 'reply-001',
        replyType: 'clarification',
        text: '我已经收到你的需求。你更看重哪一点？',
        cards: [
          ReplyCard(
            cardType: 'clarification',
            title: '你更看重哪一点？',
            options: [
              ClarificationOption(
                  optionId: 'lowest_price', label: '价格最低'),
            ],
          ),
        ],
      ));
      await tester.pumpAndSettle();
      expect(find.text('价格最低'), findsOneWidget);
    });

    testWidgets(
        'tapping option shows recommendation with mock platform',
        (tester) async {
      final ov = _TestOverrides();
      await tester.pumpWidget(_wrapChat(const ChatScreen(), overrides: ov));
      await tester.enterText(find.byType(TextField), 'test');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.send));
      await tester.pumpAndSettle();
      await tester.tap(find.text('价格最低'));
      await tester.pumpAndSettle();
      expect(find.text('Mock 平台-mock'), findsOneWidget);
    });

    testWidgets('recognition card renders with correct fields',
        (tester) async {
      final ov = _TestOverrides();
      final completer = Completer<AgentReply>();
      ov.chatApi.stubSendMessage(completer);

      await tester.pumpWidget(_wrapChat(const ChatScreen(), overrides: ov));
      await tester.enterText(find.byType(TextField), 'test');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.send));
      await tester.pump();

      completer.complete(AgentReply(
        replyId: 'reply-rec',
        replyType: 'recognition',
        text: '识别结果',
        cards: const [
          ReplyCard(
            cardType: 'recognition',
            title: '识别结果',
            category: '运动鞋',
            brand: 'Mock 品牌',
            model: 'Mock 型号',
            keywords: ['运动鞋', '白色'],
            attributes: {'color': '白色'},
            confidence: 0.82,
            aiProvider: 'mock',
            fallbackUsed: false,
            explanation: '演示识别结果。',
            recognitionId: 'rec-test-001',
          ),
        ],
      ));
      await tester.pumpAndSettle();

      // Use findsWidgets for potentially duplicated text
      expect(find.text('Mock 品牌'), findsOneWidget);
      expect(find.text('Mock 型号'), findsOneWidget);
      expect(find.text('修正识别结果'), findsOneWidget);
    });

    testWidgets(
        'correction sheet opens, edits, saves, and updates card',
        (tester) async {
      final ov = _TestOverrides();
      final completer = Completer<AgentReply>();
      ov.chatApi.stubSendMessage(completer);

      await tester.pumpWidget(_wrapChat(const ChatScreen(), overrides: ov));
      await tester.enterText(find.byType(TextField), 'test');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.send));
      await tester.pump();

      completer.complete(AgentReply(
        replyId: 'reply-rec',
        replyType: 'recognition',
        text: '识别结果',
        cards: const [
          ReplyCard(
            cardType: 'recognition',
            title: '识别结果',
            category: '运动鞋',
            brand: 'Mock 品牌',
            model: 'Mock 型号',
            keywords: [],
            attributes: {'color': '白色'},
            confidence: 0.82,
            aiProvider: 'mock',
            fallbackUsed: false,
            explanation: '',
            recognitionId: 'rec-test-001',
          ),
        ],
      ));
      await tester.pumpAndSettle();

      // Tap correction button
      await tester.tap(find.text('修正识别结果'));
      await tester.pumpAndSettle();

      // Edit category
      final categoryField = find.widgetWithText(TextField, '商品类别');
      await tester.enterText(categoryField, '耳机');
      await tester.pump();

      // Stub the update response
      ov.recApi.stubUpdateAttributes({
        'recognitionId': 'rec-test-001',
        'category': '耳机',
        'brand': 'Mock 品牌',
        'model': 'Mock 型号',
        'keywords': [],
        'attributes': {'color': '白色'},
        'confidence': 0.82,
        'aiProvider': 'mock',
        'fallbackUsed': false,
        'explanation': '',
        'notices': ['用户已修正识别属性'],
      });

      // Tap save
      await tester.tap(find.text('保存'));
      await tester.pumpAndSettle();

      // Card should show updated category
      expect(find.text('耳机'), findsOneWidget);
    });

    testWidgets(
        'switch to history session restores clarification card',
        (tester) async {
      final ov = _TestOverrides();

      // Add history with agentReply in assistant message
      ov.chatApi.addHistoryMessages('hist-001', [
        {
          'messageId': 'msg-1',
          'role': 'user',
          'text': '我想买鞋',
          'imageIds': [],
          'selectedOptionIds': [],
          'createdAt': '2026-06-06T10:00:00+08:00',
        },
        {
          'messageId': 'msg-2',
          'role': 'assistant',
          'text': '我已经收到你的需求。你更看重哪一点？',
          'imageIds': [],
          'selectedOptionIds': [],
          'createdAt': '2026-06-06T10:00:01+08:00',
          'agentReply': {
            'replyId': 'reply-hist',
            'replyType': 'clarification',
            'text': '我已经收到你的需求。你更看重哪一点？',
            'cards': [
              {
                'cardType': 'clarification',
                'title': '你更看重哪一点？',
                'options': [
                  {'optionId': 'lowest_price', 'label': '价格最低'},
                ],
              },
            ],
          },
        },
      ]);

      await tester.pumpWidget(_wrapChat(const ChatScreen(), overrides: ov));

      // Open drawer and tap history session
      await tester.tap(find.byIcon(Icons.history));
      await tester.pumpAndSettle();
      await tester.tap(find.text('历史会话'));
      await tester.pumpAndSettle();

      // Clarification card should be restored
      expect(find.text('价格最低'), findsOneWidget);
    });

    testWidgets('voice button shows placeholder snackbar',
        (tester) async {
      await tester.pumpWidget(_wrapChat(const ChatScreen()));
      await tester.tap(find.byIcon(Icons.mic_none));
      await tester.pump();
      expect(find.text('语音输入功能即将上线'), findsOneWidget);
    });
  });
}
