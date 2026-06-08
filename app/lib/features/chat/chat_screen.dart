import 'dart:io';
import 'dart:math' as math;
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
import 'product_group_detail_screen.dart';

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
  final _scrollController = ScrollController();
  final _picker = ImagePicker();
  final _scaffoldKey = GlobalKey<ScaffoldState>();
  final Set<String> _favoriteProductIds = <String>{};
  File? _pendingImage;
  String? _uploadedImageId;
  bool _imageUploadFailed = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(chatControllerProvider.notifier).loadSessions();
    });
  }

  @override
  void dispose() {
    _textController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  // ── Actions ────────────────────────────────────────────────

  void _sendMessage() {
    final text = _textController.text.trim();
    final hasText = text.isNotEmpty;
    final hasImage = _uploadedImageId != null;
    final hasPendingImageUpload =
        _pendingImage != null && _uploadedImageId == null;
    if (hasPendingImageUpload) return;
    if (!hasText && !hasImage) return;
    if (ref.read(chatControllerProvider).sending) return;

    final imageIds = _uploadedImageId != null ? [_uploadedImageId!] : null;
    final imagePaths =
        hasImage && _pendingImage != null ? [_pendingImage!.path] : null;
    ref.read(chatControllerProvider.notifier).sendTextMessage(
          hasText ? text : '',
          imageIds: imageIds,
          imagePaths: imagePaths,
        );

    _textController.clear();
    setState(() {
      _pendingImage = null;
      _uploadedImageId = null;
      _imageUploadFailed = false;
    });
    _scrollToBottom();
  }

  void _onOptionSelected(String optionId) {
    ref.read(chatControllerProvider.notifier).selectOption(optionId);
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
                '当前演示使用 Mock 商品数据，不会打开真实电商页面。正式接入后将跳转到$platform商品详情页。',
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
    final recId = recognitionCard.recognitionId;
    if (recId == null) return;

    final categoryCtrl =
        TextEditingController(text: recognitionCard.category ?? '');
    final brandCtrl = TextEditingController(text: recognitionCard.brand ?? '');
    final modelCtrl = TextEditingController(text: recognitionCard.model ?? '');

    final attrEntries = <_AttrRow>[];
    if (recognitionCard.attributes != null) {
      recognitionCard.attributes!.forEach((k, v) {
        attrEntries.add(_AttrRow(
          keyCtrl: TextEditingController(text: k.toString()),
          valueCtrl: TextEditingController(text: v.toString()),
        ));
      });
    }

    final navigator = Navigator.of(context);
    final messenger = ScaffoldMessenger.of(context);

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (ctx) {
        return StatefulBuilder(
          builder: (ctx, setSheetState) {
            return Padding(
              padding: EdgeInsets.only(
                left: 16,
                right: 16,
                top: 16,
                bottom: MediaQuery.of(ctx).viewInsets.bottom + 16,
              ),
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('修正识别结果',
                        style: TextStyle(
                            fontSize: 18, fontWeight: FontWeight.w700)),
                    const SizedBox(height: 12),
                    TextField(
                      controller: categoryCtrl,
                      decoration: const InputDecoration(labelText: '商品类别'),
                    ),
                    const SizedBox(height: 8),
                    TextField(
                      controller: brandCtrl,
                      decoration: const InputDecoration(labelText: '品牌'),
                    ),
                    const SizedBox(height: 8),
                    TextField(
                      controller: modelCtrl,
                      decoration: const InputDecoration(labelText: '型号'),
                    ),
                    const SizedBox(height: 12),
                    const Text('属性',
                        style: TextStyle(
                            fontSize: 14, fontWeight: FontWeight.w600)),
                    ...attrEntries.map((e) => Padding(
                          padding: const EdgeInsets.only(top: 8),
                          child: Row(
                            children: [
                              SizedBox(
                                width: 70,
                                child: TextField(
                                  controller: e.keyCtrl,
                                  decoration: const InputDecoration(
                                      hintText: 'key', isDense: true),
                                ),
                              ),
                              const SizedBox(width: 8),
                              Expanded(
                                child: TextField(
                                  controller: e.valueCtrl,
                                  decoration: const InputDecoration(
                                      hintText: 'value', isDense: true),
                                ),
                              ),
                            ],
                          ),
                        )),
                    const SizedBox(height: 8),
                    TextButton.icon(
                      onPressed: () {
                        setSheetState(() {
                          attrEntries.add(_AttrRow(
                            keyCtrl: TextEditingController(),
                            valueCtrl: TextEditingController(),
                          ));
                        });
                      },
                      icon: const Icon(Icons.add, size: 16),
                      label: const Text('新增属性'),
                    ),
                    const SizedBox(height: 16),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.end,
                      children: [
                        TextButton(
                          onPressed: () => navigator.pop(),
                          child: const Text('取消'),
                        ),
                        const SizedBox(width: 8),
                        ElevatedButton(
                          onPressed: () async {
                            final attrs = <String, dynamic>{};
                            for (final e in attrEntries) {
                              final k = e.keyCtrl.text.trim();
                              if (k.isEmpty) continue;
                              attrs[k] = e.valueCtrl.text.trim();
                            }
                            final payload = {
                              'category': categoryCtrl.text,
                              'brand': brandCtrl.text,
                              'model': modelCtrl.text,
                              'attributes': attrs,
                            };

                            final recApi = ref.read(recognitionApiProvider);
                            try {
                              final updated =
                                  await recApi.updateAttributes(recId, payload);
                              if (!mounted) return;
                              ref
                                  .read(chatControllerProvider.notifier)
                                  .updateRecognitionCard(recId, updated);
                              navigator.pop();
                              messenger.showSnackBar(
                                const SnackBar(content: Text('识别结果已更新')),
                              );
                            } catch (_) {
                              if (mounted) {
                                messenger.showSnackBar(
                                  const SnackBar(content: Text('修正失败，请重试')),
                                );
                              }
                            }
                          },
                          child: const Text('保存'),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOut,
        );
      }
    });
  }

  // ── Build ──────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    final controller = ref.watch(chatControllerProvider);
    final messages = controller.messages;

    return Scaffold(
      key: _scaffoldKey,
      backgroundColor: AppColors.background,
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.history),
          tooltip: '历史对话',
          onPressed: () => _scaffoldKey.currentState?.openDrawer(),
        ),
        title: const Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('购物助手'),
            SizedBox(height: 2),
            Text(
              '拍照识物 · 多平台比价',
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w400,
                color: AppColors.inkSoft,
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => context.go('/me'),
            child: const Text('我的',
                style: TextStyle(
                    color: AppColors.accent,
                    fontSize: 15,
                    fontWeight: FontWeight.w600)),
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
                    padding: const EdgeInsets.fromLTRB(12, 10, 12, 4),
                    itemCount: messages.length,
                    itemBuilder: (context, index) =>
                        _buildMessage(messages[index]),
                  ),
          ),
          _buildInputBar(),
        ],
      ),
    );
  }

  Widget _buildEmpty() {
    final examples = ['300以内的黑色耳机', '拍照识别同款', '京东索尼评分4.8以上'];
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.search, size: 36, color: AppColors.inkSoft),
          const SizedBox(height: 12),
          const Text(
            '说出商品、预算和偏好',
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 6),
          Text(
            '例如平台、品牌、价格、颜色、评分',
            style:
                Theme.of(context).textTheme.bodySmall?.copyWith(fontSize: 13),
          ),
          const SizedBox(height: 16),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            alignment: WrapAlignment.center,
            children: examples.map((text) {
              return OutlinedButton(
                onPressed: () {
                  _textController.text = text;
                  _textController.selection = TextSelection.fromPosition(
                    TextPosition(offset: _textController.text.length),
                  );
                },
                style: OutlinedButton.styleFrom(
                  visualDensity: VisualDensity.compact,
                  side: const BorderSide(color: AppColors.line),
                  foregroundColor: AppColors.inkMain,
                  backgroundColor: AppColors.panel,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(16),
                  ),
                ),
                child: Text(text, style: const TextStyle(fontSize: 12)),
              );
            }).toList(),
          ),
        ],
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
    return const Padding(
      padding: EdgeInsets.only(bottom: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(width: 2),
          SizedBox(
            width: 16,
            height: 16,
            child: CircularProgressIndicator(strokeWidth: 2),
          ),
          SizedBox(width: 8),
          Text('正在思考…',
              style: TextStyle(fontSize: 13, color: AppColors.inkSoft)),
        ],
      ),
    );
  }

  Widget _buildUserMessage(ChatMessage msg) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.end,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Flexible(
            child: ConstrainedBox(
              constraints: BoxConstraints(
                maxWidth: MediaQuery.of(context).size.width * 0.76,
              ),
              child: Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
                decoration: const BoxDecoration(
                  color: AppColors.accent,
                  borderRadius: BorderRadius.only(
                    topLeft: Radius.circular(12),
                    topRight: Radius.circular(4),
                    bottomLeft: Radius.circular(12),
                    bottomRight: Radius.circular(12),
                  ),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    if (msg.text != null && msg.text!.isNotEmpty)
                      Text(msg.text!,
                          style: const TextStyle(
                              fontSize: 15, height: 1.35, color: Colors.white)),
                    if (msg.imagePaths.isNotEmpty) ...[
                      const SizedBox(height: 6),
                      ClipRRect(
                        borderRadius: BorderRadius.circular(8),
                        child: Image.file(
                          File(msg.imagePaths.first),
                          width: 120,
                          height: 120,
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
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Align(
        alignment: Alignment.centerLeft,
        child: ConstrainedBox(
          constraints: BoxConstraints(
            maxWidth: MediaQuery.of(context).size.width - 24,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (msg.text != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Text(msg.text!,
                      style: const TextStyle(
                          fontSize: 13, height: 1.4, color: AppColors.inkSoft)),
                ),
              if (reply != null)
                ...reply.cards.map((card) => _buildCard(card, reply.cards)),
            ],
          ),
        ),
      ),
    );
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
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(card.title,
              style:
                  const TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: options.map((opt) {
              return OutlinedButton(
                onPressed: () => _onOptionSelected(opt.optionId),
                style: OutlinedButton.styleFrom(
                  visualDensity: VisualDensity.compact,
                  foregroundColor: AppColors.inkMain,
                  side: const BorderSide(color: AppColors.line),
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8),
                  ),
                ),
                child: Text(opt.label, style: const TextStyle(fontSize: 13)),
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

  Widget _alternativeProductRow(_AlternativeProductView item) {
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

  List<_AlternativeProductView> _alternativeProducts(
      ReplyCard card, List<ProductItem> products) {
    final analyses = card.productAnalyses ?? const <ProductAnalysis>[];
    final items = <_AlternativeProductView>[];
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
      items.add(_AlternativeProductView(
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
    return Container(
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
              painter: _ProductThumbPainter(
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
    final filterSummary = card.filterSummary;
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
          Row(
            children: [
              const Icon(Icons.category_outlined,
                  size: 17, color: AppColors.accent),
              const SizedBox(width: 6),
              Text(card.title,
                  style: const TextStyle(
                      fontSize: 15, fontWeight: FontWeight.w700)),
              const Spacer(),
              if (groups.isNotEmpty)
                Text('${groups.length} 组',
                    style: const TextStyle(
                        fontSize: 12, color: AppColors.inkSoft)),
            ],
          ),
          if (filterSummary.isNotEmpty) ...[
            const SizedBox(height: 6),
            _buildFilterBar(card, []),
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

    return Container(
      key: const Key('recognition_result_box'),
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
                      TextButton.icon(
                        onPressed: () => _openCorrectionSheet(card),
                        icon: const Icon(Icons.edit, size: 14),
                        label: const Text('修正', style: TextStyle(fontSize: 12)),
                        style: TextButton.styleFrom(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 8, vertical: 2),
                          minimumSize: const Size(0, 28),
                          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                        ),
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
  }

  Widget _buildGroupRow(ProductGroup group) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.panel,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.line),
      ),
      child: InkWell(
        onTap: () {
          Navigator.of(context).push(
            MaterialPageRoute(
              builder: (_) => ProductGroupDetailScreen(group: group),
            ),
          );
        },
        borderRadius: BorderRadius.circular(8),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _groupThumb(group),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(group.displayTitle,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                          fontSize: 14,
                          height: 1.35,
                          fontWeight: FontWeight.w600)),
                  const SizedBox(height: 4),
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Text('¥${group.bestPrice.toStringAsFixed(0)}',
                          style: const TextStyle(
                              fontSize: 18,
                              height: 1,
                              fontWeight: FontWeight.w700,
                              color: AppColors.priceRed)),
                      const Spacer(),
                      Text(
                        '${group.platformCount} 个平台',
                        style: const TextStyle(
                            fontSize: 11, color: AppColors.inkSoft),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(width: 4),
            const Icon(Icons.chevron_right, size: 18, color: AppColors.inkSoft),
          ],
        ),
      ),
    );
  }

  Widget _groupThumb(ProductGroup group) {
    final imageUrl = group.thumbnailUrl?.trim() ?? '';
    if (imageUrl.startsWith('http://') || imageUrl.startsWith('https://')) {
      return ClipRRect(
        borderRadius: BorderRadius.circular(6),
        child: Image.network(
          imageUrl,
          width: 56,
          height: 56,
          fit: BoxFit.cover,
          errorBuilder: (_, __, ___) => _groupThumbPlaceholder(group),
        ),
      );
    }
    return _groupThumbPlaceholder(group);
  }

  Widget _groupThumbPlaceholder(ProductGroup group) {
    final accent = switch (group.category ?? '') {
      '耳机' => const Color(0xFF2F343B),
      '吹风机' => const Color(0xFFB23A48),
      '背包' => const Color(0xFFC27A2C),
      '智能手表' => const Color(0xFF4A6FA5),
      _ => AppColors.accent,
    };
    final icon = switch (group.category ?? '') {
      '耳机' => Icons.headphones,
      '吹风机' => Icons.air,
      '背包' => Icons.backpack,
      '智能手表' => Icons.watch,
      _ => Icons.shopping_bag_outlined,
    };
    return Container(
      width: 56,
      height: 56,
      decoration: BoxDecoration(
        color: accent.withAlpha(15),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: AppColors.line),
      ),
      child: Icon(icon, size: 24, color: accent.withAlpha(150)),
    );
  }

  String _platformLabel(String platform) {
    return switch (platform) {
      '京东-mock' => '京东',
      '拼多多-mock' => '拼多多',
      '淘宝-mock' => '淘宝',
      _ => platform,
    };
  }

  // ── Input bar ───────────────────────────────────────────────

  Widget _buildInputBar() {
    final sending = ref.watch(chatControllerProvider).sending;

    return SafeArea(
      top: false,
      child: Container(
        padding: const EdgeInsets.fromLTRB(8, 8, 8, 8),
        decoration: const BoxDecoration(
          color: AppColors.panel,
          border: Border(top: BorderSide(color: AppColors.line)),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (_pendingImage != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 8, left: 4),
                child: Row(
                  children: [
                    ClipRRect(
                      borderRadius: BorderRadius.circular(6),
                      child: Image.file(
                        _pendingImage!,
                        width: 60,
                        height: 60,
                        fit: BoxFit.cover,
                      ),
                    ),
                    const SizedBox(width: 8),
                    if (_uploadedImageId != null)
                      const Icon(Icons.check_circle,
                          size: 16, color: AppColors.good)
                    else if (_imageUploadFailed)
                      const Icon(Icons.error,
                          size: 16, color: AppColors.priceRed)
                    else
                      const SizedBox(
                          width: 14,
                          height: 14,
                          child: CircularProgressIndicator(strokeWidth: 2)),
                    const Spacer(),
                    IconButton(
                      icon: const Icon(Icons.close, size: 18),
                      onPressed: () => setState(() {
                        _pendingImage = null;
                        _uploadedImageId = null;
                        _imageUploadFailed = false;
                      }),
                      padding: EdgeInsets.zero,
                      constraints:
                          const BoxConstraints(minWidth: 32, minHeight: 32),
                    ),
                  ],
                ),
              ),
            Row(
              children: [
                IconButton(
                  icon: const Icon(Icons.image_outlined, size: 22),
                  color: AppColors.inkSoft,
                  onPressed: sending ? null : _showImageSourceSheet,
                  padding: EdgeInsets.zero,
                  constraints:
                      const BoxConstraints(minWidth: 40, minHeight: 40),
                ),
                IconButton(
                  icon: const Icon(Icons.mic_none, size: 22),
                  color: AppColors.inkSoft,
                  onPressed: _onVoiceTap,
                  padding: EdgeInsets.zero,
                  constraints:
                      const BoxConstraints(minWidth: 40, minHeight: 40),
                ),
                Expanded(
                  child: TextField(
                    controller: _textController,
                    minLines: 1,
                    maxLines: 4,
                    style: const TextStyle(fontSize: 14, height: 1.35),
                    decoration: InputDecoration(
                      hintText: '搜商品、品牌或预算',
                      hintStyle: const TextStyle(
                          fontSize: 14, color: AppColors.inkSoft),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(10),
                        borderSide: const BorderSide(color: AppColors.line),
                      ),
                      enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(10),
                        borderSide: const BorderSide(color: AppColors.line),
                      ),
                      focusedBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(10),
                        borderSide: const BorderSide(color: AppColors.accent),
                      ),
                      contentPadding: const EdgeInsets.symmetric(
                          horizontal: 12, vertical: 9),
                      isDense: true,
                      filled: true,
                      fillColor: AppColors.panelSoft,
                    ),
                    textInputAction: TextInputAction.send,
                    onSubmitted: (_) => _sendMessage(),
                  ),
                ),
                const SizedBox(width: 6),
                DecoratedBox(
                  decoration: BoxDecoration(
                    color: sending ? AppColors.line : AppColors.accent,
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: IconButton(
                    icon: const Icon(Icons.arrow_forward, size: 20),
                    color: sending ? AppColors.inkSoft : Colors.white,
                    onPressed: sending ? null : _sendMessage,
                    padding: EdgeInsets.zero,
                    constraints:
                        const BoxConstraints(minWidth: 40, minHeight: 40),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _AlternativeProductView {
  final String title;
  final String platform;
  final String price;
  final String strength;
  final String caution;

  const _AlternativeProductView({
    required this.title,
    required this.platform,
    required this.price,
    required this.strength,
    required this.caution,
  });
}

class _ProductThumbPainter extends CustomPainter {
  final IconData icon;
  final Color accent;
  final Color lineColor;
  final String text;

  const _ProductThumbPainter({
    required this.icon,
    required this.accent,
    required this.lineColor,
    required this.text,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final softPaint = Paint()
      ..color = accent.withAlpha(18)
      ..style = PaintingStyle.fill;
    canvas.drawCircle(Offset(size.width * 0.68, size.height * 0.28),
        size.width * 0.28, softPaint);
    canvas.drawCircle(Offset(size.width * 0.28, size.height * 0.78),
        size.width * 0.18, softPaint);

    if (text.contains('耳机')) {
      _paintHeadphones(canvas, size);
    } else if (text.contains('鞋')) {
      _paintShoe(canvas, size);
    } else if (text.contains('吹风机')) {
      _paintHairDryer(canvas, size);
    } else if (text.contains('背包') || text.contains('双肩')) {
      _paintBag(canvas, size);
    } else if (text.contains('手表')) {
      _paintWatch(canvas, size);
    } else {
      _paintIcon(canvas, size);
    }
  }

  void _paintHeadphones(Canvas canvas, Size size) {
    final stroke = Paint()
      ..color = accent
      ..style = PaintingStyle.stroke
      ..strokeWidth = 4
      ..strokeCap = StrokeCap.round;
    final fill = Paint()
      ..color = accent.withAlpha(170)
      ..style = PaintingStyle.fill;
    canvas.drawArc(
      Rect.fromLTWH(size.width * 0.24, size.height * 0.20, size.width * 0.52,
          size.height * 0.54),
      math.pi,
      math.pi,
      false,
      stroke,
    );
    canvas.drawRRect(
        RRect.fromRectAndRadius(
            Rect.fromLTWH(size.width * 0.23, size.height * 0.48,
                size.width * 0.17, size.height * 0.27),
            const Radius.circular(8)),
        fill);
    canvas.drawRRect(
        RRect.fromRectAndRadius(
            Rect.fromLTWH(size.width * 0.60, size.height * 0.48,
                size.width * 0.17, size.height * 0.27),
            const Radius.circular(8)),
        fill);
    canvas.drawLine(Offset(size.width * 0.40, size.height * 0.72),
        Offset(size.width * 0.60, size.height * 0.72), stroke);
  }

  void _paintShoe(Canvas canvas, Size size) {
    final fill = Paint()
      ..color = accent.withAlpha(190)
      ..style = PaintingStyle.fill;
    final sole = Paint()
      ..color = lineColor
      ..strokeWidth = 3
      ..strokeCap = StrokeCap.round;
    final path = Path()
      ..moveTo(size.width * 0.20, size.height * 0.58)
      ..quadraticBezierTo(size.width * 0.43, size.height * 0.34,
          size.width * 0.62, size.height * 0.48)
      ..quadraticBezierTo(size.width * 0.76, size.height * 0.58,
          size.width * 0.84, size.height * 0.64)
      ..quadraticBezierTo(size.width * 0.67, size.height * 0.72,
          size.width * 0.23, size.height * 0.70)
      ..close();
    canvas.drawPath(path, fill);
    canvas.drawLine(Offset(size.width * 0.18, size.height * 0.73),
        Offset(size.width * 0.82, size.height * 0.74), sole);
  }

  void _paintHairDryer(Canvas canvas, Size size) {
    final fill = Paint()
      ..color = accent.withAlpha(185)
      ..style = PaintingStyle.fill;
    canvas.drawRRect(
        RRect.fromRectAndRadius(
            Rect.fromLTWH(size.width * 0.22, size.height * 0.35,
                size.width * 0.36, size.height * 0.24),
            const Radius.circular(10)),
        fill);
    final nozzle = Path()
      ..moveTo(size.width * 0.56, size.height * 0.39)
      ..lineTo(size.width * 0.82, size.height * 0.35)
      ..lineTo(size.width * 0.82, size.height * 0.56)
      ..lineTo(size.width * 0.56, size.height * 0.53)
      ..close();
    canvas.drawPath(nozzle, fill);
    canvas.drawRRect(
        RRect.fromRectAndRadius(
            Rect.fromLTWH(size.width * 0.34, size.height * 0.55,
                size.width * 0.14, size.height * 0.28),
            const Radius.circular(6)),
        fill);
  }

  void _paintBag(Canvas canvas, Size size) {
    final fill = Paint()
      ..color = accent.withAlpha(180)
      ..style = PaintingStyle.fill;
    final stroke = Paint()
      ..color = lineColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3
      ..strokeCap = StrokeCap.round;
    canvas.drawRRect(
        RRect.fromRectAndRadius(
            Rect.fromLTWH(size.width * 0.28, size.height * 0.32,
                size.width * 0.44, size.height * 0.46),
            const Radius.circular(10)),
        fill);
    canvas.drawArc(
        Rect.fromLTWH(size.width * 0.36, size.height * 0.22, size.width * 0.28,
            size.height * 0.25),
        math.pi,
        math.pi,
        false,
        stroke);
    canvas.drawLine(Offset(size.width * 0.35, size.height * 0.52),
        Offset(size.width * 0.65, size.height * 0.52), stroke);
  }

  void _paintWatch(Canvas canvas, Size size) {
    final fill = Paint()
      ..color = accent.withAlpha(180)
      ..style = PaintingStyle.fill;
    final band = Paint()
      ..color = lineColor
      ..style = PaintingStyle.fill;
    canvas.drawRRect(
        RRect.fromRectAndRadius(
            Rect.fromLTWH(size.width * 0.43, size.height * 0.18,
                size.width * 0.14, size.height * 0.62),
            const Radius.circular(7)),
        band);
    canvas.drawCircle(
        Offset(size.width * 0.50, size.height * 0.50), size.width * 0.22, fill);
  }

  void _paintIcon(Canvas canvas, Size size) {
    final painter = TextPainter(
      text: TextSpan(
        text: String.fromCharCode(icon.codePoint),
        style: TextStyle(
          fontSize: 34,
          color: accent.withAlpha(185),
          fontFamily: icon.fontFamily,
          package: icon.fontPackage,
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    painter.paint(
      canvas,
      Offset(
          (size.width - painter.width) / 2, (size.height - painter.height) / 2),
    );
  }

  @override
  bool shouldRepaint(covariant _ProductThumbPainter oldDelegate) {
    return oldDelegate.icon != icon ||
        oldDelegate.accent != accent ||
        oldDelegate.lineColor != lineColor ||
        oldDelegate.text != text;
  }
}

class _AttrRow {
  final TextEditingController keyCtrl;
  final TextEditingController valueCtrl;

  _AttrRow({required this.keyCtrl, required this.valueCtrl});
}
