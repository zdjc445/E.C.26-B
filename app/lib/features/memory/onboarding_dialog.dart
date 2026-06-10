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
  final _factors = <String>{};

  static const _allPlatforms = ['拼多多', '淘宝', '天猫', '京东'];
  static const _allFactors = {
    'low_price': '低价优先',
    'high_rating': '评分高',
    'official_store': '官方/自营',
    'after_sale': '售后保障',
    'fast_delivery': '配送速度',
    'brand_match': '偏好品牌',
  };

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Row(children: [
        Icon(Icons.tune, size: 20, color: AppColors.accent),
        SizedBox(width: 8),
        Text('个性化购物偏好'),
      ]),
      content: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 420, maxHeight: 420),
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                '可跳过，后续也能在我的偏好中修改。',
                style: TextStyle(
                  fontSize: 13,
                  height: 1.4,
                  color: AppColors.inkSoft,
                ),
              ),
              const SizedBox(height: 18),
              _sectionTitle('你买东西更看重什么？'),
              _buildFactorChips(),
              const SizedBox(height: 18),
              _sectionTitle('常用平台'),
              _buildPlatformChips(),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: _skip,
          child: const Text('跳过'),
        ),
        ElevatedButton(
          onPressed: _save,
          style: ElevatedButton.styleFrom(backgroundColor: AppColors.accent),
          child: const Text('保存偏好'),
        ),
      ],
    );
  }

  Widget _sectionTitle(String text) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Text(
        text,
        style: const TextStyle(
          fontSize: 14,
          fontWeight: FontWeight.w700,
          color: AppColors.inkMain,
        ),
      ),
    );
  }

  Widget _buildFactorChips() {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: _allFactors.entries
          .map((e) => _filterChip(
                label: e.value,
                selected: _factors.contains(e.key),
                onSelected: (v) => setState(
                  () => v ? _factors.add(e.key) : _factors.remove(e.key),
                ),
              ))
          .toList(),
    );
  }

  Widget _buildPlatformChips() {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        _filterChip(
          label: '不限',
          selected: _platforms.isEmpty,
          onSelected: (_) => setState(_platforms.clear),
        ),
        ..._allPlatforms.map(
          (p) => _filterChip(
            label: p,
            selected: _platforms.contains(p),
            onSelected: (v) => setState(
              () => v ? _platforms.add(p) : _platforms.remove(p),
            ),
          ),
        ),
      ],
    );
  }

  Widget _filterChip({
    required String label,
    required bool selected,
    required ValueChanged<bool> onSelected,
  }) {
    return FilterChip(
      label: Text(label),
      selected: selected,
      selectedColor: AppColors.accent.withAlpha(30),
      checkmarkColor: AppColors.accent,
      onSelected: onSelected,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(18),
      ),
    );
  }

  void _skip() {
    ref.read(memoryStoreProvider).setOnboardingDone();
    Navigator.of(context).pop();
  }

  void _save() async {
    final notifier = ref.read(userProfileProvider.notifier);
    await notifier.setPreferredPlatforms(_platforms.toList());
    await notifier.setDecisionFactors(_factors.toList());
    await ref.read(memoryStoreProvider).setOnboardingDone();
    if (mounted) Navigator.of(context).pop();
  }
}
