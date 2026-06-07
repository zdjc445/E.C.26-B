import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import '../../core/network/api_client.dart';
import '../../core/theme/app_theme.dart';
import '../alerts/price_alert_api.dart';
import '../auth/auth_controller.dart';
import '../favorites/favorite_api.dart';
import '../voice/voice_api.dart';
import 'chat_controller.dart';
import 'chat_history_drawer.dart';
import 'chat_models.dart';

final favoriteApiInChatProvider = Provider<FavoriteApi>((ref) {
  return FavoriteApi(baseUrl: ref.watch(apiBaseUrlProvider));
});

final priceAlertApiInChatProvider = Provider<PriceAlertApi>((ref) {
  return PriceAlertApi(baseUrl: ref.watch(apiBaseUrlProvider));
});

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
              if (reply != null) ...reply.cards.map(_buildCard),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildCard(ReplyCard card) {
    switch (card.cardType) {
      case 'clarification':
        return _buildClarificationCard(card);
      case 'recommendation':
        return _buildRecommendationCard(card);
      case 'recognition':
        return _buildRecognitionCard(card);
      case 'product_list':
        return _buildProductListCard(card);
      case 'comparison':
        return _buildComparisonCard(card);
      default:
        return const SizedBox.shrink();
    }
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

  Widget _buildRecommendationCard(ReplyCard card) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.panel,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.accent.withAlpha(40)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            const Icon(Icons.recommend, size: 18, color: AppColors.accent),
            const SizedBox(width: 6),
            Text(card.title,
                style:
                    const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
            const Spacer(),
            if (card.decisionScore != null)
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: card.decisionScore! >= 80
                      ? AppColors.good.withAlpha(20)
                      : AppColors.warn.withAlpha(20),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text('综合分 ${card.decisionScore}',
                    style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        color: card.decisionScore! >= 80
                            ? AppColors.good
                            : AppColors.warn)),
              ),
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
                Text('¥${card.price!.toStringAsFixed(2)}',
                    style: const TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w700,
                        color: AppColors.priceRed)),
            ]),
          if (card.reason != null) ...[
            const SizedBox(height: 6),
            Text(card.reason!,
                style: const TextStyle(fontSize: 12, color: AppColors.inkSoft)),
          ],
          // Quick actions: favorite / price alert
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
          // Provider status
          if (card.intentProvider != null ||
              card.explanationProvider != null) ...[
            const SizedBox(height: 6),
            Row(children: [
              if (card.intentProvider != null) ...[
                _providerChip('意图：${card.intentProvider}',
                    fallback: card.intentFallbackUsed == true),
                const SizedBox(width: 6),
              ],
              if (card.explanationProvider != null) ...[
                _providerChip('解释：${card.explanationProvider}',
                    fallback: card.explanationFallbackUsed == true),
              ],
            ]),
          ],
          if (card.notices != null && card.notices!.isNotEmpty) ...[
            const SizedBox(height: 4),
            ...card.notices!.map((n) => Text(n,
                style: const TextStyle(fontSize: 10, color: AppColors.warn))),
          ],
          // Decision signals
          if (card.decisionSignals != null &&
              card.decisionSignals!.isNotEmpty) ...[
            const SizedBox(height: 10),
            const Text('决策信号',
                style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
            const SizedBox(height: 4),
            ...card.decisionSignals!.map((s) => Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: Row(children: [
                    SizedBox(
                        width: 60,
                        child: Text(s.label,
                            style: const TextStyle(
                                fontSize: 11, color: AppColors.inkSoft))),
                    Expanded(
                        child: ClipRRect(
                      borderRadius: BorderRadius.circular(3),
                      child: LinearProgressIndicator(
                        value: s.score / 100.0,
                        backgroundColor: AppColors.line,
                        color: _signalColor(s.score),
                        minHeight: 6,
                      ),
                    )),
                    const SizedBox(width: 6),
                    Text('${s.score}',
                        style: const TextStyle(
                            fontSize: 11, fontWeight: FontWeight.w600)),
                  ]),
                )),
          ],
          // Evidence
          if (card.evidence != null && card.evidence!.isNotEmpty) ...[
            const SizedBox(height: 8),
            const Text('证据摘要',
                style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
            ...card.evidence!.map((e) => Padding(
                  padding: const EdgeInsets.only(top: 2),
                  child: Row(children: [
                    const Icon(Icons.check_circle_outline,
                        size: 12, color: AppColors.good),
                    const SizedBox(width: 4),
                    Expanded(
                        child: Text(e.content,
                            style: const TextStyle(
                                fontSize: 11, color: AppColors.inkSoft))),
                  ]),
                )),
          ],
          // Risks
          if (card.risks != null && card.risks!.isNotEmpty) ...[
            const SizedBox(height: 8),
            const Text('风险提示',
                style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
            ...card.risks!.map((r) => Padding(
                  padding: const EdgeInsets.only(top: 2),
                  child: Row(children: [
                    const Icon(Icons.warning_amber,
                        size: 12, color: AppColors.warn),
                    const SizedBox(width: 4),
                    Expanded(
                        child: Text(r,
                            style: const TextStyle(
                                fontSize: 11, color: AppColors.warn))),
                  ]),
                )),
          ],
          // Product analyses
          if (card.productAnalyses != null &&
              card.productAnalyses!.isNotEmpty) ...[
            const SizedBox(height: 8),
            const Text('商品对比',
                style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
            ...card.productAnalyses!.map((a) => Container(
                  margin: const EdgeInsets.only(top: 4),
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: AppColors.background,
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(children: [
                          Text('#${a.rank}',
                              style: const TextStyle(
                                  fontSize: 11, fontWeight: FontWeight.w700)),
                          const SizedBox(width: 6),
                          _platformBadge(a.platform),
                          const Spacer(),
                          Text('${a.score}分',
                              style: const TextStyle(
                                  fontSize: 11, fontWeight: FontWeight.w600)),
                        ]),
                        const SizedBox(height: 2),
                        if (a.strengths.isNotEmpty)
                          Text('优势：${a.strengths.join("、")}',
                              style: const TextStyle(
                                  fontSize: 11, color: AppColors.good)),
                        if (a.weaknesses.isNotEmpty)
                          Text('不足：${a.weaknesses.join("、")}',
                              style: const TextStyle(
                                  fontSize: 11, color: AppColors.warn)),
                      ]),
                )),
          ],
        ],
      ),
    );
  }

  Color _signalColor(int score) {
    if (score >= 80) return AppColors.good;
    if (score >= 50) return AppColors.warn;
    return AppColors.priceRed;
  }

  Widget _providerChip(String label, {bool fallback = false}) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: fallback
            ? AppColors.warn.withAlpha(20)
            : AppColors.accent.withAlpha(15),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Text(label,
            style: TextStyle(
                fontSize: 10,
                color: fallback ? AppColors.warn : AppColors.accent)),
        if (fallback) ...[
          const SizedBox(width: 4),
          const Text('已回退规则处理',
              style: TextStyle(fontSize: 9, color: AppColors.warn)),
        ],
      ]),
    );
  }

  Widget _buildRecognitionCard(ReplyCard card) {
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
            children: [
              const Icon(Icons.image_search, size: 18, color: AppColors.accent),
              const SizedBox(width: 6),
              Text(card.title,
                  style: const TextStyle(
                      fontSize: 14, fontWeight: FontWeight.w600)),
            ],
          ),
          const SizedBox(height: 8),
          if (card.category != null) _recognitionRow('类别', card.category!),
          if (card.brand != null) _recognitionRow('品牌', card.brand!),
          if (card.model != null) _recognitionRow('型号', card.model!),
          if (card.keywords != null && card.keywords!.isNotEmpty)
            _recognitionRow('关键词', card.keywords!.join('、')),
          if (card.attributes != null && card.attributes!.isNotEmpty)
            _recognitionRow(
                '属性',
                card.attributes!.entries
                    .map((e) => '${e.key}: ${e.value}')
                    .join('；')),
          if (card.confidence != null)
            _recognitionRow(
                '置信度', '${(card.confidence! * 100).toStringAsFixed(0)}%'),
          if (card.aiProvider != null)
            _recognitionRow('AI Provider', card.aiProvider!),
          if (card.fallbackUsed == true)
            const Text('已回退到 Mock 识别',
                style: TextStyle(fontSize: 11, color: AppColors.warn)),
          if (card.explanation != null && card.explanation!.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(card.explanation!,
                  style:
                      const TextStyle(fontSize: 11, color: AppColors.inkSoft)),
            ),
          const SizedBox(height: 8),
          Align(
            alignment: Alignment.centerRight,
            child: TextButton.icon(
              onPressed: () => _openCorrectionSheet(card),
              icon: const Icon(Icons.edit, size: 14),
              label: const Text('修正识别结果', style: TextStyle(fontSize: 12)),
            ),
          ),
        ],
      ),
    );
  }

  Widget _recognitionRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(top: 2),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 64,
            child: Text('$label：',
                style: const TextStyle(fontSize: 12, color: AppColors.inkSoft)),
          ),
          Expanded(
            child: Text(value, style: const TextStyle(fontSize: 12)),
          ),
        ],
      ),
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
                      onPressed: () {},
                      style: TextButton.styleFrom(
                        padding: EdgeInsets.zero,
                        minimumSize: const Size(48, 28),
                        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                        foregroundColor: AppColors.accent,
                      ),
                      child: const Text('去看看', style: TextStyle(fontSize: 12)),
                    ),
                    const SizedBox(width: 12),
                    TextButton(
                      onPressed: () {},
                      style: TextButton.styleFrom(
                        padding: EdgeInsets.zero,
                        minimumSize: const Size(48, 28),
                        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                        foregroundColor: AppColors.inkSoft,
                      ),
                      child: const Text('比价详情', style: TextStyle(fontSize: 12)),
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
    return Container(
      width: 88,
      height: 88,
      decoration: BoxDecoration(
        color: AppColors.panelSoft,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: AppColors.line),
      ),
      child: Stack(
        children: [
          Center(
            child: Icon(_productIcon(product),
                size: 30, color: AppColors.inkSoft.withAlpha(180)),
          ),
          Positioned(
            left: 6,
            bottom: 6,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
              decoration: BoxDecoration(
                color: Colors.white.withAlpha(230),
                borderRadius: BorderRadius.circular(4),
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
    if (priceNote != null) tags.add(priceNote);
    if (product.originalPrice > product.price) tags.add('有优惠');
    if (_afterSaleText(product) == '官方售后') {
      tags.add('官方售后');
    } else if (_shippingText(product) == '包邮') {
      tags.add('包邮');
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
          const SizedBox(height: 8),
          if (stats.isEmpty)
            const Text('暂无可比价平台',
                style: TextStyle(fontSize: 12, color: AppColors.inkSoft))
          else
            ...stats.entries.map((e) {
              final s = e.value as Map<String, dynamic>;
              final lowest =
                  (s['lowestPrice'] as num?)?.toStringAsFixed(0) ?? '-';
              final avg = (s['averagePrice'] as num?)?.toStringAsFixed(0);
              final highlight = s['highlight'] as String?;
              return Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      _platformBadge(s['platform'] as String? ?? e.key),
                      const Spacer(),
                      Text('最低 ¥$lowest',
                          style: const TextStyle(
                              fontSize: 13,
                              fontWeight: FontWeight.w600,
                              color: AppColors.priceRed)),
                      if (avg != null) ...[
                        const SizedBox(width: 8),
                        Text('均价 ¥$avg',
                            style: const TextStyle(
                                fontSize: 11, color: AppColors.inkSoft)),
                      ],
                      const SizedBox(width: 8),
                      Text('${s['productCount'] ?? 0}件',
                          style: const TextStyle(
                              fontSize: 11, color: AppColors.inkSoft)),
                    ]),
                    if (highlight != null && highlight.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 2, left: 2),
                        child: Text(highlight,
                            style: const TextStyle(
                                fontSize: 10, color: AppColors.inkSoft)),
                      ),
                  ],
                ),
              );
            }),
        ],
      ),
    );
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

class _AttrRow {
  final TextEditingController keyCtrl;
  final TextEditingController valueCtrl;

  _AttrRow({required this.keyCtrl, required this.valueCtrl});
}
