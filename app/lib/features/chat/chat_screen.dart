import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import '../../core/theme/app_theme.dart';
import 'chat_controller.dart';
import 'chat_history_drawer.dart';
import 'chat_models.dart';

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

    final imageIds =
        _uploadedImageId != null ? [_uploadedImageId!] : null;
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

  void _onVoiceTap() {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('语音输入功能即将上线'),
        duration: Duration(seconds: 2),
      ),
    );
  }

  void _openCorrectionSheet(ReplyCard recognitionCard) {
    final recId = recognitionCard.recognitionId;
    if (recId == null) return;

    final categoryCtrl =
        TextEditingController(text: recognitionCard.category ?? '');
    final brandCtrl =
        TextEditingController(text: recognitionCard.brand ?? '');
    final modelCtrl =
        TextEditingController(text: recognitionCard.model ?? '');

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
                              final updated = await recApi.updateAttributes(
                                  recId, payload);
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
          onPressed: () =>
              _scaffoldKey.currentState?.openDrawer(),
        ),
        title: const Text('购物助手'),
        actions: [
          TextButton(
            onPressed: () => context.go('/me'),
            child: const Text('我的',
                style: TextStyle(
                    color: AppColors.accent,
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
                    padding:
                        const EdgeInsets.fromLTRB(12, 12, 12, 4),
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
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.chat_bubble_outline,
              size: 64, color: AppColors.inkSoft),
          const SizedBox(height: 16),
          Text(
            '拍照或描述你想买的东西',
            style: Theme.of(context)
                .textTheme
                .bodySmall
                ?.copyWith(fontSize: 14),
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
        children: [
          SizedBox(width: 8),
          Icon(Icons.circle, size: 6, color: AppColors.inkSoft),
          SizedBox(width: 8),
          Text('正在思考…',
              style:
                  TextStyle(fontSize: 13, color: AppColors.inkSoft)),
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
            child: Container(
              padding: const EdgeInsets.symmetric(
                  horizontal: 14, vertical: 10),
              decoration: BoxDecoration(
                color: AppColors.accent.withAlpha(20),
                borderRadius: const BorderRadius.only(
                  topLeft: Radius.circular(16),
                  topRight: Radius.circular(4),
                  bottomLeft: Radius.circular(16),
                  bottomRight: Radius.circular(16),
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  if (msg.text != null && msg.text!.isNotEmpty)
                    Text(msg.text!,
                        style: const TextStyle(
                            fontSize: 15,
                            color: AppColors.inkMain)),
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
        ],
      ),
    );
  }

  Widget _buildAssistantMessage(ChatMessage msg) {
    final reply = msg.agentReply;
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SizedBox(width: 8),
          const Icon(Icons.circle, size: 6,
              color: AppColors.inkSoft),
          const SizedBox(width: 8),
          Flexible(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (msg.text != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Text(msg.text!,
                        style: const TextStyle(
                            fontSize: 13,
                            color: AppColors.inkSoft)),
                  ),
                if (reply != null)
                  ...reply.cards.map(_buildCard),
              ],
            ),
          ),
        ],
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
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.panel,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(card.title,
              style: const TextStyle(
                  fontSize: 14, fontWeight: FontWeight.w600)),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: options.map((opt) {
              return ActionChip(
                label: Text(opt.label),
                onPressed: () =>
                    _onOptionSelected(opt.optionId),
                backgroundColor:
                    AppColors.accent.withAlpha(15),
                labelStyle: const TextStyle(
                    color: AppColors.accent),
                side: const BorderSide(
                    color: AppColors.accent),
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
                style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
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
                        fontSize: 13, fontWeight: FontWeight.w700,
                        color: card.decisionScore! >= 80 ? AppColors.good : AppColors.warn)),
              ),
          ]),
          const SizedBox(height: 8),
          if (card.productName != null)
            Text(card.productName!,
                style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w500)),
          const SizedBox(height: 4),
          if (card.platform != null || card.price != null)
            Row(children: [
              if (card.platform != null) _platformBadge(card.platform!),
              if (card.platform != null && card.price != null) const SizedBox(width: 8),
              if (card.price != null)
                Text('¥${card.price!.toStringAsFixed(2)}',
                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700,
                        color: AppColors.priceRed)),
            ]),
          if (card.reason != null) ...[
            const SizedBox(height: 6),
            Text(card.reason!,
                style: const TextStyle(fontSize: 12, color: AppColors.inkSoft)),
          ],
          // Provider status
          if (card.intentProvider != null || card.explanationProvider != null) ...[
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
          if (card.decisionSignals != null && card.decisionSignals!.isNotEmpty) ...[
            const SizedBox(height: 10),
            const Text('决策信号', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
            const SizedBox(height: 4),
            ...card.decisionSignals!.map((s) => Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: Row(children: [
                SizedBox(width: 60, child: Text(s.label,
                    style: const TextStyle(fontSize: 11, color: AppColors.inkSoft))),
                Expanded(child: ClipRRect(
                  borderRadius: BorderRadius.circular(3),
                  child: LinearProgressIndicator(
                    value: s.score / 100.0,
                    backgroundColor: AppColors.line,
                    color: _signalColor(s.score),
                    minHeight: 6,
                  ),
                )),
                const SizedBox(width: 6),
                Text('${s.score}', style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600)),
              ]),
            )),
          ],
          // Evidence
          if (card.evidence != null && card.evidence!.isNotEmpty) ...[
            const SizedBox(height: 8),
            const Text('证据摘要', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
            ...card.evidence!.map((e) => Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Row(children: [
                const Icon(Icons.check_circle_outline, size: 12, color: AppColors.good),
                const SizedBox(width: 4),
                Expanded(child: Text(e.content,
                    style: const TextStyle(fontSize: 11, color: AppColors.inkSoft))),
              ]),
            )),
          ],
          // Risks
          if (card.risks != null && card.risks!.isNotEmpty) ...[
            const SizedBox(height: 8),
            const Text('风险提示', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
            ...card.risks!.map((r) => Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Row(children: [
                const Icon(Icons.warning_amber, size: 12, color: AppColors.warn),
                const SizedBox(width: 4),
                Expanded(child: Text(r,
                    style: const TextStyle(fontSize: 11, color: AppColors.warn))),
              ]),
            )),
          ],
          // Product analyses
          if (card.productAnalyses != null && card.productAnalyses!.isNotEmpty) ...[
            const SizedBox(height: 8),
            const Text('商品对比', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
            ...card.productAnalyses!.map((a) => Container(
              margin: const EdgeInsets.only(top: 4),
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: AppColors.background,
                borderRadius: BorderRadius.circular(6),
              ),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Text('#${a.rank}', style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700)),
                  const SizedBox(width: 6),
                  _platformBadge(a.platform),
                  const Spacer(),
                  Text('${a.score}分', style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600)),
                ]),
                const SizedBox(height: 2),
                if (a.strengths.isNotEmpty)
                  Text('优势：${a.strengths.join("、")}',
                      style: const TextStyle(fontSize: 11, color: AppColors.good)),
                if (a.weaknesses.isNotEmpty)
                  Text('不足：${a.weaknesses.join("、")}',
                      style: const TextStyle(fontSize: 11, color: AppColors.warn)),
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
        color: fallback ? AppColors.warn.withAlpha(20) : AppColors.accent.withAlpha(15),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Text(label, style: TextStyle(fontSize: 10,
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
              const Icon(Icons.image_search, size: 18,
                  color: AppColors.accent),
              const SizedBox(width: 6),
              Text(card.title,
                  style: const TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w600)),
            ],
          ),
          const SizedBox(height: 8),
          if (card.category != null)
            _recognitionRow('类别', card.category!),
          if (card.brand != null)
            _recognitionRow('品牌', card.brand!),
          if (card.model != null)
            _recognitionRow('型号', card.model!),
          if (card.keywords != null && card.keywords!.isNotEmpty)
            _recognitionRow(
                '关键词', card.keywords!.join('、')),
          if (card.attributes != null &&
              card.attributes!.isNotEmpty)
            _recognitionRow(
                '属性',
                card.attributes!.entries
                    .map((e) => '${e.key}: ${e.value}')
                    .join('；')),
          if (card.confidence != null)
            _recognitionRow(
                '置信度',
                (card.confidence! * 100).toStringAsFixed(0) +
                    '%'),
          if (card.aiProvider != null)
            _recognitionRow('AI Provider', card.aiProvider!),
          if (card.fallbackUsed == true)
            const Text('已回退到 Mock 识别',
                style: TextStyle(
                    fontSize: 11,
                    color: AppColors.warn)),
          if (card.explanation != null &&
              card.explanation!.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(card.explanation!,
                  style: const TextStyle(
                      fontSize: 11,
                      color: AppColors.inkSoft)),
            ),
          const SizedBox(height: 8),
          Align(
            alignment: Alignment.centerRight,
            child: TextButton.icon(
              onPressed: () => _openCorrectionSheet(card),
              icon: const Icon(Icons.edit, size: 14),
              label: const Text('修正识别结果',
                  style: TextStyle(fontSize: 12)),
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
                style: const TextStyle(
                    fontSize: 12, color: AppColors.inkSoft)),
          ),
          Expanded(
            child: Text(value,
                style: const TextStyle(fontSize: 12)),
          ),
        ],
      ),
    );
  }

  // ── Product cards ──────────────────────────────────────────

  Widget _buildProductListCard(ReplyCard card) {
    final products = card.products ?? [];
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
            const Icon(Icons.list_alt, size: 18, color: AppColors.accent),
            const SizedBox(width: 6),
            Text(card.title,
                style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
          ]),
          const SizedBox(height: 8),
          if (products.isEmpty)
            const Text('暂无符合条件的商品',
                style: TextStyle(fontSize: 12, color: AppColors.inkSoft))
          else
            ...products.map((p) => _buildProductRow(p)),
        ],
      ),
    );
  }

  Widget _buildProductRow(ProductItem p) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(
        color: AppColors.background,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: AppColors.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(p.title, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500)),
          const SizedBox(height: 4),
          Row(children: [
            _platformBadge(p.platform),
            const SizedBox(width: 8),
            Text('¥${p.price.toStringAsFixed(0)}',
                style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: AppColors.priceRed)),
            if (p.originalPrice > p.price) ...[
              const SizedBox(width: 4),
              Text('¥${p.originalPrice.toStringAsFixed(0)}',
                  style: const TextStyle(fontSize: 11, color: AppColors.inkSoft, decoration: TextDecoration.lineThrough)),
            ],
          ]),
          const SizedBox(height: 2),
          Row(children: [
            Text(p.shopName, style: const TextStyle(fontSize: 11, color: AppColors.inkSoft)),
            const SizedBox(width: 8),
            _ratingStars(p.rating),
            const SizedBox(width: 4),
            Text('${p.rating}', style: const TextStyle(fontSize: 11, color: AppColors.inkSoft)),
            const SizedBox(width: 8),
            Text('已售${p.sales > 9999 ? '${(p.sales / 10000).toStringAsFixed(1)}万' : '${p.sales}'}',
                style: const TextStyle(fontSize: 11, color: AppColors.inkSoft)),
          ]),
          if (p.tags.isNotEmpty) ...[
            const SizedBox(height: 4),
            Wrap(spacing: 4, children: p.tags.map((t) => Container(
              padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
              decoration: BoxDecoration(color: AppColors.accent.withAlpha(15), borderRadius: BorderRadius.circular(3)),
              child: Text(t, style: const TextStyle(fontSize: 9, color: AppColors.accent)),
            )).toList()),
          ],
        ],
      ),
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
            Text(card.title, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
          ]),
          const SizedBox(height: 8),
          if (stats.isEmpty)
            const Text('暂无可比价平台',
                style: TextStyle(fontSize: 12, color: AppColors.inkSoft))
          else
            ...stats.entries.map((e) {
            final s = e.value as Map<String, dynamic>;
            return Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(children: [
                _platformBadge(s['platform'] as String? ?? e.key),
                const Spacer(),
                Text('最低 ¥${(s['lowestPrice'] as num?)?.toStringAsFixed(0) ?? '-'}',
                    style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: AppColors.priceRed)),
                const SizedBox(width: 8),
                Text('${s['productCount'] ?? 0}件',
                    style: const TextStyle(fontSize: 11, color: AppColors.inkSoft)),
              ]),
            );
          }),
        ],
      ),
    );
  }

  Widget _platformBadge(String platform) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
      decoration: BoxDecoration(color: AppColors.background, borderRadius: BorderRadius.circular(4)),
      child: Text(platform, style: const TextStyle(fontSize: 10, color: AppColors.inkSoft)),
    );
  }

  Widget _ratingStars(double rating) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: List.generate(5, (i) => Icon(
        i < rating.round() ? Icons.star : Icons.star_border,
        size: 11, color: i < rating.round() ? AppColors.warn : AppColors.line,
      )),
    );
  }

  // ── Input bar ───────────────────────────────────────────────

  Widget _buildInputBar() {
    final sending = ref.watch(chatControllerProvider).sending;

    return Container(
      padding: const EdgeInsets.fromLTRB(8, 8, 8, 12),
      decoration: const BoxDecoration(
        color: AppColors.panel,
        border:
            Border(top: BorderSide(color: AppColors.line)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (_pendingImage != null)
            Padding(
              padding:
                  const EdgeInsets.only(bottom: 8, left: 4),
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
                        child: CircularProgressIndicator(
                            strokeWidth: 2)),
                  const Spacer(),
                  IconButton(
                    icon: const Icon(Icons.close, size: 18),
                    onPressed: () => setState(() {
                      _pendingImage = null;
                      _uploadedImageId = null;
                      _imageUploadFailed = false;
                    }),
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(
                        minWidth: 32, minHeight: 32),
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
                constraints: const BoxConstraints(
                    minWidth: 40, minHeight: 40),
              ),
              IconButton(
                icon: const Icon(Icons.mic_none, size: 22),
                color: AppColors.inkSoft,
                onPressed: _onVoiceTap,
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(
                    minWidth: 40, minHeight: 40),
              ),
              Expanded(
                child: TextField(
                  controller: _textController,
                  decoration: InputDecoration(
                    hintText: '描述你想买的商品…',
                    border: OutlineInputBorder(
                      borderRadius:
                          BorderRadius.circular(20),
                      borderSide: const BorderSide(
                          color: AppColors.line),
                    ),
                    enabledBorder: OutlineInputBorder(
                      borderRadius:
                          BorderRadius.circular(20),
                      borderSide: const BorderSide(
                          color: AppColors.line),
                    ),
                    focusedBorder: OutlineInputBorder(
                      borderRadius:
                          BorderRadius.circular(20),
                      borderSide: const BorderSide(
                          color: AppColors.accent),
                    ),
                    contentPadding:
                        const EdgeInsets.symmetric(
                            horizontal: 16, vertical: 10),
                    isDense: true,
                    filled: true,
                    fillColor: AppColors.background,
                  ),
                  textInputAction: TextInputAction.send,
                  onSubmitted: (_) => _sendMessage(),
                ),
              ),
              IconButton(
                icon: const Icon(Icons.send, size: 20),
                color: sending
                    ? AppColors.inkSoft
                    : AppColors.accent,
                onPressed: sending ? null : _sendMessage,
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(
                    minWidth: 40, minHeight: 40),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _AttrRow {
  final TextEditingController keyCtrl;
  final TextEditingController valueCtrl;

  _AttrRow({required this.keyCtrl, required this.valueCtrl});
}
