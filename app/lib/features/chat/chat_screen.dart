import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';
import '../../core/theme/app_theme.dart';
import 'chat_controller.dart';
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
  File? _pendingImage;
  String? _uploadedImageId;
  bool _imageUploadFailed = false;

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
    final hasPendingImageUpload = _pendingImage != null && _uploadedImageId == null;
    if (hasPendingImageUpload) {
      return;
    }
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

  Future<void> _pickImage() async {
    final picked = await _picker.pickImage(source: ImageSource.gallery);
    if (picked == null) return;

    setState(() {
      _pendingImage = File(picked.path);
      _uploadedImageId = null;
      _imageUploadFailed = false;
    });

    final imageId =
        await ref.read(chatControllerProvider.notifier).uploadImage(File(picked.path));
    if (mounted) {
      setState(() {
        _uploadedImageId = imageId;
        _imageUploadFailed = imageId == null;
      });
    }
  }

  void _onVoiceTap() {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('语音输入功能即将上线'),
        duration: Duration(seconds: 2),
      ),
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
      backgroundColor: AppColors.background,
      appBar: AppBar(title: const Text('购物助手')),
      body: Column(
        children: [
          Expanded(
            child: messages.isEmpty
                ? _buildEmpty()
                : ListView.builder(
                    controller: _scrollController,
                    padding: const EdgeInsets.fromLTRB(12, 12, 12, 4),
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
    if (msg.isLoading) {
      return _buildLoadingBubble();
    }
    if (msg.role == ChatRole.user) {
      return _buildUserMessage(msg);
    }
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
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
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
                            fontSize: 15, color: AppColors.inkMain)),
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
          const Icon(Icons.circle, size: 6, color: AppColors.inkSoft),
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
                            fontSize: 13, color: AppColors.inkSoft)),
                  ),
                if (reply != null) ...reply.cards.map(_buildCard),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCard(ReplyCard card) {
    if (card.cardType == 'clarification') {
      return _buildClarificationCard(card);
    }
    if (card.cardType == 'recommendation') {
      return _buildRecommendationCard(card);
    }
    return const SizedBox.shrink();
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
                onPressed: () => _onOptionSelected(opt.optionId),
                backgroundColor: AppColors.accent.withAlpha(15),
                labelStyle: const TextStyle(color: AppColors.accent),
                side: const BorderSide(color: AppColors.accent),
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
        border: Border.all(color: AppColors.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.recommend, size: 18, color: AppColors.accent),
              const SizedBox(width: 6),
              Text(card.title,
                  style: const TextStyle(
                      fontSize: 14, fontWeight: FontWeight.w600)),
            ],
          ),
          const SizedBox(height: 8),
          if (card.productName != null)
            Text(card.productName!,
                style: const TextStyle(
                    fontSize: 15, fontWeight: FontWeight.w500)),
          const SizedBox(height: 4),
          if (card.platform != null || card.price != null)
            Row(
              children: [
                if (card.platform != null)
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
                    decoration: BoxDecoration(
                      color: AppColors.background,
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(card.platform!,
                        style: const TextStyle(
                            fontSize: 10, color: AppColors.inkSoft)),
                  ),
                if (card.platform != null && card.price != null)
                  const SizedBox(width: 8),
                if (card.price != null)
                  Text('¥${card.price!.toStringAsFixed(2)}',
                      style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                          color: AppColors.priceRed)),
              ],
            ),
          if (card.reason != null) ...[
            const SizedBox(height: 6),
            Text(card.reason!,
                style: const TextStyle(
                    fontSize: 12, color: AppColors.inkSoft)),
          ],
        ],
      ),
    );
  }

  // ── Input bar ───────────────────────────────────────────────

  Widget _buildInputBar() {
    final sending = ref.watch(chatControllerProvider).sending;
    final waitingForImageUpload =
        _pendingImage != null && _uploadedImageId == null;

    return Container(
      padding: const EdgeInsets.fromLTRB(8, 8, 8, 12),
      decoration: const BoxDecoration(
        color: AppColors.panel,
        border: Border(top: BorderSide(color: AppColors.line)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Image preview
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
                    const Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.error_outline,
                            size: 16, color: AppColors.priceRed),
                        SizedBox(width: 4),
                        Text('上传失败',
                            style: TextStyle(
                                fontSize: 12, color: AppColors.priceRed)),
                      ],
                    )
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
          // Input row
          Row(
            children: [
              IconButton(
                icon: const Icon(Icons.image_outlined, size: 22),
                color: AppColors.inkSoft,
                onPressed: sending ? null : _pickImage,
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
                  decoration: InputDecoration(
                    hintText: '描述你想买的商品…',
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(20),
                      borderSide: const BorderSide(color: AppColors.line),
                    ),
                    enabledBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(20),
                      borderSide: const BorderSide(color: AppColors.line),
                    ),
                    focusedBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(20),
                      borderSide:
                          const BorderSide(color: AppColors.accent),
                    ),
                    contentPadding: const EdgeInsets.symmetric(
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
                color: sending || waitingForImageUpload
                    ? AppColors.inkSoft
                    : AppColors.accent,
                onPressed:
                    sending || waitingForImageUpload ? null : _sendMessage,
                padding: EdgeInsets.zero,
                constraints:
                    const BoxConstraints(minWidth: 40, minHeight: 40),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
