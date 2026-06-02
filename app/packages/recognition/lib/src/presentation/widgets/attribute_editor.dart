import 'package:app_core/app_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/recognition_provider.dart';

class AttributeEditor extends ConsumerStatefulWidget {
  const AttributeEditor({super.key});

  @override
  ConsumerState<AttributeEditor> createState() => _AttributeEditorState();
}

class _AttributeEditorState extends ConsumerState<AttributeEditor> {
  late TextEditingController _categoryController;
  late TextEditingController _brandController;
  late TextEditingController _modelController;
  final Map<String, TextEditingController> _attrControllers = {};
  String? _recognitionId;

  @override
  void initState() {
    super.initState();
    final state = ref.read(recognitionProvider);
    _recognitionId = state.recognition?.recognitionId;
    _categoryController =
        TextEditingController(text: state.recognition?.category ?? '');
    _brandController =
        TextEditingController(text: state.recognition?.brand ?? '');
    _modelController =
        TextEditingController(text: state.recognition?.model ?? '');
    _syncAttrControllers(state);
  }

  void _syncIdentityControllers(RecognitionState state) {
    final nextId = state.recognition?.recognitionId;
    if (nextId == null || nextId == _recognitionId) return;
    _recognitionId = nextId;
    _categoryController.text = state.recognition?.category ?? '';
    _brandController.text = state.recognition?.brand ?? '';
    _modelController.text = state.recognition?.model ?? '';
    for (final controller in _attrControllers.values) {
      controller.dispose();
    }
    _attrControllers.clear();
  }

  void _syncAttrControllers(RecognitionState state) {
    for (final entry in state.editingAttributes.entries) {
      _attrControllers.putIfAbsent(
        entry.key,
        () => TextEditingController(text: entry.value.toString()),
      );
    }
  }

  @override
  void dispose() {
    _categoryController.dispose();
    _brandController.dispose();
    _modelController.dispose();
    for (final c in _attrControllers.values) {
      c.dispose();
    }
    super.dispose();
  }

  void _onSave() {
    final notifier = ref.read(recognitionProvider.notifier);
    notifier.setCategory(_categoryController.text.trim());
    notifier.setBrand(_brandController.text.trim());
    notifier.setModel(_modelController.text.trim());
    for (final entry in _attrControllers.entries) {
      notifier.setAttribute(entry.key, entry.value.text.trim());
    }
    notifier.submitAttributeUpdates();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(recognitionProvider);
    final isUpdating = state.status == RecognitionStatus.updating;
    _syncIdentityControllers(state);
    _syncAttrControllers(state);

    return Container(
      decoration: BoxDecoration(
        color: AppColors.panel,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.line),
      ),
      child: Theme(
        data: Theme.of(context).copyWith(dividerColor: const Color(0x00000000)),
        child: ExpansionTile(
          tilePadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
          childrenPadding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
          iconColor: AppColors.inkSoft,
          collapsedIconColor: AppColors.inkSoft,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
          collapsedShape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
          leading: Container(
            width: 34,
            height: 34,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: AppColors.panelSoft,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: AppColors.line),
            ),
            child: const Icon(Icons.edit_outlined,
                size: 20, color: AppColors.inkSoft),
          ),
          title: Text('纠正识别结果', style: Theme.of(context).textTheme.titleSmall),
          subtitle: Text(
            '类目、品牌、型号或属性不准时再修改',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          children: [
            _EditorField(label: '类目', controller: _categoryController),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                    child: _EditorField(
                        label: '品牌', controller: _brandController)),
                const SizedBox(width: 10),
                Expanded(
                    child: _EditorField(
                        label: '型号', controller: _modelController)),
              ],
            ),
            if (state.editingAttributes.isNotEmpty) ...[
              const SizedBox(height: 14),
              Row(
                children: [
                  Text('补充属性', style: Theme.of(context).textTheme.labelMedium),
                  const Expanded(child: Divider(indent: 10)),
                ],
              ),
              const SizedBox(height: 10),
              ...state.editingAttributes.entries.map(
                (entry) => Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: _EditorField(
                    label: entry.key,
                    controller: _attrControllers[entry.key]!,
                  ),
                ),
              ),
            ],
            const SizedBox(height: 4),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: isUpdating ? null : _onSave,
                icon: isUpdating
                    ? const SizedBox(
                        height: 16,
                        width: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.check, size: 18),
                label: Text(isUpdating ? '保存中' : '保存纠正'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _EditorField extends StatelessWidget {
  final String label;
  final TextEditingController controller;

  const _EditorField({required this.label, required this.controller});

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      decoration: InputDecoration(
        labelText: label,
        isDense: true,
      ),
    );
  }
}
