import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_theme.dart';
import 'chat_controller.dart';
import 'chat_models.dart';

class RecognitionDetailScreen extends ConsumerStatefulWidget {
  final ReplyCard recognitionCard;
  final String? imagePath;

  const RecognitionDetailScreen({
    super.key,
    required this.recognitionCard,
    this.imagePath,
  });

  @override
  ConsumerState<RecognitionDetailScreen> createState() =>
      _RecognitionDetailScreenState();
}

class _RecognitionDetailScreenState
    extends ConsumerState<RecognitionDetailScreen> {
  late final TextEditingController _categoryCtrl;
  late final TextEditingController _brandCtrl;
  late final TextEditingController _modelCtrl;
  final List<_AttrRow> _attrEntries = <_AttrRow>[];
  bool _saving = false;

  ReplyCard get _card => widget.recognitionCard;

  bool get _canSave {
    final recId = _card.recognitionId;
    return recId != null && recId.isNotEmpty;
  }

  @override
  void initState() {
    super.initState();
    _categoryCtrl = TextEditingController(text: _card.category ?? '');
    _brandCtrl = TextEditingController(text: _card.brand ?? '');
    _modelCtrl = TextEditingController(text: _card.model ?? '');

    final attrs = _card.attributes;
    if (attrs != null) {
      attrs.forEach((k, v) {
        _attrEntries.add(_AttrRow(
          keyCtrl: TextEditingController(text: k.toString()),
          valueCtrl: TextEditingController(text: v.toString()),
        ));
      });
    }
  }

  @override
  void dispose() {
    _categoryCtrl.dispose();
    _brandCtrl.dispose();
    _modelCtrl.dispose();
    for (final entry in _attrEntries) {
      entry.dispose();
    }
    super.dispose();
  }

  Future<void> _save() async {
    final recId = _card.recognitionId;
    if (recId == null || recId.isEmpty || _saving) return;

    final attrs = <String, dynamic>{};
    for (final entry in _attrEntries) {
      final key = entry.keyCtrl.text.trim();
      if (key.isEmpty) continue;
      attrs[key] = entry.valueCtrl.text.trim();
    }
    final payload = {
      'category': _categoryCtrl.text,
      'brand': _brandCtrl.text,
      'model': _modelCtrl.text,
      'attributes': attrs,
    };

    final navigator = Navigator.of(context);
    final messenger = ScaffoldMessenger.of(context);
    setState(() {
      _saving = true;
    });
    try {
      final updated = await ref
          .read(recognitionApiProvider)
          .updateAttributes(recId, payload);
      if (!mounted) return;
      ref
          .read(chatControllerProvider.notifier)
          .updateRecognitionCard(recId, updated);
      navigator.pop();
      messenger.showSnackBar(
        const SnackBar(content: Text('识别结果已更新')),
      );
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _saving = false;
      });
      messenger.showSnackBar(
        const SnackBar(content: Text('修正失败，请重试')),
      );
    }
  }

  void _addAttribute() {
    setState(() {
      _attrEntries.add(_AttrRow(
        keyCtrl: TextEditingController(),
        valueCtrl: TextEditingController(),
      ));
    });
  }

  void _removeAttribute(int index) {
    final entry = _attrEntries.removeAt(index);
    entry.dispose();
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      key: const Key('recognition_detail_page'),
      backgroundColor: AppColors.chatBackground,
      appBar: AppBar(
        title: const Text('识别结果详情'),
      ),
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 20),
                children: [
                  _buildSummary(),
                  const SizedBox(height: 14),
                  _buildPrimaryFields(),
                  const SizedBox(height: 14),
                  _buildAttributes(),
                  if (!_canSave) ...[
                    const SizedBox(height: 12),
                    const Text(
                      '当前识别结果缺少记录 ID，只能查看，不能保存修改。',
                      style: TextStyle(fontSize: 12, color: AppColors.inkSoft),
                    ),
                  ],
                ],
              ),
            ),
            _buildActions(),
          ],
        ),
      ),
    );
  }

  Widget _buildSummary() {
    final category = _card.category?.trim();
    final title = category != null && category.isNotEmpty ? category : '未知商品';
    final badges = <Widget>[
      _metaBadge(_confidenceText(_card)),
    ];
    if (_card.brand != null && _card.brand!.isNotEmpty) {
      badges.add(_metaBadge('品牌：${_card.brand}'));
    }
    if (_card.model != null && _card.model!.isNotEmpty) {
      badges.add(_metaBadge('型号：${_card.model}'));
    }
    if (_card.aiProvider != null && _card.aiProvider!.isNotEmpty) {
      badges.add(_metaBadge('来源：${_card.aiProvider}'));
    }

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.panel,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.accent.withAlpha(60)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _thumb(),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  '当前识别结果',
                  style: TextStyle(
                    fontSize: 12,
                    color: AppColors.inkSoft,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 5),
                Text(
                  '识别到：$title',
                  style: const TextStyle(
                    fontSize: 17,
                    height: 1.3,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 8),
                Wrap(spacing: 6, runSpacing: 6, children: badges),
                if (_card.fallbackUsed == true) ...[
                  const SizedBox(height: 8),
                  const Text(
                    '已回退到 Mock 识别',
                    style: TextStyle(fontSize: 12, color: AppColors.warn),
                  ),
                ],
                if (_card.explanation != null &&
                    _card.explanation!.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Text(
                    _card.explanation!,
                    style: const TextStyle(
                      fontSize: 12,
                      height: 1.4,
                      color: AppColors.inkSoft,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPrimaryFields() {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.panel,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            '基础信息',
            style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 10),
          TextField(
            controller: _categoryCtrl,
            decoration: const InputDecoration(labelText: '商品类别'),
          ),
          const SizedBox(height: 8),
          TextField(
            controller: _brandCtrl,
            decoration: const InputDecoration(labelText: '品牌'),
          ),
          const SizedBox(height: 8),
          TextField(
            controller: _modelCtrl,
            decoration: const InputDecoration(labelText: '型号'),
          ),
        ],
      ),
    );
  }

  Widget _buildAttributes() {
    return Container(
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
              const Text(
                '属性',
                style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
              ),
              const Spacer(),
              TextButton.icon(
                onPressed: _saving ? null : _addAttribute,
                icon: const Icon(Icons.add, size: 16),
                label: const Text('新增属性'),
              ),
            ],
          ),
          if (_attrEntries.isEmpty)
            const Padding(
              padding: EdgeInsets.only(top: 8),
              child: Text(
                '暂无属性，可手动新增。',
                style: TextStyle(fontSize: 12, color: AppColors.inkSoft),
              ),
            ),
          ...List.generate(_attrEntries.length, (index) {
            final entry = _attrEntries[index];
            return Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Row(
                children: [
                  SizedBox(
                    width: 88,
                    child: TextField(
                      controller: entry.keyCtrl,
                      enabled: !_saving,
                      decoration: const InputDecoration(
                        hintText: 'key',
                        isDense: true,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: TextField(
                      controller: entry.valueCtrl,
                      enabled: !_saving,
                      decoration: const InputDecoration(
                        hintText: 'value',
                        isDense: true,
                      ),
                    ),
                  ),
                  IconButton(
                    tooltip: '删除属性',
                    icon: const Icon(Icons.close, size: 18),
                    color: AppColors.inkSoft,
                    onPressed: _saving ? null : () => _removeAttribute(index),
                  ),
                ],
              ),
            );
          }),
        ],
      ),
    );
  }

  Widget _buildActions() {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 10, 16, 12),
      decoration: const BoxDecoration(
        color: AppColors.panel,
        border: Border(top: BorderSide(color: AppColors.line)),
      ),
      child: Row(
        children: [
          Expanded(
            child: OutlinedButton(
              onPressed: _saving ? null : () => Navigator.of(context).pop(),
              child: const Text('取消'),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: ElevatedButton(
              onPressed: _canSave && !_saving ? _save : null,
              child: Text(_saving ? '保存中...' : '保存'),
            ),
          ),
        ],
      ),
    );
  }

  Widget _thumb() {
    final imagePath = widget.imagePath;
    if (imagePath != null && File(imagePath).existsSync()) {
      return ClipRRect(
        borderRadius: BorderRadius.circular(8),
        child: Image.file(
          File(imagePath),
          key: const Key('recognition_detail_image_thumb'),
          width: 88,
          height: 88,
          fit: BoxFit.cover,
          errorBuilder: (_, __, ___) => _thumbPlaceholder(),
        ),
      );
    }
    return _thumbPlaceholder();
  }

  Widget _thumbPlaceholder() {
    return Container(
      key: const Key('recognition_detail_image_placeholder'),
      width: 88,
      height: 88,
      decoration: BoxDecoration(
        color: AppColors.panelSoft,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.line),
      ),
      child: const Center(
        child: Icon(Icons.image_search, size: 30, color: AppColors.inkSoft),
      ),
    );
  }

  Widget _metaBadge(String label) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 4),
      decoration: BoxDecoration(
        color: AppColors.panelSoft,
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: AppColors.line),
      ),
      child: Text(
        label,
        style: const TextStyle(fontSize: 11, color: AppColors.inkSoft),
      ),
    );
  }

  String _confidenceText(ReplyCard card) {
    if (card.confidence == null) return '置信度 --';
    return '置信度 ${(card.confidence! * 100).toStringAsFixed(0)}%';
  }
}

class _AttrRow {
  final TextEditingController keyCtrl;
  final TextEditingController valueCtrl;

  _AttrRow({required this.keyCtrl, required this.valueCtrl});

  void dispose() {
    keyCtrl.dispose();
    valueCtrl.dispose();
  }
}
