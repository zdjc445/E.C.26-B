import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/theme/app_theme.dart';
import 'memory_store.dart';
import 'user_profile.dart';

/// Lightweight onboarding shown once on first launch.
/// User can set basic preferences or skip entirely.
class OnboardingDialog extends ConsumerStatefulWidget {
  const OnboardingDialog({super.key});

  @override
  ConsumerState<OnboardingDialog> createState() => _OnboardingDialogState();
}

class _OnboardingDialogState extends ConsumerState<OnboardingDialog> {
  final _platforms = <String>{};
  final _categories = <String>{};
  final _factors = <String>{};
  int _step = 0;

  static const _allPlatforms = ['拼多多', '淘宝', '天猫', '京东'];
  static const _allCategories = ['运动鞋', '耳机', '数码配件', '服饰', '日用品'];
  static const _allFactors = {
    'low_price': '低价优先',
    'official_store': '官方店铺',
    'after_sale': '售后保障',
    'fast_delivery': '配送速度',
    'high_rating': '评价数量',
    'brand_match': '偏好品牌',
  };

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Row(children: [
        const Icon(Icons.tune, size: 20, color: AppColors.accent),
        const SizedBox(width: 8),
        Text(_step == 0 ? '定制你的购物偏好' : _step == 1 ? '常买品类' : '你更看重什么'),
      ]),
      content: SizedBox(
        width: double.maxFinite,
        child: _step == 0 ? _buildPlatformStep() : _step == 1 ? _buildCategoryStep() : _buildFactorStep(),
      ),
      actions: [
        TextButton(
          onPressed: _skip,
          child: Text(_step < 2 ? '跳过' : '完成'),
        ),
        if (_step < 2)
          ElevatedButton(
            onPressed: () => setState(() => _step++),
            style: ElevatedButton.styleFrom(backgroundColor: AppColors.accent),
            child: const Text('下一步'),
          )
        else
          ElevatedButton(
            onPressed: _save,
            style: ElevatedButton.styleFrom(backgroundColor: AppColors.accent),
            child: const Text('保存'),
          ),
      ],
    );
  }

  Widget _buildPlatformStep() {
    return Wrap(
      spacing: 8, runSpacing: 8,
      children: _allPlatforms.map((p) => FilterChip(
        label: Text(p),
        selected: _platforms.contains(p),
        selectedColor: AppColors.accent.withAlpha(30),
        checkmarkColor: AppColors.accent,
        onSelected: (v) => setState(() => v ? _platforms.add(p) : _platforms.remove(p)),
      )).toList(),
    );
  }

  Widget _buildCategoryStep() {
    return Wrap(
      spacing: 8, runSpacing: 8,
      children: _allCategories.map((c) => FilterChip(
        label: Text(c),
        selected: _categories.contains(c),
        selectedColor: AppColors.accent.withAlpha(30),
        checkmarkColor: AppColors.accent,
        onSelected: (v) => setState(() => v ? _categories.add(c) : _categories.remove(c)),
      )).toList(),
    );
  }

  Widget _buildFactorStep() {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: _allFactors.entries.map((e) => CheckboxListTile(
        title: Text(e.value, style: const TextStyle(fontSize: 14)),
        value: _factors.contains(e.key),
        onChanged: (v) => setState(() => v! ? _factors.add(e.key) : _factors.remove(e.key)),
        dense: true,
        contentPadding: EdgeInsets.zero,
        activeColor: AppColors.accent,
      )).toList(),
    );
  }

  void _skip() {
    ref.read(memoryStoreProvider).setOnboardingDone();
    Navigator.of(context).pop();
  }

  void _save() async {
    final notifier = ref.read(userProfileProvider.notifier);
    if (_platforms.isNotEmpty) await notifier.setPreferredPlatforms(_platforms.toList());
    if (_categories.isNotEmpty) await notifier.setPreferredCategories(_categories.toList());
    if (_factors.isNotEmpty) await notifier.setDecisionFactors(_factors.toList());
    await ref.read(memoryStoreProvider).setOnboardingDone();
    if (mounted) Navigator.of(context).pop();
  }
}
