import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import '../../core/network/api_client.dart';
import '../../core/theme/app_theme.dart';
import '../auth/auth_controller.dart';
import '../voice/voice_api.dart';
import 'chat_controller.dart';
import 'chat_history_drawer.dart';
import 'chat_models.dart';
import 'chat_providers.dart';
import '../memory/behavior_events.dart';
import '../memory/memory_store.dart';
import '../memory/onboarding_dialog.dart';
import '../memory/query_keywords.dart';
import '../memory/user_profile.dart';
import 'product_group_detail_screen.dart';
import 'product_thumb_painter.dart';
import 'recognition_detail_screen.dart';

final voiceApiProvider = Provider<VoiceApi>((ref) {
  return VoiceApi(baseUrl: ref.watch(apiBaseUrlProvider));
});

/// Chat-style shopping agent home screen.
class ChatScreen extends ConsumerStatefulWidget {
  const ChatScreen({super.key});

  @override
  ConsumerState<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends ConsumerState<ChatScreen> {
  final _textController = TextEditingController();
  final _textFocusNode = FocusNode();
  final _scrollController = ScrollController();
  final _picker = ImagePicker();
  final _scaffoldKey = GlobalKey<ScaffoldState>();
  final Set<String> _favoriteProductIds = <String>{};
  final Set<String> _editingFilterKeys = <String>{};
  final Map<String, String> _filterDrafts = <String, String>{};
  File? _pendingImage;
  String? _uploadedImageId;
  bool _imageUploadFailed = false;

  @override
  void initState() {
    super.initState();
    _textFocusNode.addListener(_onTextFocusChanged);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(chatControllerProvider.notifier).loadSessions();
      _checkOnboarding();
    });
  }

  void _onTextFocusChanged() {
    if (mounted) {
      setState(() {});
    }
  }

  void _checkOnboarding() async {
    final store = ref.read(memoryStoreProvider);
    final privacyAccepted = await store.isPrivacyAccepted();
    if (!privacyAccepted && mounted) {
      final accepted = await showDialog<bool>(
        context: context,
        barrierDismissible: false,
        builder: (_) => _PrivacyNoticeDialog(),
      );
      if (accepted == true) {
        await store.setPrivacyAccepted();
      } else {
        // User skipped — disable personalization and skip onboarding
        await ref
            .read(userProfileProvider.notifier)
            .setPersonalizationEnabled(false);
        await store.setOnboardingDone();
        return;
      }
    }
    final onboarded = await store.isOnboardingDone();
    if (!onboarded && mounted) {
      showDialog(
        context: context,
        barrierDismissible: false,
        builder: (_) => const OnboardingDialog(),
      );
    }
  }

  /// Build the profile payload to send with chat requests.
  /// Only includes profile when personalization is enabled.
  Map<String, dynamic>? _profileForRequest() {
    final profile = ref.read(userProfileProvider);
    if (!profile.personalizationEnabled) return null;
    final p = profile.toJson();
    // Remove control flags before sending
    p.remove('personalizationEnabled');
    return p.isEmpty ? null : p;
  }

  @override
  void dispose() {
    _textFocusNode.removeListener(_onTextFocusChanged);
    _textFocusNode.dispose();
    _textController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  // ── Actions ────────────────────────────────────────────────

  void _sendMessage() {
    final text = _textController.text.trim();
    final hasText = text.isNotEmpty;
    final hasImage = _uploadedImageId != null;
    if (_imageUploadInProgress) return;
    if (!hasText && !hasImage) return;
    if (ref.read(chatControllerProvider).sending) return;

    final imageIds = _uploadedImageId != null ? [_uploadedImageId!] : null;
    final imagePaths =
        hasImage && _pendingImage != null ? [_pendingImage!.path] : null;
    ref.read(chatControllerProvider.notifier).sendTextMessage(
          hasText ? text : '',
          imageIds: imageIds,
          imagePaths: imagePaths,
          profile: _profileForRequest(),
        );

    // Record search behavior event and refresh inferred profile.
    // Enrich with structured signals (category, brand, price) so the
    // profile engine can extract useful inferences from search queries.
    if (hasText) {
      final recorder = ref.read(behaviorRecorderProvider);
      final kw = const QueryKeywordExtractor().extract(text);
      recorder.record(
        BehaviorEventType.search,
        query: text,
        category: kw.category,
        brand: kw.brand,
        price: kw.priceMax,
      );
      ref.read(userProfileProvider.notifier).refreshInferred();
    }

    _textController.clear();
    setState(() {
      _pendingImage = null;
      _uploadedImageId = null;
      _imageUploadFailed = false;
    });
    _scrollToBottom();
  }

  bool get _imageUploadInProgress {
    return _pendingImage != null &&
        _uploadedImageId == null &&
        !_imageUploadFailed;
  }

  bool _canSendMessage(bool sending, String draftText) {
    if (sending || _imageUploadInProgress) {
      return false;
    }
    return draftText.trim().isNotEmpty || _uploadedImageId != null;
  }

  void _onOptionSelected(String optionId) {
    ref
        .read(chatControllerProvider.notifier)
        .selectOption(optionId, profile: _profileForRequest());
    ref
        .read(behaviorRecorderProvider)
        .record(BehaviorEventType.filterApply, optionId: optionId);
    _scrollToBottom();
  }

  Future<void> _pickImage(ImageSource source) async {
    final picked = await _picker.pickImage(
      source: source,
      imageQuality: 85,
      maxWidth: 1920,
      maxHeight: 1920,
    );
    if (picked == null) return;

    setState(() {
      _pendingImage = File(picked.path);
      _uploadedImageId = null;
      _imageUploadFailed = false;
    });

    final imageId = await ref
        .read(chatControllerProvider.notifier)
        .uploadImage(File(picked.path));
    if (mounted) {
      setState(() {
        _uploadedImageId = imageId;
        _imageUploadFailed = imageId == null;
      });
    }
  }

  void _showImageSourceSheet() {
    showModalBottomSheet(
      context: context,
      builder: (ctx) => SafeArea(
        child: Wrap(
          children: [
            ListTile(
              leading: const Icon(Icons.camera_alt),
              title: const Text('拍照'),
              onTap: () {
                Navigator.pop(ctx);
                _pickImage(ImageSource.camera);
              },
            ),
            ListTile(
              leading: const Icon(Icons.photo_library),
              title: const Text('从相册选择'),
              onTap: () {
                Navigator.pop(ctx);
                _pickImage(ImageSource.gallery);
              },
            ),
          ],
        ),
      ),
    );
  }

  /// Demo voice flow: synthesizes a tiny audio buffer and round-trips the
  /// `/api/voice/transcribe` endpoint. Real microphone capture can plug in by
  /// providing real bytes here (e.g. via the `record` plugin).
  Future<void> _onVoiceTap() async {
    final messenger = ScaffoldMessenger.of(context);
    messenger.showSnackBar(const SnackBar(
      content: Text('正在向语音服务发送演示音频…'),
      duration: Duration(seconds: 1),
    ));
    try {
      final api = ref.read(voiceApiProvider);
      final result =
          await api.transcribeBytes(List<int>.generate(64, (i) => i % 256));
      if (!mounted) return;
      _textController.text = result.text;
      messenger.showSnackBar(SnackBar(
        content: Text(
            '语音转写（${result.provider}${result.fallbackUsed ? "·fallback" : ""}）：${result.text}'),
        duration: const Duration(seconds: 2),
      ));
    } catch (e) {
      if (mounted) {
        messenger.showSnackBar(SnackBar(content: Text('语音转写失败：$e')));
      }
    }
  }

  Future<void> _addToFavorites(ReplyCard card) async {
    final messenger = ScaffoldMessenger.of(context);
    final productId = card.productName != null ? card.productName! : 'unknown';
    final payload = <String, dynamic>{
      'productId': productId,
      'title': card.productName ?? '推荐商品',
      'platform': card.platform ?? '',
      'price': card.price ?? 0,
      'shopName': null,
      'brand': null,
    };
    try {
      final token = ref.read(authControllerProvider).session?.token;
      await ref.read(favoriteApiInChatProvider).add(payload, token: token);
      if (mounted) {
        messenger.showSnackBar(const SnackBar(content: Text('已加入收藏')));
      }
    } catch (e) {
      if (mounted) {
        messenger.showSnackBar(SnackBar(content: Text('收藏失败：$e')));
      }
    }
  }

  Future<void> _addProductToFavorites(ProductItem product) async {
    final messenger = ScaffoldMessenger.of(context);
    if (_favoriteProductIds.contains(product.productId)) {
      messenger.showSnackBar(const SnackBar(content: Text('已收藏')));
      return;
    }

    final payload = <String, dynamic>{
      'productId': product.productId,
      'title': _displayProductTitle(product),
      'platform': product.platform,
      'price': product.price,
      'shopName': product.shopName,
      'brand': product.brand,
      'imageUrl': product.imageUrl,
      'productUrl': product.productUrl,
    };
    try {
      final token = ref.read(authControllerProvider).session?.token;
      await ref.read(favoriteApiInChatProvider).add(payload, token: token);
      if (!mounted) return;
      setState(() {
        _favoriteProductIds.add(product.productId);
      });
      messenger.showSnackBar(
        const SnackBar(content: Text('已收藏，可在「我的收藏」查看')),
      );
    } catch (e) {
      if (mounted) {
        messenger.showSnackBar(SnackBar(content: Text('收藏失败：$e')));
      }
    }
  }

  Future<void> _addPlatformOfferToFavorites(PlatformOfferSummary offer,
      {ProductGroup? group}) async {
    final messenger = ScaffoldMessenger.of(context);
    if (_favoriteProductIds.contains(offer.productId)) {
      messenger.showSnackBar(const SnackBar(content: Text('已收藏')));
      return;
    }

    final payload = <String, dynamic>{
      'productId': offer.productId,
      'title': offer.title.isNotEmpty
          ? offer.title
          : (group?.displayTitle ?? '推荐商品'),
      'platform': offer.platform,
      'price': offer.price,
      'shopName': offer.shopName,
      'brand': offer.brand.isNotEmpty ? offer.brand : group?.brand,
      'imageUrl': offer.imageUrl.isNotEmpty
          ? offer.imageUrl
          : (group?.thumbnailUrl ?? ''),
      'productUrl': offer.productUrl,
    };
    try {
      final token = ref.read(authControllerProvider).session?.token;
      await ref.read(favoriteApiInChatProvider).add(payload, token: token);
      if (!mounted) return;
      setState(() {
        _favoriteProductIds.add(offer.productId);
      });
      await ref.read(behaviorRecorderProvider).record(
            BehaviorEventType.favorite,
            productId: offer.productId,
            platform: offer.platform,
            price: offer.price,
            category: group?.category,
            brand: offer.brand.isNotEmpty ? offer.brand : group?.brand,
            tags: offer.tags,
          );
      messenger.showSnackBar(
        const SnackBar(content: Text('已收藏，可在「我的收藏」查看')),
      );
    } catch (e) {
      if (mounted) {
        messenger.showSnackBar(SnackBar(content: Text('收藏失败：$e')));
      }
    }
  }

  void _showProductJumpSheet(ProductItem product) {
    final platform = _platformLabel(product.platform);
    showModalBottomSheet(
      context: context,
      builder: (ctx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 14, 16, 16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('即将跳转到$platform',
                  style: const TextStyle(
                      fontSize: 16, fontWeight: FontWeight.w700)),
              const SizedBox(height: 12),
              Text(_displayProductTitle(product),
                  style: const TextStyle(
                      fontSize: 14, height: 1.35, fontWeight: FontWeight.w600)),
              const SizedBox(height: 6),
              Text(_shopLine(product),
                  style:
                      const TextStyle(fontSize: 12, color: AppColors.inkSoft)),
              const SizedBox(height: 4),
              Text('¥${product.price.toStringAsFixed(0)}',
                  style: const TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                      color: AppColors.priceRed)),
              const SizedBox(height: 12),
              Text(
                '当前演示使用公开样例商品数据，不会打开真实电商页面。正式接入后将跳转到$platform商品详情页。',
                style: const TextStyle(
                    fontSize: 13, height: 1.45, color: AppColors.inkSoft),
              ),
              const SizedBox(height: 14),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: () => Navigator.of(ctx).pop(),
                  child: const Text('知道了'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _setPriceAlert(ReplyCard card) async {
    if (card.price == null) return;
    final controller =
        TextEditingController(text: (card.price! * 0.9).round().toString());
    final result = await showDialog<double>(
      context: context,
      builder: (ctx) {
        return AlertDialog(
          title: const Text('设置价格提醒'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('当 ${card.productName ?? "该商品"} 价格 ≤ 以下数值时触发：'),
              const SizedBox(height: 8),
              TextField(
                controller: controller,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(prefixText: '¥ '),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(),
              child: const Text('取消'),
            ),
            ElevatedButton(
              onPressed: () {
                final v = double.tryParse(controller.text);
                Navigator.of(ctx).pop(v);
              },
              child: const Text('保存'),
            ),
          ],
        );
      },
    );
    if (result == null || result <= 0) return;
    final messenger = ScaffoldMessenger.of(context);
    try {
      final token = ref.read(authControllerProvider).session?.token;
      await ref.read(priceAlertApiInChatProvider).create({
        'productId': card.productName ?? 'unknown',
        'title': card.productName ?? '推荐商品',
        'platform': card.platform ?? '',
        'targetPrice': result,
        'note': '从推荐卡创建',
      }, token: token);
      if (mounted) {
        messenger.showSnackBar(SnackBar(
          content: Text('已设置价格提醒：¥${result.toStringAsFixed(0)}'),
        ));
      }
    } catch (e) {
      if (mounted) {
        messenger.showSnackBar(SnackBar(content: Text('设置失败：$e')));
      }
    }
  }

  void _openCorrectionSheet(ReplyCard recognitionCard) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => RecognitionDetailScreen(
          recognitionCard: recognitionCard,
          imagePath: _recognitionImagePath(recognitionCard.imageId),
        ),
      ),
    );
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _animateToBottom();
      Future<void>.delayed(const Duration(milliseconds: 120), () {
        if (!mounted) return;
        _animateToBottom();
      });
    });
  }

  void _animateToBottom() {
    if (_scrollController.hasClients) {
      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent,
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOut,
      );
    }
  }

  // ── Build ──────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    final controller = ref.watch(chatControllerProvider);
    final messages = controller.messages;
    final recognitionQuickCard = _latestRecognitionMetaCard(messages);
    ref.listen(chatControllerProvider, (previous, next) {
      final previousCount = previous?.messages.length ?? 0;
      final shouldScroll = previousCount != next.messages.length ||
          (previous?.sending == true && !next.sending);
      if (shouldScroll) {
        _scrollToBottom();
      }
    });

    return Scaffold(
      key: _scaffoldKey,
      backgroundColor: AppColors.chatBackground,
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.history),
          tooltip: '历史对话',
          onPressed: () => _scaffoldKey.currentState?.openDrawer(),
        ),
        title: const Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('识价镜',
                style: TextStyle(
                    fontSize: 17,
                    fontWeight: FontWeight.w700,
                    letterSpacing: -0.3)),
            SizedBox(width: 8),
            Text('拍照识物 · 比价',
                style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w400,
                    color: AppColors.inkSoft)),
          ],
        ),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 4),
            child: IconButton(
              icon: const Icon(Icons.person_outline, size: 22),
              color: AppColors.inkBody,
              onPressed: () => context.go('/me'),
            ),
          ),
        ],
      ),
      drawer: ChatHistoryDrawer(
        onClose: () {
          if (_scaffoldKey.currentState?.isDrawerOpen ?? false) {
            Navigator.pop(context);
          }
        },
      ),
      body: Column(
        children: [
          Expanded(
            child: messages.isEmpty
                ? _buildEmpty()
                : ListView.builder(
                    key: const Key('chat_message_list'),
                    controller: _scrollController,
                    padding: const EdgeInsets.fromLTRB(12, 10, 12, 14),
                    itemCount: messages.length,
                    itemBuilder: (context, index) =>
                        _buildMessage(messages[index]),
                  ),
          ),
          if (recognitionQuickCard != null)
            _buildRecognitionQuickAction(recognitionQuickCard),
          _buildInputBar(recognitionQuickCard),
        ],
      ),
    );
  }

  ReplyCard? _latestRecognitionMetaCard(List<ChatMessage> messages) {
    for (final msg in messages.reversed) {
      final reply = msg.agentReply;
      if (reply == null) continue;
      for (final card in reply.cards.reversed) {
        if (_hasRecognitionMeta(card)) {
          return card;
        }
      }
    }
    return null;
  }

  Widget _buildRecognitionQuickAction(ReplyCard card) {
    final category = card.category?.trim();
    final brand = card.brand?.trim();
    final title = category != null && category.isNotEmpty ? category : '识别结果';
    final meta =
        brand != null && brand.isNotEmpty ? brand : _confidenceText(card);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
      color: AppColors.panel,
      child: OutlinedButton.icon(
        key: const Key('recognition_quick_action'),
        onPressed: () => _openCorrectionSheet(card),
        icon: const Icon(Icons.image_search, size: 18),
        label: Align(
          alignment: Alignment.centerLeft,
          child: Text(
            '查看/修改本次识别结果 · $title · $meta',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ),
        style: OutlinedButton.styleFrom(
          alignment: Alignment.centerLeft,
          foregroundColor: AppColors.inkBody,
          backgroundColor: AppColors.panelSoft,
          side: BorderSide(color: AppColors.accent.withAlpha(70)),
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          textStyle: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
          minimumSize: const Size.fromHeight(42),
        ),
      ),
    );
  }

  Widget _buildEmpty() {
    return const Center(
      child: Padding(
        padding: EdgeInsets.symmetric(horizontal: 32),
        child: Text(
          '告诉我你想买什么',
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: 24,
            fontWeight: FontWeight.w700,
            color: AppColors.inkMain,
          ),
        ),
      ),
    );
  }

  // ── Message rendering ──────────────────────────────────────

  Widget _buildMessage(ChatMessage msg) {
    if (msg.isLoading) return _buildLoadingBubble();
    if (msg.role == ChatRole.user) return _buildUserMessage(msg);
    return _buildAssistantMessage(msg);
  }

  Widget _buildLoadingBubble() {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10, left: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: BoxDecoration(
              color: AppColors.panel,
              borderRadius: BorderRadius.circular(16),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withAlpha(6),
                  blurRadius: 4,
                  offset: const Offset(0, 1),
                ),
              ],
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const SizedBox(
                  width: 15,
                  height: 15,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
                const SizedBox(width: 8),
                const Text('AI 正在为你查找…',
                    style: TextStyle(fontSize: 13, color: AppColors.inkSoft)),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildUserMessage(ChatMessage msg) {
    final hasImage = msg.imagePaths.isNotEmpty;
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.end,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Flexible(
            child: ConstrainedBox(
              constraints: BoxConstraints(
                maxWidth: MediaQuery.of(context).size.width * 0.78,
              ),
              child: Container(
                padding: EdgeInsets.fromLTRB(hasImage ? 3 : 15,
                    hasImage ? 3 : 12, 15, hasImage ? 3 : 12),
                decoration: BoxDecoration(
                  gradient: const LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [AppColors.userBubble, AppColors.userBubbleEnd],
                  ),
                  borderRadius: const BorderRadius.only(
                    topLeft: Radius.circular(18),
                    topRight: Radius.circular(18),
                    bottomLeft: Radius.circular(18),
                    bottomRight: Radius.circular(5),
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: AppColors.userBubble.withAlpha(40),
                      blurRadius: 8,
                      offset: const Offset(0, 2),
                    ),
                  ],
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    if (msg.text != null && msg.text!.isNotEmpty)
                      Padding(
                        padding: hasImage
                            ? const EdgeInsets.fromLTRB(9, 6, 9, 6)
                            : EdgeInsets.zero,
                        child: Text(msg.text!,
                            style: const TextStyle(
                                fontSize: 15,
                                height: 1.35,
                                color: Colors.white)),
                      ),
                    if (hasImage) ...[
                      ClipRRect(
                        borderRadius: BorderRadius.circular(14),
                        child: Image.file(
                          File(msg.imagePaths.first),
                          width: 130,
                          height: 130,
                          fit: BoxFit.cover,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildAssistantMessage(ChatMessage msg) {
    final reply = msg.agentReply;
    final showText = msg.text != null &&
        msg.text!.isNotEmpty &&
        !_hasProductGroupList(reply);
    return Padding(
      padding: const EdgeInsets.only(bottom: 10, left: 0, right: 8),
      child: Align(
        alignment: Alignment.centerLeft,
        child: ConstrainedBox(
          constraints: BoxConstraints(
            maxWidth: MediaQuery.of(context).size.width - 16,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (showText)
                Padding(
                  padding: const EdgeInsets.only(bottom: 6),
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 14, vertical: 10),
                    decoration: BoxDecoration(
                      color: AppColors.panel,
                      borderRadius: BorderRadius.circular(16),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withAlpha(6),
                          blurRadius: 4,
                          offset: const Offset(0, 1),
                        ),
                      ],
                    ),
                    child: Text(msg.text!,
                        style: const TextStyle(
                            fontSize: 14,
                            height: 1.45,
                            color: AppColors.inkBody)),
                  ),
                ),
              if (reply != null)
                ...reply.cards.map((card) => _buildCard(card, reply.cards)),
            ],
          ),
        ),
      ),
    );
  }

  bool _hasProductGroupList(AgentReply? reply) {
    if (reply == null) {
      return false;
    }
    return reply.cards.any((card) => card.cardType == 'product_group_list');
  }

  Widget _buildCard(ReplyCard card, List<ReplyCard> siblingCards) {
    switch (card.cardType) {
      case 'clarification':
        return _buildClarificationCard(card);
      case 'recommendation':
        return _buildRecommendationCard(card, _productsFromCards(siblingCards));
      case 'recognition':
        return _buildRecognitionCard(card);
      case 'product_list':
        return _buildProductListCard(card);
      case 'comparison':
        return _buildComparisonCard(card);
      case 'product_group_list':
        return _buildProductGroupListCard(card);
      default:
        return const SizedBox.shrink();
    }
  }

  List<ProductItem> _productsFromCards(List<ReplyCard> cards) {
    final products = <ProductItem>[];
    for (final card in cards) {
      final items = card.products;
      if (card.cardType == 'product_list' && items != null) {
        products.addAll(items);
      }
    }
    return products;
  }

  Widget _buildClarificationCard(ReplyCard card) {
    final options = card.options ?? [];
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.panel,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withAlpha(6),
            blurRadius: 6,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (card.title.isNotEmpty) ...[
            Text(card.title,
                style: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                    color: AppColors.inkBody)),
            const SizedBox(height: 10),
          ],
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: options.map((opt) {
              return ActionChip(
                label: Text(opt.label, style: const TextStyle(fontSize: 13)),
                onPressed: () => _onOptionSelected(opt.optionId),
                backgroundColor: AppColors.panelSoft,
                side: const BorderSide(color: AppColors.line),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(20),
                ),
                padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
              );
            }).toList(),
          ),
        ],
      ),
    );
  }

  Widget _buildRecommendationCard(ReplyCard card, List<ProductItem> products) {
    final reasons = _recommendationReasons(card);
    final risks = _recommendationRisks(card);
    final details = _recommendationDetails(card);
    final alternatives = _alternativeProducts(card, products);

    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.panel,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            const Icon(Icons.shopping_bag_outlined,
                size: 18, color: AppColors.accent),
            const SizedBox(width: 6),
            Text(card.title,
                style:
                    const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
            const Spacer(),
            if (card.decisionScore != null) _scoreBadge(card.decisionScore!),
          ]),
          const SizedBox(height: 8),
          if (card.productName != null)
            Text(card.productName!,
                style:
                    const TextStyle(fontSize: 15, fontWeight: FontWeight.w500)),
          const SizedBox(height: 4),
          if (card.platform != null || card.price != null)
            Row(children: [
              if (card.platform != null) _platformBadge(card.platform!),
              if (card.platform != null && card.price != null)
                const SizedBox(width: 8),
              if (card.price != null)
                Text('¥${card.price!.toStringAsFixed(0)}',
                    style: const TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w700,
                        color: AppColors.priceRed)),
            ]),
          if (reasons.isNotEmpty) ...[
            const SizedBox(height: 10),
            _briefInfoBlock(
              title: '推荐理由',
              lines: reasons,
              icon: Icons.check_circle_outline,
              color: AppColors.good,
            ),
          ],
          if (risks.isNotEmpty) ...[
            const SizedBox(height: 8),
            _briefInfoBlock(
              title: '注意事项',
              lines: risks,
              icon: Icons.error_outline,
              color: AppColors.warn,
            ),
          ],
          if (card.productName != null) ...[
            const SizedBox(height: 8),
            Row(children: [
              OutlinedButton.icon(
                onPressed: () => _addToFavorites(card),
                icon: const Icon(Icons.favorite_border, size: 14),
                label: const Text('收藏', style: TextStyle(fontSize: 12)),
                style: OutlinedButton.styleFrom(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  minimumSize: const Size(0, 28),
                ),
              ),
              const SizedBox(width: 8),
              OutlinedButton.icon(
                onPressed: () => _setPriceAlert(card),
                icon: const Icon(Icons.notifications_outlined, size: 14),
                label: const Text('价格提醒', style: TextStyle(fontSize: 12)),
                style: OutlinedButton.styleFrom(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  minimumSize: const Size(0, 28),
                ),
              ),
            ]),
          ],
          if (details.isNotEmpty) ...[
            const SizedBox(height: 10),
            _recommendationReasonExpansion(card, details),
          ],
          if (alternatives.isNotEmpty) ...[
            const SizedBox(height: 8),
            const Text('备选商品',
                style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
            const SizedBox(height: 4),
            ...alternatives.map(_alternativeProductRow),
          ],
        ],
      ),
    );
  }

  Widget _scoreBadge(int score) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: AppColors.panelSoft,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.line),
      ),
      child: Text('匹配度 $score',
          style: const TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w600,
              color: AppColors.inkSoft)),
    );
  }

  Widget _briefInfoBlock({
    required String title,
    required List<String> lines,
    required IconData icon,
    required Color color,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(title,
            style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
        const SizedBox(height: 4),
        ...lines.map((line) => Padding(
              padding: const EdgeInsets.only(bottom: 3),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Icon(icon, size: 13, color: color),
                  ),
                  const SizedBox(width: 5),
                  Expanded(
                    child: Text(line,
                        style: TextStyle(
                            fontSize: 11.5,
                            height: 1.35,
                            color: color == AppColors.warn
                                ? AppColors.warn
                                : AppColors.inkSoft)),
                  ),
                ],
              ),
            )),
      ],
    );
  }

  Widget _recommendationReasonExpansion(
      ReplyCard card, List<MapEntry<String, String>> details) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.panelSoft,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: AppColors.line),
      ),
      child: Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          tilePadding: const EdgeInsets.symmetric(horizontal: 10),
          childrenPadding: const EdgeInsets.fromLTRB(10, 0, 10, 8),
          shape: const Border(),
          collapsedShape: const Border(),
          title: const Text('为什么推荐它',
              style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
          subtitle: Text(_recommendationSummary(card),
              style: const TextStyle(
                  fontSize: 11, height: 1.35, color: AppColors.inkSoft)),
          children: details.map(_recommendationDetailRow).toList(),
        ),
      ),
    );
  }

  Widget _recommendationDetailRow(MapEntry<String, String> detail) {
    return Padding(
      padding: const EdgeInsets.only(top: 5),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 42,
            child: Text(detail.key,
                style: const TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                    color: AppColors.inkMain)),
          ),
          Expanded(
            child: Text(detail.value,
                style: const TextStyle(
                    fontSize: 11, height: 1.35, color: AppColors.inkSoft)),
          ),
        ],
      ),
    );
  }

  Widget _alternativeProductRow(AlternativeProductView item) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 7),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: AppColors.line)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Text(item.title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        fontSize: 12.5, fontWeight: FontWeight.w600)),
              ),
              const SizedBox(width: 8),
              Text(item.price,
                  style: const TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                      color: AppColors.priceRed)),
            ],
          ),
          const SizedBox(height: 3),
          Row(children: [
            _platformBadge(item.platform),
            const SizedBox(width: 6),
            Expanded(
              child: Text('优点：${item.strength}',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style:
                      const TextStyle(fontSize: 11, color: AppColors.inkSoft)),
            ),
          ]),
          const SizedBox(height: 2),
          Text('注意：${item.caution}',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 11, color: AppColors.inkSoft)),
        ],
      ),
    );
  }

  List<String> _recommendationReasons(ReplyCard card) {
    final lines = <String>[];
    final reason = _compactDecisionText(card.reason);
    if (reason != null) lines.add(reason);
    for (final evidence in card.evidence ?? const <RecommendationEvidence>[]) {
      final line = _compactDecisionText(evidence.content);
      if (line != null) lines.add(line);
    }
    if (lines.isEmpty) {
      for (final signal in card.decisionSignals ?? const <DecisionSignal>[]) {
        final line = _compactDecisionText(signal.explanation);
        if (line != null) lines.add(line);
      }
    }
    if (lines.isEmpty) lines.add('价格、评价和售后信息较均衡');
    return _uniqueLimited(lines, 3);
  }

  List<String> _recommendationRisks(ReplyCard card) {
    final lines = <String>[];
    for (final risk in card.risks ?? const <String>[]) {
      final line = _compactDecisionText(risk);
      if (line != null) lines.add(line);
    }
    return _uniqueLimited(lines, 2);
  }

  List<MapEntry<String, String>> _recommendationDetails(ReplyCard card) {
    final rows = <MapEntry<String, String>>[];
    for (final signal in card.decisionSignals ?? const <DecisionSignal>[]) {
      final detail = _compactDecisionText(signal.explanation, maxLength: 42);
      rows.add(
          MapEntry(_decisionSignalLabel(signal), detail ?? '${signal.score}分'));
    }
    if (rows.isEmpty) {
      for (final evidence
          in card.evidence ?? const <RecommendationEvidence>[]) {
        final detail = _compactDecisionText(evidence.content, maxLength: 42);
        if (detail != null) rows.add(MapEntry('参考', detail));
      }
    }
    return rows.take(5).toList();
  }

  String _recommendationSummary(ReplyCard card) {
    final reasons = _recommendationReasons(card);
    final risks = _recommendationRisks(card);
    if (reasons.isNotEmpty && risks.isNotEmpty) {
      return '${_stripEndPunctuation(reasons.first)}，${_stripEndPunctuation(risks.first)}。';
    }
    if (reasons.isNotEmpty) {
      return '${_stripEndPunctuation(reasons.first)}，下单前再核对规格和优惠。';
    }
    return '价格、评价和售后信息已按当前条件整理。';
  }

  List<AlternativeProductView> _alternativeProducts(
      ReplyCard card, List<ProductItem> products) {
    final analyses = card.productAnalyses ?? const <ProductAnalysis>[];
    final items = <AlternativeProductView>[];
    for (final analysis in analyses.take(3)) {
      final product = _productForAnalysis(analysis, products);
      final title = product != null
          ? _displayProductTitle(product)
          : _cleanProductTitle(analysis.title);
      final platform = product?.platform ?? analysis.platform;
      final price = product != null
          ? '¥${product.price.toStringAsFixed(0)}'
          : (card.productName == analysis.title && card.price != null
              ? '¥${card.price!.toStringAsFixed(0)}'
              : '价格见列表');
      final strength = _compactDecisionText(
              analysis.strengths.isNotEmpty
                  ? analysis.strengths.first
                  : (product?.reasons.isNotEmpty == true
                      ? product!.reasons.first
                      : '价格和评价较均衡'),
              maxLength: 24) ??
          '价格和评价较均衡';
      final caution = _compactDecisionText(
              analysis.weaknesses.isNotEmpty
                  ? analysis.weaknesses.first
                  : _defaultProductCaution(product),
              maxLength: 24) ??
          '购买前核对规格';
      items.add(AlternativeProductView(
        title: title,
        platform: platform,
        price: price,
        strength: strength,
        caution: caution,
      ));
    }
    return items;
  }

  ProductItem? _productForAnalysis(
      ProductAnalysis analysis, List<ProductItem> products) {
    for (final product in products) {
      if (product.productId == analysis.productId) return product;
    }
    return null;
  }

  String _decisionSignalLabel(DecisionSignal signal) {
    final text = '${signal.key}${signal.label}';
    if (text.contains('price') || text.contains('价格')) return '价格';
    if (text.contains('rating') ||
        text.contains('review') ||
        text.contains('评分') ||
        text.contains('评价')) {
      return '评价';
    }
    if (text.contains('store') ||
        text.contains('shop') ||
        text.contains('店') ||
        text.contains('售后')) {
      return '售后';
    }
    if (text.contains('risk') || text.contains('风险')) return '风险';
    if (text.contains('platform') || text.contains('渠道')) return '平台';
    return signal.label;
  }

  String? _compactDecisionText(String? value, {int maxLength = 36}) {
    final raw = value?.trim();
    if (raw == null || raw.isEmpty) return null;
    var text = raw
        .replaceAll('\n', ' ')
        .replaceAll('整体决策得分', '')
        .replaceAll('模型判断', '')
        .replaceAll('综合排序策略', '')
        .replaceAll('AI', '')
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
    if (text.isEmpty) return null;
    if (text.length > maxLength) {
      text = '${text.substring(0, maxLength)}...';
    }
    return text;
  }

  String _stripEndPunctuation(String value) {
    return value.replaceAll(RegExp(r'[。！？；,.!?\s]+$'), '');
  }

  List<String> _uniqueLimited(List<String> values, int limit) {
    final seen = <String>{};
    final result = <String>[];
    for (final value in values) {
      if (seen.add(value)) result.add(value);
      if (result.length >= limit) break;
    }
    return result;
  }

  String _cleanProductTitle(String title) {
    return title
        .replaceAll('爆款', '')
        .replaceAll('高性价比', '')
        .replaceAll('专业级', '')
        .replaceAll('高音质', '')
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
  }

  String _defaultProductCaution(ProductItem? product) {
    if (product == null) return '购买前核对规格';
    if (product.platform == '拼多多-mock') return '注意店铺售后规则';
    if (product.priceHistory.isEmpty) return '暂无历史价参考';
    return '下单前确认优惠有效';
  }

  Widget _buildRecognitionCard(ReplyCard card) {
    final imagePath = _recognitionImagePath(card.imageId);
    final box = Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.panel,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.accent.withAlpha(60)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _recognitionThumb(imagePath),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('识别到：${card.category ?? "未知商品"}',
                        style: const TextStyle(
                            fontSize: 15,
                            height: 1.3,
                            fontWeight: FontWeight.w700)),
                    const SizedBox(height: 6),
                    Wrap(
                      spacing: 6,
                      runSpacing: 6,
                      children: [
                        _recognitionInfoBadge(_confidenceText(card)),
                        _recognitionInfoBadge('来源：${card.aiProvider ?? "未知"}'),
                      ],
                    ),
                    if (card.fallbackUsed == true) ...[
                      const SizedBox(height: 6),
                      const Text('已回退到 Mock 识别',
                          style:
                              TextStyle(fontSize: 11, color: AppColors.warn)),
                    ],
                  ],
                ),
              ),
            ],
          ),
          if (card.explanation != null && card.explanation!.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 10),
              child: Text(card.explanation!,
                  style:
                      const TextStyle(fontSize: 11, color: AppColors.inkSoft)),
            ),
          const SizedBox(height: 10),
          Row(
            children: [
              const Text('可修正字段',
                  style: TextStyle(
                      fontSize: 12,
                      color: AppColors.inkSoft,
                      fontWeight: FontWeight.w600)),
              const Spacer(),
              TextButton.icon(
                onPressed: () => _openCorrectionSheet(card),
                icon: const Icon(Icons.edit, size: 14),
                label: const Text('修正', style: TextStyle(fontSize: 12)),
                style: TextButton.styleFrom(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  minimumSize: const Size(0, 28),
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: _recognitionEditableFields(card)
                .map((field) => _recognitionFieldChip(
                      field.key,
                      field.value,
                      card,
                    ))
                .toList(),
          ),
        ],
      ),
    );
    return Material(
      color: Colors.transparent,
      child: InkWell(
        key: const Key('recognition_card_box'),
        onTap: () => _openCorrectionSheet(card),
        borderRadius: BorderRadius.circular(8),
        child: box,
      ),
    );
  }

  String? _recognitionImagePath(String? imageId) {
    if (imageId == null || imageId.isEmpty) return null;
    final messages = ref.watch(chatControllerProvider).messages;
    for (final msg in messages) {
      for (var i = 0; i < msg.imageIds.length; i++) {
        if (msg.imageIds[i] == imageId && i < msg.imagePaths.length) {
          return msg.imagePaths[i];
        }
      }
    }
    return null;
  }

  Widget _recognitionThumb(String? imagePath) {
    if (imagePath != null && File(imagePath).existsSync()) {
      return ClipRRect(
        borderRadius: BorderRadius.circular(6),
        child: Image.file(
          File(imagePath),
          key: const Key('recognition_image_thumb'),
          width: 82,
          height: 82,
          fit: BoxFit.cover,
          errorBuilder: (_, __, ___) => _recognitionThumbPlaceholder(),
        ),
      );
    }
    return _recognitionThumbPlaceholder();
  }

  Widget _recognitionThumbPlaceholder() {
    return Container(
      key: const Key('recognition_image_placeholder'),
      width: 82,
      height: 82,
      decoration: BoxDecoration(
        color: AppColors.panelSoft,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: AppColors.line),
      ),
      child: const Center(
        child: Icon(Icons.image_search, size: 28, color: AppColors.inkSoft),
      ),
    );
  }

  Widget _recognitionInfoBadge(String label) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 4),
      decoration: BoxDecoration(
        color: AppColors.panelSoft,
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: AppColors.line),
      ),
      child: Text(label,
          style: const TextStyle(fontSize: 11, color: AppColors.inkSoft)),
    );
  }

  String _confidenceText(ReplyCard card) {
    if (card.confidence == null) return '置信度 --';
    return '置信度 ${(card.confidence! * 100).toStringAsFixed(0)}%';
  }

  List<MapEntry<String, String>> _recognitionEditableFields(ReplyCard card) {
    final fields = <MapEntry<String, String>>[
      MapEntry('类别', card.category ?? '未识别'),
      MapEntry('品牌', card.brand ?? '未识别'),
      MapEntry('型号', card.model ?? '未识别'),
    ];
    final attrs = card.attributes ?? {};
    const attrLabels = <String, String>{
      'color': '颜色',
      'style': '风格',
      'scenario': '场景',
      'keySpecs': '规格',
      'subCategory': '细分品类',
    };
    for (final entry in attrLabels.entries) {
      final value = attrs[entry.key];
      if (value != null && value.toString().trim().isNotEmpty) {
        fields.add(MapEntry(entry.value, value.toString()));
      }
    }
    return fields;
  }

  Widget _recognitionFieldChip(
      String label, String value, ReplyCard recognitionCard) {
    return ActionChip(
      onPressed: () => _openCorrectionSheet(recognitionCard),
      label: Text('$label：$value', style: const TextStyle(fontSize: 12)),
      backgroundColor: AppColors.panelSoft,
      side: const BorderSide(color: AppColors.line),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
      visualDensity: VisualDensity.compact,
      materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
    );
  }

  // ── Product cards ──────────────────────────────────────────

  Widget _buildProductListCard(ReplyCard card) {
    final products = card.products ?? [];
    final sourceLine = _resultSourceLine(products);
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(_resultTitle(products.length),
              style:
                  const TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
          const SizedBox(height: 4),
          Text(sourceLine,
              style: const TextStyle(
                  fontSize: 12, height: 1.35, color: AppColors.inkSoft)),
          const SizedBox(height: 10),
          _buildFilterBar(card, products),
          const SizedBox(height: 10),
          if (products.isEmpty)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: AppColors.panel,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: AppColors.line),
              ),
              child: const Text('暂无符合条件的商品',
                  style: TextStyle(fontSize: 13, color: AppColors.inkSoft)),
            )
          else
            ...products.map((p) => _buildProductRow(p)),
        ],
      ),
    );
  }

  Widget _buildProductRow(ProductItem p) {
    final isFavorite = _favoriteProductIds.contains(p.productId);
    return Container(
      margin: const EdgeInsets.only(bottom: 1),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 12),
      decoration: const BoxDecoration(
        color: AppColors.panel,
        border: Border(bottom: BorderSide(color: AppColors.line)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _productThumb(p),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(_displayProductTitle(p),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        fontSize: 14,
                        height: 1.35,
                        fontWeight: FontWeight.w600)),
                const SizedBox(height: 5),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text('¥${p.price.toStringAsFixed(0)}',
                        style: const TextStyle(
                            fontSize: 18,
                            height: 1,
                            fontWeight: FontWeight.w700,
                            color: AppColors.priceRed)),
                    if (p.originalPrice > p.price) ...[
                      const SizedBox(width: 5),
                      Padding(
                        padding: const EdgeInsets.only(bottom: 1),
                        child: Text('¥${p.originalPrice.toStringAsFixed(0)}',
                            style: const TextStyle(
                                fontSize: 11,
                                color: AppColors.inkSoft,
                                decoration: TextDecoration.lineThrough)),
                      ),
                    ],
                  ],
                ),
                const SizedBox(height: 5),
                Text(_shopLine(p),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        fontSize: 12, color: AppColors.inkSoft)),
                const SizedBox(height: 5),
                Text(_trustLine(p),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        fontSize: 11, color: AppColors.inkSoft)),
                const SizedBox(height: 6),
                Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  children: _decisionTags(p).map(_tagBadge).toList(),
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    TextButton(
                      key: Key('go_${p.productId}'),
                      onPressed: () => _showProductJumpSheet(p),
                      style: _productActionStyle(primary: true),
                      child: const Text('去看看', style: TextStyle(fontSize: 11)),
                    ),
                    const SizedBox(width: 8),
                    TextButton.icon(
                      key: Key('favorite_${p.productId}'),
                      onPressed: () => _addProductToFavorites(p),
                      style: _productActionStyle(selected: isFavorite),
                      icon: Icon(
                        isFavorite ? Icons.favorite : Icons.favorite_border,
                        size: 13,
                      ),
                      label: Text(isFavorite ? '已收藏' : '收藏',
                          style: const TextStyle(fontSize: 11)),
                    ),
                    const SizedBox(width: 8),
                    TextButton(
                      onPressed: () {},
                      style: _productActionStyle(),
                      child: const Text('比价详情', style: TextStyle(fontSize: 11)),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  ButtonStyle _productActionStyle(
      {bool primary = false, bool selected = false}) {
    final color = selected
        ? AppColors.priceRed
        : (primary ? AppColors.accent : AppColors.inkSoft);
    return TextButton.styleFrom(
      padding: const EdgeInsets.symmetric(horizontal: 8),
      minimumSize: const Size(0, 28),
      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
      foregroundColor: color,
      backgroundColor:
          primary ? AppColors.accent.withAlpha(12) : AppColors.panelSoft,
      side: BorderSide(
          color: selected
              ? AppColors.priceRed.withAlpha(80)
              : (primary ? AppColors.accent.withAlpha(50) : AppColors.line)),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
    );
  }

  String _resultTitle(int count) {
    if (count <= 0) return '没有找到合适商品';
    return '找到 $count 个相关商品';
  }

  String _resultSourceLine(List<ProductItem> products) {
    if (products.isEmpty) return '可以放宽预算、颜色或平台后再试一次';
    final platforms = <String>{};
    for (final product in products) {
      platforms.add(_platformLabel(product.platform));
    }
    final names = platforms.take(3).join('、');
    return '已按价格和评价综合排序，以下结果来自$names等平台';
  }

  Widget _buildFilterBar(ReplyCard card, List<ProductItem> products) {
    final chips = _filterChips(card, products);
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        children: chips
            .map((label) => Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: _filterChip(label),
                ))
            .toList(),
      ),
    );
  }

  List<String> _filterChips(ReplyCard card, List<ProductItem> products) {
    String? category;
    String? color;
    String? budget;
    String? brand;
    String? platform;
    String? sort;
    final prefs = <String>[];

    for (final raw in card.filterSummary) {
      if (raw.startsWith('品类：')) {
        category = raw.substring('品类：'.length);
      } else if (raw.startsWith('颜色：')) {
        color = raw.substring('颜色：'.length);
      } else if (raw.startsWith('预算≤')) {
        final amount = raw.substring('预算≤'.length).replaceAll('元', '').trim();
        if (amount.isNotEmpty) budget = '¥$amount以内';
      } else if (raw.startsWith('品牌：')) {
        brand = raw.substring('品牌：'.length);
      } else if (raw.startsWith('平台：')) {
        platform = raw.substring('平台：'.length);
      } else if (raw.startsWith('排序：')) {
        sort = raw.substring('排序：'.length);
      } else if (raw.startsWith('偏好：')) {
        prefs.addAll(raw.substring('偏好：'.length).split('、'));
      }
    }

    final chips = <String>[];
    if (category != null && color != null) {
      chips.add('$color$category');
    } else if (category != null) {
      chips.add(category);
    } else if (color != null) {
      chips.add(color);
    }
    if (budget != null) chips.add(budget);
    if (brand != null) chips.add(brand);
    chips.add(platform ?? '全部平台');
    chips.add(_sortChip(sort));

    for (final pref in prefs) {
      if (pref.contains('官方') || pref.contains('自营')) {
        chips.add('自营');
      } else if (pref.contains('配送')) {
        chips.add('配送更快');
      } else if (pref.contains('低价')) {
        chips.add('价格优先');
      }
    }
    return chips.take(6).toList();
  }

  String _sortChip(String? sort) {
    if (sort == null || sort.trim().isEmpty) return '综合排序';
    if (sort.contains('价格')) return '价格优先';
    if (sort.contains('销量')) return '销量优先';
    if (sort.contains('评分')) return '评价优先';
    return sort;
  }

  Widget _filterChip(String label) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: AppColors.panel,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.line),
      ),
      child: Text(label,
          style: const TextStyle(fontSize: 12, color: AppColors.inkMain)),
    );
  }

  Widget _productThumb(ProductItem product) {
    final imageUrl = product.imageUrl.trim();
    if (imageUrl.startsWith('http://') || imageUrl.startsWith('https://')) {
      return ClipRRect(
        borderRadius: BorderRadius.circular(6),
        child: Image.network(
          imageUrl,
          width: 88,
          height: 88,
          fit: BoxFit.cover,
          errorBuilder: (_, __, ___) => _productThumbPlaceholder(product),
        ),
      );
    }
    return _productThumbPlaceholder(product);
  }

  Widget _productThumbPlaceholder(ProductItem product) {
    final accent = _thumbAccent(product);
    return Container(
      key: Key('product_thumb_${product.productId}'),
      width: 88,
      height: 88,
      decoration: BoxDecoration(
        color: _thumbSurface(product),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: AppColors.line),
      ),
      child: Stack(
        children: [
          Positioned.fill(
            child: CustomPaint(
              painter: ProductThumbPainter(
                icon: _productIcon(product),
                accent: accent,
                lineColor: AppColors.inkSoft.withAlpha(80),
                text: '${product.title}${product.tags.join()}',
              ),
            ),
          ),
          Positioned(
            left: 6,
            top: 6,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
              decoration: BoxDecoration(
                color: Colors.white.withAlpha(215),
                borderRadius: BorderRadius.circular(4),
                border: Border.all(color: AppColors.line),
              ),
              child: Text(_thumbBrand(product),
                  style: TextStyle(
                      fontSize: 9, fontWeight: FontWeight.w600, color: accent)),
            ),
          ),
          Positioned(
            left: 6,
            bottom: 6,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
              decoration: BoxDecoration(
                color: Colors.white.withAlpha(230),
                borderRadius: BorderRadius.circular(4),
                border: Border.all(color: AppColors.line),
              ),
              child: Text(_platformLabel(product.platform),
                  style:
                      const TextStyle(fontSize: 10, color: AppColors.inkSoft)),
            ),
          ),
        ],
      ),
    );
  }

  Color _thumbSurface(ProductItem product) {
    return switch (product.platform) {
      '京东-mock' => const Color(0xFFF8F3F4),
      '拼多多-mock' => const Color(0xFFFFF4EE),
      '淘宝-mock' => const Color(0xFFF7F5EF),
      _ => AppColors.panelSoft,
    };
  }

  Color _thumbAccent(ProductItem product) {
    final text = '${product.title}${product.tags.join()}';
    if (text.contains('黑色')) return const Color(0xFF2F343B);
    if (text.contains('白色')) return const Color(0xFF8A8F98);
    if (product.platform == '京东-mock') return const Color(0xFFB23A48);
    if (product.platform == '拼多多-mock') return const Color(0xFFE36A3D);
    if (product.platform == '淘宝-mock') return const Color(0xFFC27A2C);
    return AppColors.accent;
  }

  String _thumbBrand(ProductItem product) {
    final brand = product.brand?.trim();
    if (brand != null && brand.isNotEmpty) return brand;
    final title = _displayProductTitle(product);
    if (title.contains('索尼')) return 'SONY';
    if (title.contains('小米')) return 'MI';
    if (title.contains('华为')) return 'HUAWEI';
    if (title.contains('森海塞尔')) return 'SENN';
    return '商品';
  }

  IconData _productIcon(ProductItem product) {
    final text = '${product.title}${product.tags.join()}';
    if (text.contains('耳机')) return Icons.headphones;
    if (text.contains('鞋')) return Icons.directions_run;
    if (text.contains('吹风机')) return Icons.air;
    if (text.contains('背包') || text.contains('双肩')) return Icons.backpack;
    if (text.contains('手表')) return Icons.watch;
    return Icons.shopping_bag_outlined;
  }

  String _displayProductTitle(ProductItem product) {
    final mapped = switch (product.productId) {
      'jd-101' => '索尼无线降噪耳机 黑色款',
      'jd-102' => '小米入耳式无线耳机 长续航版',
      'jd-103' => '索尼头戴式降噪耳机 黑色',
      'jd-104' => '华为运动蓝牙耳机 防水款',
      'pdd-101' => '黑色蓝牙耳机 基础款',
      'pdd-102' => '小米运动无线耳机 白色',
      'pdd-103' => '头戴式游戏耳机 黑色',
      'pdd-104' => '长续航降噪蓝牙耳机 白色',
      'tb-101' => '森海塞尔无线降噪耳机 黑色',
      'tb-102' => '复古头戴式蓝牙耳机 黑色',
      'tb-103' => '森海塞尔入耳式 HiFi 耳机',
      'tb-104' => '华为运动防水蓝牙耳机',
      _ => null,
    };
    if (mapped != null) return mapped;
    return product.title
        .replaceAll('爆款', '')
        .replaceAll('高性价比', '')
        .replaceAll('专业级', '')
        .replaceAll('高音质', '')
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
  }

  String _shopLine(ProductItem product) {
    return '${_platformLabel(product.platform)} · ${product.shopName}';
  }

  String _trustLine(ProductItem product) {
    return '${product.rating.toStringAsFixed(1)}分 · ${_reviewCount(product)}条评价 · ${_shippingText(product)} · ${_afterSaleText(product)}';
  }

  String _reviewCount(ProductItem product) {
    final reviews = (product.sales * 0.18).round().clamp(12, product.sales);
    return _formatCount(reviews);
  }

  String _formatCount(int value) {
    if (value >= 10000) return '${(value / 10000).toStringAsFixed(1)}万';
    return value.toString();
  }

  String _shippingText(ProductItem product) {
    return switch (product.platform) {
      '京东-mock' => '京仓发货',
      '拼多多-mock' => '包邮',
      '淘宝-mock' => '浙江发货',
      _ => '平台发货',
    };
  }

  String _afterSaleText(ProductItem product) {
    final tags = product.tags.join();
    if (tags.contains('自营') || tags.contains('官方')) return '官方售后';
    return '7天无理由';
  }

  List<String> _decisionTags(ProductItem product) {
    final tags = <String>[];
    final priceNote = _priceNote(product);
    if (priceNote != null && priceNote != '暂无历史价' && priceNote != '价格稳定') {
      tags.add(priceNote);
    }
    if (_afterSaleText(product) == '官方售后') {
      tags.add('自营/官方');
    } else if (_shippingText(product) == '包邮') {
      tags.add('包邮');
    }
    if (product.originalPrice > product.price && tags.length < 3) {
      tags.add('券后价');
    }
    return tags.take(3).toList();
  }

  String? _priceNote(ProductItem product) {
    final history = product.priceHistory;
    if (history.length < 2) return '暂无历史价';
    final current = product.price;
    final min = history.reduce((a, b) => a < b ? a : b);
    final avg = history.reduce((a, b) => a + b) / history.length;
    if ((current - min).abs() < 0.01) return '近30天低价';
    final diff = ((avg - current) / avg * 100).round();
    if (diff >= 8 && diff <= 25) return '比均价低$diff%';
    if (diff > 25) return '低于近期均价';
    return '价格稳定';
  }

  Widget _tagBadge(String label) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
      decoration: BoxDecoration(
        color: AppColors.panelSoft,
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: AppColors.line),
      ),
      child: Text(label,
          style: const TextStyle(fontSize: 11, color: AppColors.inkSoft)),
    );
  }

  Widget _buildComparisonCard(ReplyCard card) {
    final stats = card.platformStats ?? {};
    final lowestValues = <double>[];
    for (final entry in stats.entries) {
      final value = entry.value;
      if (value is Map<String, dynamic>) {
        final lowest = (value['lowestPrice'] as num?)?.toDouble();
        if (lowest != null) lowestValues.add(lowest);
      }
    }
    final minLowest = lowestValues.isEmpty
        ? null
        : lowestValues.reduce((a, b) => a < b ? a : b);
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.panel,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            const Icon(Icons.compare_arrows, size: 18, color: AppColors.accent),
            const SizedBox(width: 6),
            Text(card.title,
                style:
                    const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
          ]),
          if (stats.isNotEmpty) ...[
            const SizedBox(height: 2),
            const Text('各平台价格概览',
                style: TextStyle(fontSize: 11, color: AppColors.inkSoft)),
          ],
          const SizedBox(height: 8),
          if (stats.isEmpty)
            const Text('暂无可比价平台',
                style: TextStyle(fontSize: 12, color: AppColors.inkSoft))
          else
            ...stats.entries.map((e) {
              final s = e.value as Map<String, dynamic>;
              final platform = s['platform'] as String? ?? e.key;
              final lowestValue = (s['lowestPrice'] as num?)?.toDouble();
              final lowest = lowestValue?.toStringAsFixed(0) ?? '-';
              final avgValue = (s['averagePrice'] as num?)?.toDouble();
              final avg = avgValue?.toStringAsFixed(0);
              final count = s['productCount'] ?? 0;
              final highlight = (s['highlight'] as String?)?.trim();
              final isLowest = minLowest != null &&
                  lowestValue != null &&
                  lowestValue == minLowest;
              final isStable = _isStablePlatform(platform, highlight);
              return Container(
                padding: const EdgeInsets.symmetric(vertical: 8),
                decoration: const BoxDecoration(
                  border: Border(bottom: BorderSide(color: AppColors.line)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      _platformBadge(platform),
                      if (isLowest) ...[
                        const SizedBox(width: 6),
                        _platformMarker('最低价平台', AppColors.priceRed),
                      ],
                      if (isStable) ...[
                        const SizedBox(width: 6),
                        _platformMarker('更稳妥平台', AppColors.accent),
                      ],
                      const Spacer(),
                      Text('最低 ¥$lowest',
                          style: const TextStyle(
                              fontSize: 13,
                              fontWeight: FontWeight.w600,
                              color: AppColors.priceRed)),
                    ]),
                    const SizedBox(height: 3),
                    Text('${avg != null ? '均价 ¥$avg' : '暂无均价'} · $count件',
                        style: const TextStyle(
                            fontSize: 11, color: AppColors.inkSoft)),
                    if (highlight != null && highlight.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 2),
                        child: Text(_compactPlatformHighlight(highlight),
                            style: const TextStyle(
                                fontSize: 11, color: AppColors.inkSoft)),
                      ),
                  ],
                ),
              );
            }),
        ],
      ),
    );
  }

  Widget _platformMarker(String label, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
      decoration: BoxDecoration(
        color: color.withAlpha(14),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: color.withAlpha(50)),
      ),
      child: Text(label,
          style: TextStyle(
              fontSize: 9, fontWeight: FontWeight.w600, color: color)),
    );
  }

  bool _isStablePlatform(String platform, String? highlight) {
    if (platform == '京东-mock') return true;
    final text = highlight ?? '';
    return text.contains('自营') || text.contains('售后') || text.contains('保障');
  }

  String _compactPlatformHighlight(String value) {
    if (value.length <= 26) return value;
    return '${value.substring(0, 26)}...';
  }

  Widget _platformBadge(String platform) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
      decoration: BoxDecoration(
          color: AppColors.panelSoft,
          borderRadius: BorderRadius.circular(4),
          border: Border.all(color: AppColors.line)),
      child: Text(_platformLabel(platform),
          style: const TextStyle(fontSize: 11, color: AppColors.inkSoft)),
    );
  }

  // ── Product group list card ────────────────────────────────

  Widget _buildProductGroupListCard(ReplyCard card) {
    final groups = card.groups ?? [];
    final emptyReason = card.emptyReason;
    final showRecognitionBox = _hasRecognitionMeta(card);

    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (showRecognitionBox) ...[
            _buildRecognitionResultBox(card),
            const SizedBox(height: 10),
          ],
          _buildProductResultHeader(card, groups),
          if (card.filterSummary.isNotEmpty) ...[
            const SizedBox(height: 8),
            _buildEditableFilterSummary(card),
          ],
          const SizedBox(height: 8),
          if (groups.isEmpty && emptyReason != null)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: AppColors.panel,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: AppColors.line),
              ),
              child: Row(
                children: [
                  const Icon(Icons.info_outline,
                      size: 16, color: AppColors.inkSoft),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(emptyReason,
                        style: const TextStyle(
                            fontSize: 13, color: AppColors.inkSoft)),
                  ),
                ],
              ),
            )
          else
            ...groups.map((g) => _buildGroupRow(g)),
        ],
      ),
    );
  }

  Widget _buildProductResultHeader(ReplyCard card, List<ProductGroup> groups) {
    final title = groups.isEmpty ? '暂未找到商品' : '找到 ${groups.length} 组商品';
    return Row(
      children: [
        const Icon(Icons.category_outlined, size: 17, color: AppColors.accent),
        const SizedBox(width: 6),
        Text(title,
            style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
        const Spacer(),
        if (card.emptyReason == null && groups.isNotEmpty)
          Text('可继续筛选',
              style: const TextStyle(fontSize: 12, color: AppColors.inkSoft)),
      ],
    );
  }

  Widget _buildEditableFilterSummary(ReplyCard card) {
    final key = _filterEditorKey(card);
    final editing = _editingFilterKeys.contains(key);
    final originalText = _editableFilterText(card);
    final draft = _filterDrafts[key] ?? originalText;
    final changed = draft.trim().isNotEmpty && draft.trim() != originalText;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: AppColors.panel,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.tune, size: 15, color: AppColors.accent),
              const SizedBox(width: 5),
              const Text('本轮筛选',
                  style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                      color: AppColors.inkBody)),
              const Spacer(),
              TextButton.icon(
                onPressed: () {
                  setState(() {
                    if (editing) {
                      _editingFilterKeys.remove(key);
                      _filterDrafts.remove(key);
                    } else {
                      _editingFilterKeys.add(key);
                      _filterDrafts[key] = originalText;
                    }
                  });
                },
                icon: Icon(editing ? Icons.close : Icons.edit, size: 14),
                label: Text(editing ? '取消' : '修改'),
                style: TextButton.styleFrom(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  minimumSize: const Size(0, 28),
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          if (!editing)
            _buildFilterBar(card, [])
          else ...[
            TextFormField(
              key: Key('filter_editor_$key'),
              initialValue: draft,
              minLines: 1,
              maxLines: 2,
              decoration: const InputDecoration(
                hintText: '例如：索尼黑色耳机 300以内 只看京东 评分4.8以上',
                isDense: true,
                contentPadding:
                    EdgeInsets.symmetric(horizontal: 10, vertical: 9),
              ),
              style: const TextStyle(fontSize: 13),
              onChanged: (value) {
                setState(() {
                  _filterDrafts[key] = value;
                });
              },
              onFieldSubmitted: (_) {
                if (changed) {
                  _submitFilterEdit(key);
                }
              },
            ),
            if (changed) ...[
              const SizedBox(height: 8),
              Align(
                alignment: Alignment.centerRight,
                child: ElevatedButton.icon(
                  key: Key('filter_submit_$key'),
                  onPressed: () => _submitFilterEdit(key),
                  icon: const Icon(Icons.send, size: 14),
                  label: const Text('提交修改'),
                  style: ElevatedButton.styleFrom(
                    minimumSize: const Size(0, 34),
                    padding:
                        const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                    textStyle: const TextStyle(
                        fontSize: 12, fontWeight: FontWeight.w600),
                  ),
                ),
              ),
            ],
          ],
        ],
      ),
    );
  }

  String _filterEditorKey(ReplyCard card) {
    final groupKey =
        (card.groups ?? []).map((group) => group.groupId).take(3).join('|');
    return '${card.filterSummary.join('|')}::$groupKey';
  }

  String _editableFilterText(ReplyCard card) {
    final parts = <String>[];
    for (final raw in card.filterSummary) {
      final value = raw.trim();
      if (value.startsWith('品类：')) {
        parts.add(value.substring('品类：'.length));
      } else if (value.startsWith('颜色：')) {
        parts.add(value.substring('颜色：'.length));
      } else if (value.startsWith('预算≤')) {
        final amount = value.substring('预算≤'.length).replaceAll('元', '').trim();
        if (amount.isNotEmpty) parts.add('$amount以内');
      } else if (value.startsWith('品牌：')) {
        parts.add(value.substring('品牌：'.length));
      } else if (value.startsWith('平台：')) {
        parts.add('只看${value.substring('平台：'.length)}');
      } else if (value.startsWith('排序：')) {
        parts.add(value.substring('排序：'.length));
      } else if (value.startsWith('偏好：')) {
        parts.add(value.substring('偏好：'.length).replaceAll('、', ' '));
      }
    }
    return parts.where((part) => part.trim().isNotEmpty).join(' ');
  }

  void _submitFilterEdit(String key) {
    final text = _filterDrafts[key]?.trim() ?? '';
    if (text.isEmpty) {
      return;
    }
    setState(() {
      _editingFilterKeys.remove(key);
    });
    ref
        .read(chatControllerProvider.notifier)
        .sendTextMessage(text, profile: _profileForRequest());
    _scrollToBottom();
  }

  bool _hasRecognitionMeta(ReplyCard card) {
    return (card.imageId != null && card.imageId!.isNotEmpty) ||
        (card.recognitionId != null && card.recognitionId!.isNotEmpty) ||
        (card.category != null && card.category!.isNotEmpty) ||
        (card.brand != null && card.brand!.isNotEmpty) ||
        (card.model != null && card.model!.isNotEmpty);
  }

  Widget _buildRecognitionResultBox(ReplyCard card) {
    final imagePath = _recognitionImagePath(card.imageId);
    final hasCorrection =
        card.recognitionId != null && card.recognitionId!.isNotEmpty;
    final badges = <Widget>[
      _recognitionInfoBadge(_confidenceText(card)),
    ];
    if (card.brand != null && card.brand!.isNotEmpty) {
      badges.add(_recognitionInfoBadge('品牌：${card.brand}'));
    }
    if (card.model != null && card.model!.isNotEmpty) {
      badges.add(_recognitionInfoBadge('型号：${card.model}'));
    }
    if (card.aiProvider != null && card.aiProvider!.isNotEmpty) {
      badges.add(_recognitionInfoBadge('来源：${card.aiProvider}'));
    }

    final box = Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.panel,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.accent.withAlpha(60)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _recognitionThumb(imagePath),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    const Icon(Icons.image_search,
                        size: 15, color: AppColors.accent),
                    const SizedBox(width: 5),
                    const Text('识别结果',
                        style: TextStyle(
                            fontSize: 12,
                            color: AppColors.inkSoft,
                            fontWeight: FontWeight.w600)),
                    const Spacer(),
                    if (hasCorrection)
                      const Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.edit, size: 14, color: AppColors.accent),
                          SizedBox(width: 4),
                          Text('修正',
                              style: TextStyle(
                                  fontSize: 12,
                                  color: AppColors.accent,
                                  fontWeight: FontWeight.w600)),
                        ],
                      ),
                  ],
                ),
                const SizedBox(height: 4),
                Text('识别到：${card.category ?? "未知商品"}',
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        fontSize: 15,
                        height: 1.3,
                        fontWeight: FontWeight.w700)),
                const SizedBox(height: 7),
                Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  children: badges,
                ),
                if (hasCorrection) ...[
                  const SizedBox(height: 6),
                  const Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.touch_app, size: 13, color: AppColors.inkSoft),
                      SizedBox(width: 4),
                      Text('点击查看/修改识别信息',
                          style: TextStyle(
                              fontSize: 11, color: AppColors.inkSoft)),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Container(
                    key: const Key('recognition_result_action_button'),
                    width: double.infinity,
                    padding: const EdgeInsets.symmetric(vertical: 9),
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: AppColors.lineStrong),
                    ),
                    child: const Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(Icons.open_in_new,
                            size: 15, color: AppColors.inkBody),
                        SizedBox(width: 8),
                        Text('查看/修改识别结果',
                            style: TextStyle(
                                fontSize: 13,
                                color: AppColors.inkBody,
                                fontWeight: FontWeight.w600)),
                      ],
                    ),
                  ),
                ],
                if (card.fallbackUsed == true) ...[
                  const SizedBox(height: 6),
                  const Text('已回退到 Mock 识别',
                      style: TextStyle(fontSize: 11, color: AppColors.warn)),
                ],
                if (card.explanation != null && card.explanation!.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text(card.explanation!,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                            fontSize: 11, color: AppColors.inkSoft)),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
    return Semantics(
      button: true,
      label: hasCorrection ? '查看并修改识别结果' : '查看识别结果',
      child: GestureDetector(
        key: const Key('recognition_result_box'),
        behavior: HitTestBehavior.opaque,
        onTap: () => _openCorrectionSheet(card),
        child: box,
      ),
    );
  }

  Widget _buildGroupRow(ProductGroup group) {
    // Find cheapest platform and build price summary for others
    final platforms = group.platforms;
    PlatformOfferSummary? cheapest;
    double minPrice = double.infinity;
    for (final p in platforms) {
      if (p.price < minPrice) {
        minPrice = p.price;
        cheapest = p;
      }
    }
    // Other platform prices (distinct platforms, not the cheapest one)
    final otherPrices = <String, double>{};
    for (final p in platforms) {
      if (p.platform != (cheapest?.platform ?? '')) {
        final existing = otherPrices[p.platform];
        if (existing == null || p.price < existing) {
          otherPrices[p.platform] = p.price;
        }
      }
    }
    // Top rating
    final topRating =
        platforms.map((p) => p.rating).reduce((a, b) => a > b ? a : b);
    final totalReviews =
        platforms.map((p) => p.sales).fold<int>(0, (a, b) => a + b);
    final bestOffer = cheapest;
    final isFavorite =
        bestOffer != null && _favoriteProductIds.contains(bestOffer.productId);

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () {
          ref.read(behaviorRecorderProvider).record(
                BehaviorEventType.productClick,
                productId: group.groupId,
                category: group.category,
                brand: group.brand,
                price: group.bestPrice,
              );
          Navigator.of(context).push(
            MaterialPageRoute(
              builder: (_) => ProductGroupDetailScreen(group: group),
            ),
          );
        },
        child: Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: AppColors.panel,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: AppColors.line.withAlpha(120)),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withAlpha(6),
                blurRadius: 8,
                offset: const Offset(0, 2),
              ),
            ],
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Top row: image + title + arrow
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _groupThumb(group, size: 72),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(group.displayTitle,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                                fontSize: 15,
                                height: 1.3,
                                fontWeight: FontWeight.w600)),
                        const SizedBox(height: 6),
                        // Rating + reviews + badges
                        Row(
                          children: [
                            Icon(Icons.star_rounded,
                                size: 15, color: AppColors.warn.withAlpha(220)),
                            const SizedBox(width: 2),
                            Text(topRating.toStringAsFixed(1),
                                style: const TextStyle(
                                    fontSize: 12,
                                    fontWeight: FontWeight.w700,
                                    color: AppColors.inkMain)),
                            const SizedBox(width: 4),
                            Text('${_formatCount(totalReviews)}评价',
                                style: const TextStyle(
                                    fontSize: 11, color: AppColors.inkSoft)),
                            const SizedBox(width: 8),
                            Container(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 5, vertical: 2),
                              decoration: BoxDecoration(
                                color: AppColors.panelSoft,
                                borderRadius: BorderRadius.circular(5),
                              ),
                              child: Text('${group.platformCount}个平台',
                                  style: const TextStyle(
                                      fontSize: 10,
                                      color: AppColors.inkSoft,
                                      fontWeight: FontWeight.w500)),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                  const Padding(
                    padding: EdgeInsets.only(top: 4),
                    child: Icon(Icons.chevron_right,
                        size: 20, color: AppColors.inkSoft),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              // Price row — platform badge + best price
              if (bestOffer != null)
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  decoration: BoxDecoration(
                    color: AppColors.primaryMuted.withAlpha(40),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.center,
                        children: [
                          Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 7, vertical: 3),
                            decoration: BoxDecoration(
                              color: platformColor(bestOffer.platform)
                                  .withAlpha(22),
                              borderRadius: BorderRadius.circular(5),
                            ),
                            child: Text(_platformLabel(bestOffer.platform),
                                style: TextStyle(
                                    fontSize: 11,
                                    fontWeight: FontWeight.w700,
                                    color: platformColor(bestOffer.platform))),
                          ),
                          const SizedBox(width: 8),
                          Text('¥${bestOffer.price.toStringAsFixed(0)}',
                              style: const TextStyle(
                                  fontSize: 20,
                                  height: 1,
                                  fontWeight: FontWeight.w700,
                                  color: AppColors.priceRed)),
                          const SizedBox(width: 4),
                          const Text('起',
                              style: TextStyle(
                                  fontSize: 11, color: AppColors.inkSoft)),
                          const Spacer(),
                          TextButton.icon(
                            key: Key('favorite_group_${bestOffer.productId}'),
                            onPressed: () => _addPlatformOfferToFavorites(
                                bestOffer,
                                group: group),
                            icon: Icon(
                                isFavorite
                                    ? Icons.favorite
                                    : Icons.favorite_border,
                                size: 15),
                            label: Text(isFavorite ? '已收藏' : '收藏',
                                style: const TextStyle(fontSize: 12)),
                            style: TextButton.styleFrom(
                              foregroundColor: isFavorite
                                  ? AppColors.priceRed
                                  : AppColors.inkSoft,
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 6, vertical: 4),
                              minimumSize: const Size(0, 30),
                              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                            ),
                          ),
                        ],
                      ),
                      if (otherPrices.isNotEmpty) ...[
                        const SizedBox(height: 6),
                        Wrap(
                          spacing: 10,
                          runSpacing: 4,
                          children: otherPrices.entries.take(2).map((e) {
                            return Text(
                              '${_platformLabel(e.key)} ¥${e.value.toStringAsFixed(0)}',
                              style: const TextStyle(
                                  fontSize: 11, color: AppColors.inkSoft),
                            );
                          }).toList(),
                        ),
                      ],
                    ],
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _groupThumb(ProductGroup group, {double size = 56}) {
    // Prefer group thumbnailUrl, fallback to first platform's imageUrl
    String imageUrl = group.thumbnailUrl?.trim() ?? '';
    if (imageUrl.isEmpty && group.platforms.isNotEmpty) {
      imageUrl = group.platforms.first.imageUrl.trim();
    }
    if (imageUrl.startsWith('http://') || imageUrl.startsWith('https://')) {
      return ClipRRect(
        borderRadius: BorderRadius.circular(6),
        child: Image.network(
          imageUrl,
          width: size,
          height: size,
          fit: BoxFit.cover,
          errorBuilder: (_, __, ___) => _groupThumbPlaceholder(group, size),
        ),
      );
    }
    return _groupThumbPlaceholder(group, size);
  }

  Widget _groupThumbPlaceholder(ProductGroup group, double size) {
    final colors = _thumbColors(group.category ?? '');
    final brand = group.brand ?? '';
    final initial = brand.isNotEmpty ? brand[0] : '商';

    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(10),
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [colors.bg, colors.bg2],
        ),
        boxShadow: [
          BoxShadow(
            color: colors.bg.withAlpha(60),
            blurRadius: 4,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Stack(
        children: [
          Positioned(
            right: -size * 0.15,
            bottom: -size * 0.1,
            child: Icon(colors.icon,
                size: size * 0.55, color: Colors.white.withAlpha(30)),
          ),
          Center(
            child: Text(initial,
                style: TextStyle(
                    fontSize: size * 0.32,
                    fontWeight: FontWeight.w700,
                    color: Colors.white)),
          ),
        ],
      ),
    );
  }

  ThumbColors _thumbColors(String category) {
    return switch (category) {
      '运动鞋' => ThumbColors(const Color(0xFF6366F1), const Color(0xFF818CF8),
          Icons.directions_run),
      '耳机' => ThumbColors(
          const Color(0xFF0EA5E9), const Color(0xFF38BDF8), Icons.headphones),
      '吹风机' => ThumbColors(
          const Color(0xFFF43F5E), const Color(0xFFFB7185), Icons.air),
      '背包' => ThumbColors(
          const Color(0xFFF59E0B), const Color(0xFFFBBF24), Icons.backpack),
      '智能手表' => ThumbColors(
          const Color(0xFF10B981), const Color(0xFF34D399), Icons.watch),
      _ => ThumbColors(const Color(0xFF6366F1), const Color(0xFF818CF8),
          Icons.shopping_bag_outlined),
    };
  }

  String _platformLabel(String platform) {
    return switch (platform) {
      '京东-mock' => '京东',
      '拼多多-mock' => '拼多多',
      '淘宝-mock' => '淘宝',
      '天猫-mock' => '天猫',
      _ => platform,
    };
  }

  // ── Input bar ───────────────────────────────────────────────

  Widget _buildInputBar(ReplyCard? recognitionQuickCard) {
    final sending = ref.watch(chatControllerProvider).sending;
    final inputFocused = _textFocusNode.hasFocus;

    return SafeArea(
      top: false,
      child: Container(
        padding: const EdgeInsets.fromLTRB(12, 8, 12, 10),
        decoration: const BoxDecoration(
          color: AppColors.panel,
          border: Border(top: BorderSide(color: AppColors.line, width: 0.5)),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (_pendingImage != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 8, left: 6),
                child: Row(
                  children: [
                    ClipRRect(
                      borderRadius: BorderRadius.circular(10),
                      child: Image.file(
                        _pendingImage!,
                        width: 52,
                        height: 52,
                        fit: BoxFit.cover,
                      ),
                    ),
                    const SizedBox(width: 10),
                    if (_uploadedImageId != null)
                      const Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.check_circle,
                              size: 15, color: AppColors.good),
                          SizedBox(width: 4),
                          Text('已上传',
                              style: TextStyle(
                                  fontSize: 12, color: AppColors.good)),
                        ],
                      )
                    else if (_imageUploadFailed)
                      const Text('上传失败',
                          style: TextStyle(
                              fontSize: 12, color: AppColors.priceRed))
                    else
                      const SizedBox(
                          width: 14,
                          height: 14,
                          child: CircularProgressIndicator(strokeWidth: 2)),
                    const Spacer(),
                    IconButton(
                      icon: const Icon(Icons.close, size: 16),
                      onPressed: () => setState(() {
                        _pendingImage = null;
                        _uploadedImageId = null;
                        _imageUploadFailed = false;
                      }),
                      padding: EdgeInsets.zero,
                      constraints:
                          const BoxConstraints(minWidth: 30, minHeight: 30),
                    ),
                  ],
                ),
              ),
            Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                _composerIconButton(
                  icon: Icons.image_outlined,
                  tooltip: '添加图片',
                  onPressed: sending ? null : _showImageSourceSheet,
                ),
                _composerIconButton(
                  icon: Icons.mic_none,
                  tooltip: '语音输入',
                  onPressed: sending ? null : _onVoiceTap,
                ),
                if (recognitionQuickCard != null)
                  _composerIconButton(
                    key: const Key('recognition_quick_icon_button'),
                    icon: Icons.image_search,
                    tooltip: '识别结果',
                    onPressed: sending
                        ? null
                        : () => _openCorrectionSheet(recognitionQuickCard),
                  ),
                Expanded(
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 140),
                    curve: Curves.easeOut,
                    constraints: const BoxConstraints(minHeight: 46),
                    decoration: BoxDecoration(
                      color: AppColors.panelSoft,
                      borderRadius: BorderRadius.circular(24),
                      border: Border.all(
                        color: inputFocused
                            ? AppColors.accent.withAlpha(130)
                            : AppColors.line,
                        width: inputFocused ? 1 : 0.5,
                      ),
                      boxShadow: [
                        BoxShadow(
                          color: inputFocused
                              ? AppColors.accent.withAlpha(16)
                              : Colors.black.withAlpha(5),
                          blurRadius: inputFocused ? 10 : 4,
                          offset: const Offset(0, 1),
                        ),
                      ],
                    ),
                    child: TextField(
                      key: const Key('chat_input_field'),
                      controller: _textController,
                      focusNode: _textFocusNode,
                      minLines: 1,
                      maxLines: 4,
                      keyboardType: TextInputType.multiline,
                      style: const TextStyle(fontSize: 14.5, height: 1.35),
                      decoration: const InputDecoration(
                        hintText: '搜商品、品牌或预算',
                        hintStyle:
                            TextStyle(fontSize: 14.5, color: AppColors.inkSoft),
                        border: InputBorder.none,
                        enabledBorder: InputBorder.none,
                        focusedBorder: InputBorder.none,
                        contentPadding:
                            EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                        isDense: true,
                        filled: true,
                        fillColor: Colors.transparent,
                      ),
                      textInputAction: TextInputAction.send,
                      onSubmitted: (_) {
                        if (_canSendMessage(sending, _textController.text)) {
                          _sendMessage();
                        }
                      },
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                ValueListenableBuilder<TextEditingValue>(
                  valueListenable: _textController,
                  builder: (context, value, _) {
                    final canSend = _canSendMessage(sending, value.text);
                    return _sendButton(canSend: canSend);
                  },
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _composerIconButton({
    Key? key,
    required IconData icon,
    required String tooltip,
    required VoidCallback? onPressed,
  }) {
    final enabled = onPressed != null;
    return Padding(
      padding: const EdgeInsets.only(right: 6, bottom: 1),
      child: SizedBox(
        width: 44,
        height: 44,
        child: IconButton(
          key: key,
          tooltip: tooltip,
          icon: Icon(icon, size: 21),
          color: enabled ? AppColors.inkSoft : AppColors.lineStrong,
          onPressed: onPressed,
          padding: EdgeInsets.zero,
          constraints: const BoxConstraints(minWidth: 44, minHeight: 44),
          style: IconButton.styleFrom(
            tapTargetSize: MaterialTapTargetSize.shrinkWrap,
            backgroundColor: AppColors.panelSoft,
            disabledBackgroundColor: AppColors.panelSoft,
            shape: const CircleBorder(
              side: BorderSide(color: AppColors.line, width: 0.5),
            ),
          ),
        ),
      ),
    );
  }

  Widget _sendButton({required bool canSend}) {
    return Semantics(
      button: true,
      enabled: canSend,
      label: _imageUploadInProgress ? '图片上传中' : '发送消息',
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 140),
        curve: Curves.easeOut,
        width: 46,
        height: 46,
        margin: const EdgeInsets.only(bottom: 1),
        decoration: BoxDecoration(
          gradient: canSend
              ? const LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [AppColors.userBubble, AppColors.userBubbleEnd],
                )
              : null,
          color: canSend ? null : AppColors.line,
          borderRadius: BorderRadius.circular(23),
          boxShadow: canSend
              ? [
                  BoxShadow(
                    color: AppColors.userBubble.withAlpha(34),
                    blurRadius: 10,
                    offset: const Offset(0, 3),
                  ),
                ]
              : null,
        ),
        child: IconButton(
          key: const Key('chat_send_button'),
          tooltip: '发送',
          icon: Icon(
            _imageUploadInProgress ? Icons.hourglass_top : Icons.arrow_upward,
            size: 20,
          ),
          color: canSend ? Colors.white : AppColors.inkSoft,
          onPressed: canSend ? _sendMessage : null,
          padding: EdgeInsets.zero,
          constraints: const BoxConstraints(minWidth: 46, minHeight: 46),
          iconSize: 20,
        ),
      ),
    );
  }
}
/// Privacy notice shown before onboarding on first launch.
class _PrivacyNoticeDialog extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('隐私与个性化推荐'),
      content: const Text(
        '为了给你更相关的商品推荐，识价镜会：\n\n'
        '• 记录你搜索、点击、查看的商品信息\n'
        '• 根据使用行为推断你的购物偏好\n'
        '• 使用偏好优化商品排序\n\n'
        '原始行为事件仅存储在手机本地，不会上传服务器；\n'
        '开启个性化后，推断出的偏好画像（品类、品牌、价位等）会随聊天请求发送至服务器用于排序。\n\n'
        '你可以随时在「我的 → 推荐记忆与隐私」中查看、管理或删除这些数据。',
        style: TextStyle(fontSize: 14, height: 1.6),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context, true),
          child: const Text('同意并继续'),
        ),
        TextButton(
          onPressed: () => Navigator.pop(context, false),
          child: const Text('跳过', style: TextStyle(color: AppColors.inkSoft)),
        ),
      ],
    );
  }
}
