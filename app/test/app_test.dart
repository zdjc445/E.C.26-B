import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shopping_agent_app/features/chat/chat_api.dart';
import 'package:shopping_agent_app/features/chat/chat_controller.dart';
import 'package:shopping_agent_app/features/chat/chat_models.dart';
import 'package:shopping_agent_app/features/alerts/price_alert_api.dart';
import 'package:shopping_agent_app/features/alerts/price_alert_models.dart';
import 'package:shopping_agent_app/features/chat/chat_screen.dart';
import 'package:shopping_agent_app/features/chat/chat_providers.dart';
import 'package:shopping_agent_app/features/chat/product_group_detail_screen.dart';
import 'package:shopping_agent_app/features/chat/recognition_api.dart';
import 'package:shopping_agent_app/features/favorites/favorite_api.dart';
import 'package:shopping_agent_app/features/favorites/favorite_models.dart';
import 'package:shopping_agent_app/features/profile/health_api.dart';
import 'package:shopping_agent_app/features/profile/profile_screen.dart';
import 'package:shopping_agent_app/features/voice/voice_api.dart';

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

/// Fake HealthApi returning configurable status.
class FakeHealthApi extends HealthApi {
  FakeHealthApi() : super(baseUrl: 'http://test');
  @override
  Future<HealthStatus> fetch() async {
    return const HealthStatus(
      status: 'ok',
      app: 'shopping-agent',
      stage:
          '聊天式 AI 识别 + 公开样例数据多平台比价 + 7 维度自然语言筛选 + 动态建议卡 + 持久化 + 认证 + 收藏 + 价格提醒 + 语音转写阶段',
      aiProvider: 'ark',
      chatHistoryStore: 'memory',
      authEnabled: false,
      ecommerceProvider: 'mock',
      voiceProvider: 'mock',
      timestamp: '2026-06-06T10:00:00+08:00',
    );
  }
}

class FakeVoiceApi extends VoiceApi {
  const FakeVoiceApi() : super(baseUrl: 'http://test');

  @override
  Future<VoiceTranscription> transcribeBytes(
    List<int> bytes, {
    String filename = 'voice.m4a',
    String contentType = 'audio/m4a',
  }) async {
    return const VoiceTranscription(
      text: '推荐耳机',
      provider: 'mock',
      fallbackUsed: false,
    );
  }
}

class FakeFavoriteApi extends FavoriteApi {
  FakeFavoriteApi() : super(baseUrl: 'http://test');

  final List<Map<String, dynamic>> addedPayloads = [];
  bool failAdd = false;

  @override
  Future<FavoriteItem> add(Map<String, dynamic> payload,
      {String? token}) async {
    if (failAdd) {
      throw Exception('收藏接口失败');
    }
    final saved = Map<String, dynamic>.from(payload);
    addedPayloads.add(saved);
    return FavoriteItem(
      id: addedPayloads.length,
      productId: saved['productId'] as String,
      title: saved['title'] as String,
      platform: saved['platform'] as String? ?? '',
      price: (saved['price'] as num?)?.toDouble() ?? 0,
      shopName: saved['shopName'] as String?,
      brand: saved['brand'] as String?,
      imageUrl: saved['imageUrl'] as String?,
      productUrl: saved['productUrl'] as String?,
      createdAt: '2026-06-07T10:00:00+08:00',
    );
  }
}

class FakePriceAlertApi extends PriceAlertApi {
  FakePriceAlertApi() : super(baseUrl: 'http://test');

  final List<Map<String, dynamic>> createdPayloads = [];
  bool failCreate = false;

  @override
  Future<PriceAlertItem> create(Map<String, dynamic> payload,
      {String? token}) async {
    if (failCreate) {
      throw Exception('创建提醒失败');
    }
    createdPayloads.add(Map<String, dynamic>.from(payload));
    return PriceAlertItem(
      id: createdPayloads.length,
      productId: payload['productId'] as String,
      title: payload['title'] as String,
      platform: payload['platform'] as String? ?? '',
      targetPrice: (payload['targetPrice'] as num).toDouble(),
      triggered: false,
      note: payload['note'] as String?,
      createdAt: '2026-06-07T10:00:00+08:00',
    );
  }
}

/// Fake ChatApi with controllable Completer and history stubs.
class FakeChatApi extends ChatApi {
  FakeChatApi() : super(baseUrl: 'http://test');

  Completer<AgentReply>? _sendMessageCompleter;
  final List<Map<String, dynamic>> sendRequests = [];
  final List<ChatSessionSummary> _sessions = [];
  final Map<String, List<Map<String, dynamic>>> _storedMessages = {};
  int _sessionCounter = 0;

  void stubSendMessage(Completer<AgentReply> c) {
    _sendMessageCompleter = c;
  }

  void addHistoryMessages(String sessionId, List<Map<String, dynamic>> msgs) {
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
  Future<List<ChatSessionSummary>> listSessions() async => List.from(_sessions);

  @override
  Future<SessionResult> renameSession(String sessionId, String newTitle) async {
    return SessionResult(
        sessionId: sessionId, createdAt: '2026-06-06T10:00:00+08:00');
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
    Map<String, dynamic>? profile,
  }) async {
    sendRequests.add({
      'sessionId': sessionId,
      'text': text,
      'imageIds': imageIds ?? [],
      'selectedOptionIds': selectedOptionIds ?? [],
      if (profile != null) 'profile': profile,
    });
    if (_sendMessageCompleter != null) {
      final c = _sendMessageCompleter!;
      _sendMessageCompleter = null;
      return c.future;
    }
    final hasOptions =
        selectedOptionIds != null && selectedOptionIds.isNotEmpty;
    final hasImages = imageIds != null && imageIds.isNotEmpty;
    final hasShoppingText = _isShoppingText(text);
    return _buildReply(
      hasProductRecommendation: hasOptions || hasShoppingText,
      hasImages: hasImages,
    );
  }

  @override
  Future<List<Map<String, dynamic>>> getMessages(String sessionId) async {
    return _storedMessages[sessionId] ?? [];
  }

  bool _isShoppingText(String? text) {
    if (text == null || text.trim().isEmpty) {
      return false;
    }
    return RegExp(
      '买|想买|想要|推荐|帮我找|找.*商品|多少钱|价格|便宜|优惠|性价比|官方|自营|旗舰|配送|物流|评价|评分|销量|预算|以内|不超过|以下',
    ).hasMatch(text);
  }

  AgentReply _buildReply({
    bool hasProductRecommendation = false,
    bool hasImages = false,
  }) {
    if (hasProductRecommendation) {
      return AgentReply(
        replyId: 'reply-002',
        replyType: 'product_recommendation',
        text: '找到 5 组商品',
        cards: [
          const ReplyCard(
            cardType: 'product_group_list',
            title: '商品结果',
            filterSummary: ['品类：运动鞋', '全部平台'],
            groups: [
              ProductGroup(
                groupId: 'jd-001',
                sameItemKey: null,
                displayTitle: '耐克品牌运动鞋 轻便透气',
                category: '运动鞋',
                brand: '耐克',
                thumbnailUrl: '',
                bestPrice: 199.00,
                originalPrice: 399.00,
                priceRange: PriceRange(min: 199.00, max: 299.00),
                platformCount: 2,
                platforms: [
                  PlatformOfferSummary(
                    productId: 'jd-001',
                    platform: '京东-mock',
                    price: 299.00,
                    originalPrice: 399.00,
                    shopName: '耐克京东自营',
                    productUrl: '',
                    rating: 4.8,
                    sales: 12000,
                    tags: ['自营', '透气'],
                    reasons: ['价格优惠'],
                  ),
                  PlatformOfferSummary(
                    productId: 'pdd-001',
                    platform: '拼多多-mock',
                    price: 199.00,
                    originalPrice: 299.00,
                    shopName: '品牌专营店',
                    productUrl: '',
                    rating: 4.5,
                    sales: 58000,
                    tags: ['爆款', '透气'],
                    reasons: ['高销量'],
                  ),
                ],
                highlights: ['最低 ¥199', '2 个平台有售', '高销量'],
                matchLevel: 'strict',
              ),
              ProductGroup(
                groupId: 'jd-002',
                sameItemKey: null,
                displayTitle: '阿迪达斯官方旗舰减震训练运动鞋',
                category: '运动鞋',
                brand: '阿迪达斯',
                thumbnailUrl: '',
                bestPrice: 329.00,
                originalPrice: 499.00,
                priceRange: PriceRange(min: 329.00, max: 389.00),
                platformCount: 2,
                platforms: [
                  PlatformOfferSummary(
                    productId: 'jd-002',
                    platform: '京东-mock',
                    price: 389.00,
                    originalPrice: 499.00,
                    shopName: '阿迪达斯官方旗舰店',
                    productUrl: '',
                    rating: 4.9,
                    sales: 8500,
                    tags: ['官方', '减震'],
                    reasons: ['高评分'],
                  ),
                  PlatformOfferSummary(
                    productId: 'tb-003',
                    platform: '淘宝-mock',
                    price: 329.00,
                    originalPrice: 429.00,
                    shopName: '阿迪达斯品牌官方店',
                    productUrl: '',
                    rating: 4.8,
                    sales: 22000,
                    tags: ['官方', '减震'],
                    reasons: ['性价比'],
                  ),
                ],
                highlights: ['最低 ¥329', '2 个平台有售', '高评分'],
                matchLevel: 'strict',
              ),
              ProductGroup(
                groupId: 'lining-running-shoe',
                sameItemKey: 'lining-running-shoe',
                displayTitle: '李宁透气网面跑步运动鞋',
                category: '运动鞋',
                brand: '李宁',
                thumbnailUrl: '',
                bestPrice: 169.00,
                originalPrice: 299.00,
                priceRange: PriceRange(min: 169.00, max: 219.00),
                platformCount: 2,
                platforms: [
                  PlatformOfferSummary(
                    productId: 'jd-004',
                    platform: '京东-mock',
                    price: 219.00,
                    originalPrice: 299.00,
                    shopName: '李宁品牌专营店',
                    productUrl: '',
                    rating: 4.4,
                    sales: 18000,
                    tags: ['透气', '跑步'],
                    reasons: [],
                  ),
                  PlatformOfferSummary(
                    productId: 'pdd-003',
                    platform: '拼多多-mock',
                    price: 169.00,
                    originalPrice: 249.00,
                    shopName: '李宁品牌折扣店',
                    productUrl: '',
                    rating: 4.2,
                    sales: 78000,
                    tags: ['性价比', '跑步', '透气'],
                    reasons: ['高销量'],
                  ),
                ],
                highlights: ['最低 ¥169', '2 个平台有售', '有优惠'],
                matchLevel: 'strict',
              ),
            ],
          ),
          const ReplyCard(
            cardType: 'clarification',
            title: '你更想看哪类「运动鞋」推荐？',
            options: [
              ClarificationOption(optionId: 'lowest_price', label: '查看同款低价'),
              ClarificationOption(optionId: 'official_store', label: '只看官方旗舰店'),
              ClarificationOption(optionId: 'fast_delivery', label: '配送更快'),
              ClarificationOption(optionId: 'style_similar', label: '相似风格推荐'),
              ClarificationOption(optionId: 'price_history', label: '查看历史价格走势'),
            ],
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
            cardType: 'product_group_list',
            title: '商品结果',
            filterSummary: ['品类：运动鞋'],
            groups: [
              ProductGroup(
                groupId: 'jd-001',
                displayTitle: '耐克品牌运动鞋 轻便透气',
                category: '运动鞋',
                brand: '耐克',
                thumbnailUrl: '',
                bestPrice: 199.00,
                originalPrice: 399.00,
                priceRange: PriceRange(min: 199.00, max: 299.00),
                platformCount: 2,
                platforms: [
                  PlatformOfferSummary(
                    productId: 'jd-001',
                    platform: '京东-mock',
                    price: 299.00,
                    originalPrice: 399.00,
                    shopName: '耐克京东自营',
                    productUrl: '',
                    rating: 4.8,
                    sales: 12000,
                    tags: ['自营'],
                    reasons: [],
                  ),
                  PlatformOfferSummary(
                    productId: 'pdd-001',
                    platform: '拼多多-mock',
                    price: 199.00,
                    originalPrice: 299.00,
                    shopName: '品牌专营店',
                    productUrl: '',
                    rating: 4.5,
                    sales: 58000,
                    tags: ['爆款'],
                    reasons: [],
                  ),
                ],
                highlights: ['最低 ¥199', '2 个平台有售'],
                matchLevel: 'strict',
              ),
            ],
          ),
          ReplyCard(
            cardType: 'clarification',
            title: '继续筛选',
            options: [
              ClarificationOption(optionId: 'lowest_price', label: '价格最低'),
              ClarificationOption(optionId: 'official_store', label: '官方店铺'),
              ClarificationOption(optionId: 'fast_delivery', label: '配送更快'),
            ],
          ),
        ],
      );
    }
    return const AgentReply(
      replyId: 'reply-001',
      replyType: 'clarification',
      text: '找到 0 组商品',
      cards: [
        ReplyCard(
          cardType: 'product_group_list',
          title: '商品结果',
          filterSummary: ['品类：运动鞋'],
          groups: [],
          emptyReason: '请输入你想要的商品关键词以开始搜索。',
        ),
        ReplyCard(
          cardType: 'clarification',
          title: '继续筛选',
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

class _TestOverrides {
  final FakeChatApi chatApi;
  final FakeRecognitionApi recApi;
  final FakeFavoriteApi favoriteApi;
  final FakePriceAlertApi priceAlertApi;

  _TestOverrides()
      : chatApi = FakeChatApi(),
        recApi = FakeRecognitionApi(),
        favoriteApi = FakeFavoriteApi(),
        priceAlertApi = FakePriceAlertApi();
}

Widget _wrapChat(Widget child, {_TestOverrides? overrides}) {
  final o = overrides ?? _TestOverrides();
  return ProviderScope(
    overrides: [
      chatApiProvider.overrideWithValue(o.chatApi),
      recognitionApiProvider.overrideWithValue(o.recApi),
      favoriteApiInChatProvider.overrideWithValue(o.favoriteApi),
      priceAlertApiInChatProvider.overrideWithValue(o.priceAlertApi),
      voiceApiProvider.overrideWithValue(const FakeVoiceApi()),
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
      favoriteApiInChatProvider.overrideWithValue(o.favoriteApi),
      priceAlertApiInChatProvider.overrideWithValue(o.priceAlertApi),
      healthApiProvider.overrideWithValue(FakeHealthApi()),
      voiceApiProvider.overrideWithValue(const FakeVoiceApi()),
    ],
    child: MaterialApp.router(routerConfig: router),
  );
}

Future<void> _dragUntilFinderVisible(WidgetTester tester, Finder finder) async {
  final scrollable = find.byType(Scrollable).first;
  for (var i = 0; i < 8; i++) {
    final center = _finderCenter(tester, finder);
    final screenSize = tester.view.physicalSize / tester.view.devicePixelRatio;
    if (center != null &&
        center.dx >= 0 &&
        center.dy >= 48 &&
        center.dx <= screenSize.width &&
        center.dy <= screenSize.height - 24) {
      return;
    }
    final dy = center != null && center.dy < 48 ? 180.0 : -320.0;
    await tester.drag(scrollable, Offset(0, dy));
    await tester.pumpAndSettle();
  }
}

Offset? _finderCenter(WidgetTester tester, Finder finder) {
  if (finder.evaluate().isEmpty) {
    return null;
  }
  try {
    return tester.getCenter(finder.first);
  } catch (_) {
    return null;
  }
}

void main() {
  group('ChatScreen AppBar', () {
    testWidgets('has history, profile, image, mic, send buttons',
        (tester) async {
      await tester.pumpWidget(_wrapChat(const ChatScreen()));

      expect(find.byIcon(Icons.history), findsOneWidget);
      expect(find.byIcon(Icons.person_outline), findsOneWidget);
      expect(find.byIcon(Icons.image_outlined), findsOneWidget);
      expect(find.byIcon(Icons.mic_none), findsOneWidget);
      expect(find.byIcon(Icons.arrow_upward), findsOneWidget);
    });

    testWidgets('send button is enabled only after input has content',
        (tester) async {
      await tester.pumpWidget(_wrapChat(const ChatScreen()));

      IconButton sendButton() => tester.widget<IconButton>(
            find.byKey(const Key('chat_send_button')),
          );

      expect(sendButton().onPressed, isNull);

      await tester.enterText(find.byKey(const Key('chat_input_field')), '耳机');
      await tester.pump();
      expect(sendButton().onPressed, isNotNull);

      await tester.enterText(find.byKey(const Key('chat_input_field')), '');
      await tester.pump();
      expect(sendButton().onPressed, isNull);
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
      await tester.tap(find.byIcon(Icons.person_outline));
      await tester.pumpAndSettle();

      // Top content visible without scrolling
      expect(find.text('演示用户'), findsOneWidget);
      expect(find.text('后端认证未启用 · 使用演示用户'), findsOneWidget);
      expect(find.text('我的收藏'), findsOneWidget);
      expect(find.text('价格提醒'), findsOneWidget);
      expect(find.text('购物偏好'), findsOneWidget);
    });

    testWidgets('displays lower sections after scrolling', (tester) async {
      await tester.pumpWidget(_wrapWithRouter());
      await tester.tap(find.byIcon(Icons.person_outline));
      await tester.pumpAndSettle();

      // Verify lower sections visible without scrolling
      expect(find.text('演示用户'), findsOneWidget);
      expect(find.text('购物偏好'), findsOneWidget);
      expect(find.text('关于购物助手'), findsOneWidget);
      expect(find.text('E.C.26-B'), findsOneWidget);
    });

    testWidgets('displays live health status in debug screen via long-press',
        (tester) async {
      await tester.pumpWidget(_wrapWithRouter());
      await tester.tap(find.byIcon(Icons.person_outline));
      await tester.pumpAndSettle();

      // Long-press "关于购物助手" to reveal debug screen
      await tester.longPress(find.text('E.C.26-B'));
      await tester.pumpAndSettle();

      // Debug screen shows backend provider status
      expect(find.text('开发者调试'), findsOneWidget);
      expect(find.text('AI Provider'), findsOneWidget);
      expect(find.text('ark'), findsOneWidget);
    });
  });

  group('Chat messaging', () {
    testWidgets('sends text and shows clarification card', (tester) async {
      final ov = _TestOverrides();
      final completer = Completer<AgentReply>();
      ov.chatApi.stubSendMessage(completer);

      await tester.pumpWidget(_wrapChat(const ChatScreen(), overrides: ov));
      await tester.enterText(find.byType(TextField), 'test');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.arrow_upward));
      await tester.pump();

      expect(find.text('AI 正在为你查找…'), findsOneWidget);

      completer.complete(const AgentReply(
        replyId: 'reply-001',
        replyType: 'clarification',
        text: '请选择筛选条件',
        cards: [
          ReplyCard(
            cardType: 'clarification',
            title: '继续筛选',
            options: [
              ClarificationOption(optionId: 'lowest_price', label: '价格最低'),
            ],
          ),
        ],
      ));
      await tester.pumpAndSettle();
      expect(find.text('价格最低'), findsOneWidget);
    });

    testWidgets('tapping option shows product_recommendation cards',
        (tester) async {
      final ov = _TestOverrides();
      await tester.pumpWidget(_wrapChat(const ChatScreen(), overrides: ov));
      await tester.enterText(find.byType(TextField), 'test');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.arrow_upward));
      await tester.pumpAndSettle();
      await tester.tap(find.text('价格最低'));
      await tester.pumpAndSettle();

      // Should show product group list
      expect(find.textContaining('找到 '), findsWidgets);
      expect(find.textContaining('组商品'), findsOneWidget);
      // Group cards show: title, price, rating, chevron
      expect(find.textContaining('运动鞋'), findsWidgets);
      expect(find.textContaining('¥'), findsWidgets);
      expect(find.textContaining('起'), findsWidgets);
      expect(find.byIcon(Icons.chevron_right), findsWidgets);
      // Should NOT show brand labels, highlights, relaxed match tags in group row
      expect(find.text('耐克'), findsNothing);
      expect(find.text('放宽匹配'), findsNothing);
      // Should show clarification card
      expect(find.text('查看同款低价'), findsAtLeastNWidgets(1));
    });

    testWidgets('recognition card renders with correct fields', (tester) async {
      final ov = _TestOverrides();
      final completer = Completer<AgentReply>();
      ov.chatApi.stubSendMessage(completer);

      await tester.pumpWidget(_wrapChat(const ChatScreen(), overrides: ov));
      await tester.enterText(find.byType(TextField), 'test');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.arrow_upward));
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

      expect(find.text('识别到：运动鞋'), findsOneWidget);
      expect(find.text('置信度 82%'), findsOneWidget);
      expect(find.text('来源：mock'), findsOneWidget);
      expect(find.text('可修正字段'), findsOneWidget);
      expect(find.text('品牌：Mock 品牌'), findsOneWidget);
      expect(find.text('型号：Mock 型号'), findsOneWidget);
      expect(find.text('修正'), findsOneWidget);
    });

    testWidgets('correction sheet opens, edits, saves, and updates card',
        (tester) async {
      final ov = _TestOverrides();
      final completer = Completer<AgentReply>();
      ov.chatApi.stubSendMessage(completer);

      await tester.pumpWidget(_wrapChat(const ChatScreen(), overrides: ov));
      await tester.enterText(find.byType(TextField), 'test');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.arrow_upward));
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
      await tester.tap(find.text('修正'));
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

      // Card should show updated category in the redesigned recognition card.
      expect(find.text('识别到：耳机'), findsOneWidget);
      expect(find.text('类别：耳机'), findsOneWidget);
    });

    testWidgets('recognition card shows uploaded image thumbnail',
        (tester) async {
      final ov = _TestOverrides();
      final imageFile =
          File('android/app/src/main/res/mipmap-mdpi/ic_launcher.png');
      expect(imageFile.existsSync(), isTrue);
      ov.chatApi.addHistoryMessages('hist-image', [
        {
          'messageId': 'msg-img-user',
          'role': 'user',
          'text': null,
          'imageIds': ['test-image-id'],
          'imagePaths': [imageFile.path],
          'selectedOptionIds': [],
          'createdAt': '2026-06-06T10:00:00+08:00',
        },
        {
          'messageId': 'msg-img-assistant',
          'role': 'assistant',
          'text': '识别结果',
          'imageIds': [],
          'selectedOptionIds': [],
          'agentReply': {
            'replyId': 'reply-rec-image',
            'replyType': 'recognition',
            'text': '识别结果',
            'cards': [
              {
                'cardType': 'recognition',
                'title': '识别结果',
                'imageId': 'test-image-id',
                'category': '运动鞋',
                'brand': 'Mock 品牌',
                'model': 'Mock 型号',
                'keywords': ['运动鞋', '白色'],
                'attributes': {'color': '白色'},
                'confidence': 0.82,
                'aiProvider': 'mock',
                'fallbackUsed': false,
                'explanation': '演示识别结果。',
                'recognitionId': 'rec-test-001',
              },
            ],
          },
          'createdAt': '2026-06-06T10:00:01+08:00',
        },
      ]);

      await tester.pumpWidget(_wrapChat(const ChatScreen(), overrides: ov));
      final container =
          ProviderScope.containerOf(tester.element(find.byType(ChatScreen)));
      await container
          .read(chatControllerProvider.notifier)
          .switchToSession('hist-image');
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.byKey(const Key('recognition_image_thumb')), findsOneWidget);
      expect(find.text('识别到：运动鞋'), findsOneWidget);
      expect(find.text('置信度 82%'), findsOneWidget);
      expect(find.text('来源：mock'), findsOneWidget);
      expect(find.text('可修正字段'), findsOneWidget);
    });

    testWidgets('recognition editable field chip opens correction sheet',
        (tester) async {
      final ov = _TestOverrides();
      final completer = Completer<AgentReply>();
      ov.chatApi.stubSendMessage(completer);

      await tester.pumpWidget(_wrapChat(const ChatScreen(), overrides: ov));
      await tester.enterText(find.byType(TextField), 'test');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.arrow_upward));
      await tester.pump();

      completer.complete(const AgentReply(
        replyId: 'reply-rec-chip',
        replyType: 'recognition',
        text: '识别结果',
        cards: [
          ReplyCard(
            cardType: 'recognition',
            title: '识别结果',
            category: '运动鞋',
            brand: 'Mock 品牌',
            model: 'Mock 型号',
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

      await tester.tap(find.text('颜色：白色'));
      await tester.pumpAndSettle();

      expect(find.widgetWithText(TextField, '商品类别'), findsOneWidget);
      expect(find.text('保存'), findsOneWidget);
    });

    testWidgets('switch to history session restores clarification card',
        (tester) async {
      final ov = _TestOverrides();
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
                  {'optionId': 'lowest_price', 'label': '价格最低'}
                ],
              }
            ],
          },
        },
      ]);
      await tester.pumpWidget(_wrapChat(const ChatScreen(), overrides: ov));
      await tester.tap(find.byIcon(Icons.history));
      await tester.pumpAndSettle();
      await tester.tap(find.text('历史会话'));
      await tester.pumpAndSettle();
      expect(find.text('价格最低'), findsOneWidget);
    });

    testWidgets('history restores product_recommendation with all card types',
        (tester) async {
      final ov = _TestOverrides();
      ov.chatApi.addHistoryMessages('hist-002', [
        {
          'messageId': 'msg-1',
          'role': 'user',
          'text': '推荐运动鞋',
          'imageIds': [],
          'selectedOptionIds': [],
          'createdAt': '2026-06-06T10:00:00+08:00',
        },
        {
          'messageId': 'msg-2',
          'role': 'assistant',
          'text': '我按你的偏好整理了几个平台的选择。',
          'imageIds': [],
          'selectedOptionIds': [],
          'createdAt': '2026-06-06T10:00:01+08:00',
          'agentReply': {
            'replyId': 'reply-pr',
            'replyType': 'product_recommendation',
            'text': '我按你的偏好整理了几个平台的选择。',
            'cards': [
              {
                'cardType': 'product_list',
                'title': '多平台商品结果',
                'products': [
                  {
                    'productId': 'jd-001',
                    'title': 'Mock 运动鞋 京东自营',
                    'platform': '京东-mock',
                    'price': 299.0,
                    'originalPrice': 399.0,
                    'shopName': '京东自营',
                    'imageUrl': '',
                    'productUrl': '',
                    'rating': 4.8,
                    'sales': 12000,
                    'tags': ['自营'],
                    'reasons': ['价格优惠'],
                    'score': 7.0,
                  },
                ],
              },
              {
                'cardType': 'comparison',
                'title': '平台比价',
                'platformStats': {
                  '京东-mock': {
                    'platform': '京东-mock',
                    'lowestPrice': 299.0,
                    'productCount': 2,
                    'highlight': '自营'
                  },
                  '拼多多-mock': {
                    'platform': '拼多多-mock',
                    'lowestPrice': 199.0,
                    'productCount': 2,
                    'highlight': '价格优势'
                  },
                },
              },
              {
                'cardType': 'recommendation',
                'title': '推荐购买',
                'productName': 'Mock 商品',
                'platform': '京东-mock',
                'price': 299.0,
                'reason': '综合评分较高',
              },
            ],
          },
        },
      ]);
      await tester.pumpWidget(_wrapChat(const ChatScreen(), overrides: ov));
      await tester.tap(find.byIcon(Icons.history));
      await tester.pumpAndSettle();
      await tester.tap(find.text('历史会话'));
      await tester.pumpAndSettle();

      expect(find.textContaining('找到 '), findsWidgets);
      expect(find.text('平台比价'), findsOneWidget);
      expect(find.text('京东'), findsWidgets);
      expect(find.text('拼多多'), findsOneWidget);
      expect(find.text('Mock 商品'), findsOneWidget);
    });

    testWidgets('voice button fills transcribed text', (tester) async {
      await tester.pumpWidget(_wrapChat(const ChatScreen()));
      await tester.tap(find.byIcon(Icons.mic_none));
      await tester.pumpAndSettle();
      expect(find.text('推荐耳机'), findsOneWidget);
    });

    testWidgets('empty product group list shows empty reason', (tester) async {
      final ov = _TestOverrides();
      final completer = Completer<AgentReply>();
      ov.chatApi.stubSendMessage(completer);

      await tester.pumpWidget(_wrapChat(const ChatScreen(), overrides: ov));
      await tester.enterText(find.byType(TextField), '50以内的耳机');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.arrow_upward));
      await tester.pump();

      completer.complete(AgentReply(
        replyId: 'reply-empty',
        replyType: 'product_recommendation',
        text: '当前预算下暂无合适的 Mock 商品',
        cards: const [
          ReplyCard(
            cardType: 'product_group_list',
            title: '商品结果',
            groups: [],
            emptyReason: '当前预算下暂无合适的 Mock 商品，请放宽条件。',
          ),
          ReplyCard(
            cardType: 'clarification',
            title: '继续筛选',
            options: [
              ClarificationOption(optionId: 'lowest_price', label: '价格最低'),
            ],
          ),
        ],
      ));
      await tester.pumpAndSettle();

      expect(find.text('暂未找到商品'), findsOneWidget);
      expect(find.text('当前预算下暂无合适的 Mock 商品，请放宽条件。'), findsOneWidget);
    });

    testWidgets('product group list shows lightweight summary', (tester) async {
      final ov = _TestOverrides();
      await tester.pumpWidget(_wrapChat(const ChatScreen(), overrides: ov));
      await tester.enterText(find.byType(TextField), '推荐耳机');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.arrow_upward));
      await tester.pumpAndSettle();

      // Should show product group list with compact info
      expect(find.textContaining('组商品'), findsOneWidget);
      // Should show group count
      expect(find.textContaining('组'), findsWidgets);
      // Should show price, platform badge, rating and reviews
      expect(find.textContaining('¥'), findsWidgets);
      expect(find.textContaining('起'), findsWidgets);
      expect(find.byIcon(Icons.chevron_right), findsWidgets);
      // Group row shows rating via star icon + number (not "X分" format)
      expect(find.byIcon(Icons.star_rounded), findsWidgets);
      expect(find.textContaining('评价'), findsWidgets);
      expect(find.text('放宽匹配'), findsNothing);
      // Should show clarification card
      expect(find.text('查看同款低价'), findsOneWidget);
      // Should NOT show heavy recommendation cards
      expect(find.text('推荐理由'), findsNothing);
      expect(find.text('注意事项'), findsNothing);
      expect(find.text('为什么推荐它'), findsNothing);
      expect(find.text('综合分 86'), findsNothing);
      expect(find.text('决策信号'), findsNothing);
    });

    testWidgets('old recommendation card without explanation still works',
        (tester) async {
      final ov = _TestOverrides();
      final completer = Completer<AgentReply>();
      ov.chatApi.stubSendMessage(completer);

      await tester.pumpWidget(_wrapChat(const ChatScreen(), overrides: ov));
      await tester.enterText(find.byType(TextField), 'test');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.arrow_upward));
      await tester.pump();

      // Old-style recommendation without explanation fields
      completer.complete(const AgentReply(
        replyId: 'reply-old',
        replyType: 'product_recommendation',
        text: '推荐结果',
        cards: [
          ReplyCard(cardType: 'product_list', title: '商品列表', products: [
            ProductItem(
                productId: 'p1',
                title: 'Test',
                platform: '京东-mock',
                price: 100,
                originalPrice: 150,
                shopName: 'Shop',
                imageUrl: '',
                productUrl: '',
                rating: 4.0,
                sales: 100,
                tags: [],
                reasons: [],
                score: 5),
          ]),
          ReplyCard(cardType: 'comparison', title: '比价', platformStats: {}),
          ReplyCard(
              cardType: 'recommendation',
              title: '推荐',
              productName: 'Old Card',
              platform: '京东-mock',
              price: 100,
              reason: 'test'),
        ],
      ));
      await tester.pumpAndSettle();

      expect(find.text('Old Card'), findsOneWidget);
      // Should not crash on missing fields
      expect(find.text('综合分'), findsNothing);
    });

    testWidgets('recommendation card hides provider status', (tester) async {
      final ov = _TestOverrides();
      await tester.pumpWidget(_wrapChat(const ChatScreen(), overrides: ov));
      await tester.enterText(find.byType(TextField), '推荐耳机');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.arrow_upward));
      await tester.pumpAndSettle();

      expect(find.text('意图：rule'), findsNothing);
      expect(find.text('解释：rule'), findsNothing);
    });

    testWidgets('history restores provider metadata', (tester) async {
      final ov = _TestOverrides();
      // Use minimal cards so the recommendation card is visible without scrolling
      ov.chatApi.addHistoryMessages('hist-prov', [
        {
          'messageId': 'm1',
          'role': 'user',
          'text': '推荐',
          'imageIds': [],
          'selectedOptionIds': [],
          'createdAt': '2026-06-06T10:00:00+08:00'
        },
        {
          'messageId': 'm2',
          'role': 'assistant',
          'text': '推荐结果',
          'imageIds': [],
          'selectedOptionIds': [],
          'createdAt': '2026-06-06T10:00:01+08:00',
          'agentReply': {
            'replyId': 'rp',
            'replyType': 'product_recommendation',
            'text': '推荐',
            'cards': [
              {'cardType': 'product_list', 'title': '商品', 'products': []},
              {'cardType': 'comparison', 'title': '比价', 'platformStats': {}},
              {
                'cardType': 'recommendation',
                'title': '推荐',
                'productName': 'T',
                'platform': '京东-mock',
                'price': 100.0,
                'reason': 'test',
                'decisionScore': 80,
                'decisionSignals': [],
                'evidence': [],
                'risks': [],
                'productAnalyses': [],
                'intentProvider': 'ark',
                'intentFallbackUsed': true,
                'explanationProvider': 'rule',
                'explanationFallbackUsed': false,
                'notices': []
              },
            ],
          }
        },
      ]);

      final controller = ChatController(ov.chatApi);
      await controller.switchToSession('hist-prov');
      expect(controller.messages, hasLength(2));
      final restoredReply = controller.messages[1].agentReply;
      expect(restoredReply, isNotNull);
      final restoredCard = restoredReply!.cards[2];
      expect(restoredCard.productName, 'T');
      expect(restoredCard.intentProvider, 'ark');
      expect(restoredCard.intentFallbackUsed, isTrue);

      await tester.pumpWidget(_wrapChat(const ChatScreen(), overrides: ov));
      await tester.tap(find.byIcon(Icons.history));
      await tester.pumpAndSettle();
      await tester.tap(find.text('历史会话'));
      await tester.pumpAndSettle();

      final uiController = ProviderScope.containerOf(
        tester.element(find.byType(ChatScreen)),
        listen: false,
      ).read(chatControllerProvider);
      expect(uiController.messages, hasLength(2));
      final uiReply = uiController.messages[1].agentReply;
      expect(uiReply, isNotNull);
      expect(uiReply!.cards[2].productName, 'T');

      // Verify history loaded
      expect(find.text('T'), findsOneWidget);
      expect(find.text('test'), findsOneWidget);
      // Provider metadata is retained in the model but hidden from the user UI.
      expect(find.text('意图：ark'), findsNothing);
      expect(find.text('已回退规则处理'), findsNothing);
    });
  });

  group('Product card extensions', () {
    test('ReplyCard parses filter summary', () {
      final card = ReplyCard.fromJson({
        'cardType': 'product_list',
        'title': '多平台商品结果',
        'products': [],
        'filterSummary': ['品类：耳机', '预算≤300元', '颜色：黑色'],
      });

      expect(card.filterSummary, ['品类：耳机', '预算≤300元', '颜色：黑色']);
    });

    testWidgets('shows brand badge, price trend, matched preference badges',
        (tester) async {
      final ov = _TestOverrides();
      final completer = Completer<AgentReply>();
      ov.chatApi.stubSendMessage(completer);

      await tester.pumpWidget(_wrapChat(const ChatScreen(), overrides: ov));
      await tester.enterText(find.byType(TextField), '推荐耳机');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.arrow_upward));
      await tester.pump();

      completer.complete(const AgentReply(
        replyId: 'reply-ext',
        replyType: 'product_recommendation',
        text: '推荐结果',
        cards: [
          ReplyCard(cardType: 'product_list', title: '多平台商品结果', products: [
            ProductItem(
              productId: 'jd-101',
              title: '索尼蓝牙耳机',
              platform: '京东-mock',
              price: 299,
              originalPrice: 499,
              shopName: '京东自营',
              imageUrl: '',
              productUrl: '',
              rating: 4.9,
              sales: 23000,
              tags: ['自营'],
              reasons: [],
              score: 8,
              brand: '索尼',
              priceHistory: [499, 459, 379, 309, 299],
              matchedPreferences: ['budget_match', 'high_rating'],
            ),
          ]),
        ],
      ));
      await tester.pumpAndSettle();

      expect(find.text('索尼无线降噪耳机 黑色款'), findsOneWidget);
      expect(find.text('京东 · 京东自营'), findsOneWidget);
      expect(find.textContaining('条评价'), findsOneWidget);
      expect(find.byKey(const Key('product_thumb_jd-101')), findsOneWidget);
      expect(find.text('近30天低价'), findsOneWidget);
      expect(find.text('自营/官方'), findsOneWidget);
      expect(find.text('券后价'), findsOneWidget);
      expect(find.text('有优惠'), findsNothing);
    });

    testWidgets('product row favorite updates state and avoids duplicate add',
        (tester) async {
      final ov = _TestOverrides();
      final completer = Completer<AgentReply>();
      ov.chatApi.stubSendMessage(completer);

      await tester.pumpWidget(_wrapChat(const ChatScreen(), overrides: ov));
      await tester.enterText(find.byType(TextField), '推荐耳机');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.arrow_upward));
      await tester.pump();

      completer.complete(const AgentReply(
        replyId: 'reply-fav-row',
        replyType: 'product_recommendation',
        text: '推荐结果',
        cards: [
          ReplyCard(cardType: 'product_list', title: '多平台商品结果', products: [
            ProductItem(
              productId: 'jd-101',
              title: '索尼蓝牙耳机',
              platform: '京东-mock',
              price: 299,
              originalPrice: 499,
              shopName: '京东自营',
              imageUrl: '',
              productUrl: '',
              rating: 4.9,
              sales: 23000,
              tags: ['自营'],
              reasons: [],
              score: 8,
              brand: '索尼',
            ),
          ]),
        ],
      ));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('favorite_jd-101')));
      await tester.pumpAndSettle();

      expect(find.text('已收藏'), findsOneWidget);
      expect(find.text('已收藏，可在「我的收藏」查看'), findsOneWidget);
      expect(ov.favoriteApi.addedPayloads, hasLength(1));
      expect(ov.favoriteApi.addedPayloads.single['productId'], 'jd-101');
      expect(ov.favoriteApi.addedPayloads.single['platform'], '京东-mock');
      expect(ov.favoriteApi.addedPayloads.single['brand'], '索尼');

      await tester.tap(find.byKey(const Key('favorite_jd-101')));
      await tester.pumpAndSettle();

      expect(ov.favoriteApi.addedPayloads, hasLength(1));
    });

    testWidgets('product row go button shows platform jump notice',
        (tester) async {
      final ov = _TestOverrides();
      final completer = Completer<AgentReply>();
      ov.chatApi.stubSendMessage(completer);

      await tester.pumpWidget(_wrapChat(const ChatScreen(), overrides: ov));
      await tester.enterText(find.byType(TextField), '推荐耳机');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.arrow_upward));
      await tester.pump();

      completer.complete(const AgentReply(
        replyId: 'reply-go-row',
        replyType: 'product_recommendation',
        text: '推荐结果',
        cards: [
          ReplyCard(cardType: 'product_list', title: '多平台商品结果', products: [
            ProductItem(
              productId: 'jd-101',
              title: '索尼蓝牙耳机',
              platform: '京东-mock',
              price: 299,
              originalPrice: 499,
              shopName: '京东自营',
              imageUrl: '',
              productUrl: '',
              rating: 4.9,
              sales: 23000,
              tags: ['自营'],
              reasons: [],
              score: 8,
              brand: '索尼',
            ),
          ]),
        ],
      ));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('go_jd-101')));
      await tester.pumpAndSettle();

      expect(find.text('即将跳转到京东'), findsOneWidget);
      expect(find.text('京东 · 京东自营'), findsWidgets);
      expect(find.text('¥299'), findsWidgets);
      expect(find.textContaining('当前演示使用 Mock 商品数据'), findsOneWidget);
      expect(find.text('知道了'), findsOneWidget);
    });

    testWidgets('comparison card shows average price', (tester) async {
      final ov = _TestOverrides();
      final completer = Completer<AgentReply>();
      ov.chatApi.stubSendMessage(completer);

      await tester.pumpWidget(_wrapChat(const ChatScreen(), overrides: ov));
      await tester.enterText(find.byType(TextField), '推荐耳机');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.arrow_upward));
      await tester.pump();

      completer.complete(const AgentReply(
        replyId: 'reply-avg',
        replyType: 'product_recommendation',
        text: '推荐结果',
        cards: [
          ReplyCard(cardType: 'product_list', title: '多平台商品结果', products: []),
          ReplyCard(cardType: 'comparison', title: '平台比价', platformStats: {
            '京东-mock': {
              'platform': '京东-mock',
              'lowestPrice': 199,
              'averagePrice': 259,
              'productCount': 4,
              'highlight': '自营保障，物流快',
            },
          }),
        ],
      ));
      await tester.pumpAndSettle();

      expect(find.text('最低 ¥199'), findsOneWidget);
      expect(find.text('均价 ¥259 · 4件'), findsOneWidget);
      expect(find.text('最低价平台'), findsOneWidget);
      expect(find.text('更稳妥平台'), findsOneWidget);
      expect(find.text('自营保障，物流快'), findsOneWidget);
    });

    testWidgets('product group list shows active filter summary',
        (tester) async {
      final ov = _TestOverrides();
      final completer = Completer<AgentReply>();
      ov.chatApi.stubSendMessage(completer);

      await tester.pumpWidget(_wrapChat(const ChatScreen(), overrides: ov));
      await tester.enterText(find.byType(TextField), '推荐耳机');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.arrow_upward));
      await tester.pump();

      completer.complete(const AgentReply(
        replyId: 'reply-filter',
        replyType: 'product_recommendation',
        text: '推荐结果',
        cards: [
          ReplyCard(
            cardType: 'product_group_list',
            title: '商品结果',
            filterSummary: ['品类：耳机', '预算≤300元', '颜色：黑色'],
            groups: [],
          ),
        ],
      ));
      await tester.pumpAndSettle();

      expect(find.text('黑色耳机'), findsOneWidget);
      expect(find.text('¥300以内'), findsOneWidget);
      expect(find.text('全部平台'), findsOneWidget);
    });

    testWidgets('product group filter editor submits modified text',
        (tester) async {
      final ov = _TestOverrides();
      final completer = Completer<AgentReply>();
      ov.chatApi.stubSendMessage(completer);

      await tester.pumpWidget(_wrapChat(const ChatScreen(), overrides: ov));
      await tester.enterText(find.byType(TextField), '推荐耳机');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.arrow_upward));
      await tester.pump();

      completer.complete(const AgentReply(
        replyId: 'reply-filter-edit',
        replyType: 'product_recommendation',
        text: '找到 1 组商品',
        cards: [
          ReplyCard(
            cardType: 'product_group_list',
            title: '商品结果',
            filterSummary: ['品类：耳机', '预算≤300元', '颜色：黑色'],
            groups: [],
          ),
        ],
      ));
      await tester.pumpAndSettle();

      expect(find.text('本轮筛选'), findsOneWidget);
      expect(find.text('提交修改'), findsNothing);

      await tester.tap(find.text('修改'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextFormField), '索尼黑色耳机 500以内 只看京东');
      await tester.pumpAndSettle();

      expect(find.text('提交修改'), findsOneWidget);
      await tester.tap(find.text('提交修改'));
      await tester.pumpAndSettle();

      expect(ov.chatApi.sendRequests.last['text'], '索尼黑色耳机 500以内 只看京东');
    });

    testWidgets('product group list shows recognition result box',
        (tester) async {
      final ov = _TestOverrides();
      final completer = Completer<AgentReply>();
      ov.chatApi.stubSendMessage(completer);

      await tester.pumpWidget(_wrapChat(const ChatScreen(), overrides: ov));
      await tester.enterText(find.byType(TextField), '识别这张图');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.arrow_upward));
      await tester.pump();

      completer.complete(const AgentReply(
        replyId: 'reply-rec-groups',
        replyType: 'product_recommendation',
        text: '找到 0 组商品',
        cards: [
          ReplyCard(
            cardType: 'product_group_list',
            title: '商品结果',
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
            filterSummary: ['品类：运动鞋'],
            groups: [],
          ),
          ReplyCard(
            cardType: 'clarification',
            title: '继续筛选',
            options: [
              ClarificationOption(optionId: 'lowest_price', label: '查看同款低价'),
            ],
          ),
        ],
      ));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('recognition_result_box')), findsOneWidget);
      expect(find.text('识别结果'), findsOneWidget);
      expect(find.text('识别到：运动鞋'), findsOneWidget);
      expect(find.text('品牌：Mock 品牌'), findsOneWidget);
      expect(find.text('型号：Mock 型号'), findsOneWidget);
      expect(find.text('置信度 82%'), findsOneWidget);
      expect(find.text('修正'), findsOneWidget);
      expect(find.text('暂未找到商品'), findsOneWidget);
      expect(find.text('查看同款低价'), findsOneWidget);
    });

    testWidgets('product group list hides empty filter summary',
        (tester) async {
      final ov = _TestOverrides();
      final completer = Completer<AgentReply>();
      ov.chatApi.stubSendMessage(completer);

      await tester.pumpWidget(_wrapChat(const ChatScreen(), overrides: ov));
      await tester.enterText(find.byType(TextField), '推荐耳机');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.arrow_upward));
      await tester.pump();

      completer.complete(const AgentReply(
        replyId: 'reply-no-filter',
        replyType: 'product_recommendation',
        text: '推荐结果',
        cards: [
          ReplyCard(cardType: 'product_group_list', title: '商品结果', groups: []),
        ],
      ));
      await tester.pumpAndSettle();

      expect(find.textContaining('当前条件：'), findsNothing);
    });

    testWidgets('dynamic suggestion options render labels', (tester) async {
      final ov = _TestOverrides();
      final completer = Completer<AgentReply>();
      ov.chatApi.stubSendMessage(completer);

      await tester.pumpWidget(_wrapChat(const ChatScreen(), overrides: ov));
      await tester.enterText(find.byType(TextField), 'hi');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.arrow_upward));
      await tester.pump();

      completer.complete(const AgentReply(
        replyId: 'reply-sug',
        replyType: 'clarification',
        text: '请选择',
        cards: [
          ReplyCard(cardType: 'clarification', title: '继续筛选', options: [
            ClarificationOption(optionId: 'lowest_price', label: '查看同款低价'),
            ClarificationOption(optionId: 'style_similar', label: '相似风格推荐'),
            ClarificationOption(optionId: 'price_history', label: '查看历史价格走势'),
          ]),
        ],
      ));
      await tester.pumpAndSettle();

      expect(find.text('查看同款低价'), findsOneWidget);
      expect(find.text('相似风格推荐'), findsOneWidget);
      expect(find.text('查看历史价格走势'), findsOneWidget);
    });

    test('PlatformOfferSummary.fromJson parses new fields', () {
      final p = PlatformOfferSummary.fromJson({
        'productId': 'jd-001',
        'platform': '京东-mock',
        'price': 199,
        'originalPrice': 299,
        'shopName': '测试店铺',
        'productUrl': '',
        'rating': 4.5,
        'sales': 1000,
        'tags': ['自营'],
        'reasons': ['低价'],
        'score': 7.5,
        'title': '测试商品标题',
        'imageUrl': 'https://example.com/img.jpg',
        'brand': '测试品牌',
        'priceHistory': [299, 259, 199],
        'matchedPreferences': ['lowest_price'],
        'specs': [
          {'label': '品类', 'value': '耳机'},
          {'label': '店铺', 'value': '测试店铺'},
        ],
      });

      expect(p.productId, 'jd-001');
      expect(p.title, '测试商品标题');
      expect(p.imageUrl, 'https://example.com/img.jpg');
      expect(p.brand, '测试品牌');
      expect(p.priceHistory, [299, 259, 199]);
      expect(p.matchedPreferences, ['lowest_price']);
      expect(p.specs.length, 2);
      expect(p.specs[0].label, '品类');
      expect(p.specs[0].value, '耳机');
    });

    test('PlatformOfferSummary.fromJson handles missing new fields', () {
      final p = PlatformOfferSummary.fromJson({
        'productId': 'jd-001',
        'platform': '京东-mock',
        'price': 199,
        'originalPrice': 299,
        'shopName': '测试店铺',
        'productUrl': '',
        'rating': 4.5,
        'sales': 1000,
        'tags': [],
        'reasons': [],
      });

      // Should not crash — use defaults
      expect(p.title, '');
      expect(p.imageUrl, '');
      expect(p.brand, '');
      expect(p.priceHistory, []);
      expect(p.matchedPreferences, []);
      expect(p.specs, []);
      expect(p.score, 0);
    });

    testWidgets('group row shows only minimal info', (tester) async {
      final ov = _TestOverrides();
      await tester.pumpWidget(_wrapChat(const ChatScreen(), overrides: ov));
      await tester.enterText(find.byType(TextField), '推荐耳机');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.arrow_upward));
      await tester.pumpAndSettle();

      // Group row shows: thumbnail placeholder, title, price, rating star, reviews, chevron
      expect(find.textContaining('组商品'), findsOneWidget);
      expect(find.textContaining('¥'), findsWidgets);
      // Platform count badge now shown in group row
      expect(find.textContaining('个平台'), findsWidgets);
      expect(find.byIcon(Icons.chevron_right), findsWidgets);
      // Group row now shows ratings (star icon + number) and reviews count
      expect(find.byIcon(Icons.star_rounded), findsWidgets);
      expect(find.textContaining('评价'), findsWidgets);
      // Should NOT show strikethrough original price
      expect(find.text('¥399'), findsNothing);
    });

    testWidgets('group row favorite saves cheapest platform offer',
        (tester) async {
      final ov = _TestOverrides();
      await tester.pumpWidget(_wrapChat(const ChatScreen(), overrides: ov));
      await tester.enterText(find.byType(TextField), '推荐耳机');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.arrow_upward));
      await tester.pumpAndSettle();

      final favoriteButton = find.byKey(const Key('favorite_group_pdd-001'));
      await _dragUntilFinderVisible(tester, favoriteButton);
      await tester.tap(favoriteButton);
      await tester.pumpAndSettle();

      expect(ov.favoriteApi.addedPayloads, hasLength(1));
      expect(ov.favoriteApi.addedPayloads.single['productId'], 'pdd-001');
      expect(ov.favoriteApi.addedPayloads.single['platform'], '拼多多-mock');
    });

    testWidgets('tapping group row opens 商品详情 page', (tester) async {
      final ov = _TestOverrides();
      await tester.pumpWidget(_wrapChat(const ChatScreen(), overrides: ov));
      await tester.enterText(find.byType(TextField), '推荐耳机');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.arrow_upward));
      await tester.pumpAndSettle();

      // Scroll the first chevron into view, then tap to open detail page
      await tester.scrollUntilVisible(
        find.byIcon(Icons.chevron_right).first,
        200,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byIcon(Icons.chevron_right).first);
      await tester.pumpAndSettle();

      // Should be on detail page
      expect(find.text('商品详情'), findsOneWidget);
      await _dragUntilFinderVisible(tester, find.text('平台比价'));
      expect(find.text('平台比价'), findsOneWidget);
    });

    testWidgets('detail page shows all required sections', (tester) async {
      final ov = _TestOverrides();
      await tester.pumpWidget(_wrapChat(const ChatScreen(), overrides: ov));
      await tester.enterText(find.byType(TextField), '推荐耳机');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.arrow_upward));
      await tester.pumpAndSettle();

      // Open detail page
      await tester.scrollUntilVisible(
        find.byIcon(Icons.chevron_right).first,
        200,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byIcon(Icons.chevron_right).first);
      await tester.pumpAndSettle();

      // Header
      expect(find.text('商品详情'), findsOneWidget);
      // Price section
      expect(find.textContaining('¥'), findsWidgets);
      expect(find.text('购买判断'), findsOneWidget);
      expect(find.text('评价概览'), findsOneWidget);
      expect(find.text('平均评分'), findsOneWidget);
      expect(find.textContaining('最低价'), findsWidgets);
      expect(find.text('评分最高'), findsWidgets);
      // Platform comparison list
      await _dragUntilFinderVisible(tester, find.text('平台比价'));
      expect(find.text('平台比价'), findsOneWidget);
      await _dragUntilFinderVisible(tester, find.text('去看看'));
      // Platform cards show shop name and action buttons
      expect(find.text('到手价'), findsWidgets);
      expect(find.text('精选评论'), findsWidgets);
      expect(find.text('样例口碑摘要'), findsWidgets);
      expect(find.text('去看看'), findsWidgets);
      expect(find.text('价格提醒'), findsWidgets);
      // Rating/sales displayed
      expect(find.textContaining('分'), findsWidgets);
    });

    testWidgets('detail page uses compact placeholder when image is missing',
        (tester) async {
      const group = ProductGroup(
        groupId: 'headphone-test',
        displayTitle: '测试耳机 黑色',
        category: '耳机',
        brand: '测试品牌',
        thumbnailUrl: '',
        bestPrice: 299,
        originalPrice: 399,
        priceRange: PriceRange(min: 299, max: 299),
        platformCount: 1,
        platforms: [
          PlatformOfferSummary(
            productId: 'headphone-test-jd',
            platform: '京东-mock',
            price: 299,
            originalPrice: 399,
            shopName: '测试京东自营',
            productUrl: '',
            rating: 4.9,
            sales: 23000,
            tags: ['自营'],
            reasons: ['高评分'],
            title: '测试耳机 黑色 高音质',
            priceHistory: [399, 369, 329, 299],
            matchedPreferences: ['budget_match', 'high_rating'],
          ),
        ],
        highlights: ['最低 ¥299', '高评分'],
        matchLevel: 'strict',
      );

      await tester.pumpWidget(_wrapChat(
        const ProductGroupDetailScreen(group: group),
      ));

      final placeholder =
          find.byKey(const Key('product_detail_thumbnail_placeholder'));
      expect(placeholder, findsOneWidget);
      expect(tester.getSize(placeholder), const Size(88, 88));
      expect(find.textContaining('价格区间'), findsNothing);
      expect(find.textContaining('个平台有售'), findsOneWidget);
      expect(find.text('购买判断'), findsOneWidget);
      expect(find.text('评价概览'), findsOneWidget);
      await _dragUntilFinderVisible(tester, find.text('推荐点'));
      expect(find.text('推荐点'), findsOneWidget);
      expect(find.text('精选评论'), findsOneWidget);
      expect(find.text('样例口碑摘要'), findsOneWidget);
      expect(find.text('预算匹配'), findsOneWidget);
      expect(find.textContaining('价格走势'), findsOneWidget);
    });

    testWidgets('detail page back returns to chat', (tester) async {
      final ov = _TestOverrides();
      await tester.pumpWidget(_wrapChat(const ChatScreen(), overrides: ov));
      await tester.enterText(find.byType(TextField), '推荐耳机');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.arrow_upward));
      await tester.pumpAndSettle();

      // Open detail page
      await tester.scrollUntilVisible(
        find.byIcon(Icons.chevron_right).first,
        200,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byIcon(Icons.chevron_right).first);
      await tester.pumpAndSettle();
      expect(find.text('商品详情'), findsOneWidget);

      // Go back
      await tester.tap(find.byTooltip('Back'));
      await tester.pumpAndSettle();

      // Back on chat screen
      expect(find.textContaining('组商品'), findsOneWidget);
      expect(find.text('查看同款低价'), findsOneWidget);
    });

    testWidgets('detail page price alert calls API with platform price',
        (tester) async {
      final ov = _TestOverrides();
      await tester.pumpWidget(_wrapChat(const ChatScreen(), overrides: ov));
      await tester.enterText(find.byType(TextField), '推荐耳机');
      await tester.pump();
      await tester.tap(find.byIcon(Icons.arrow_upward));
      await tester.pumpAndSettle();

      // Open detail page
      await tester.scrollUntilVisible(
        find.byIcon(Icons.chevron_right).first,
        200,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byIcon(Icons.chevron_right).first);
      await tester.pumpAndSettle();
      expect(find.text('商品详情'), findsOneWidget);

      // Scroll to the first "价格提醒" button (may be off-screen)
      await _dragUntilFinderVisible(tester, find.text('价格提醒'));

      // Tap "价格提醒" on first platform card
      await tester.tap(find.text('价格提醒').first);
      await tester.pumpAndSettle();

      // Enter target price (leave default = platform price = 199)
      await tester.tap(find.text('保存'));
      await tester.pumpAndSettle();

      // Verify API was called with platform price as targetPrice
      expect(ov.priceAlertApi.createdPayloads, hasLength(1));
      final payload = ov.priceAlertApi.createdPayloads.first;
      expect(payload['productId'], isNotEmpty);
      expect(payload['platform'], contains('-mock'));
      // Default is current platform price (299), not 0.9 * price
      expect(payload['targetPrice'], 299.0);
      expect(payload['note'], '从商品详情页创建');
    });
  });
}
