import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/theme/app_theme.dart';
import 'behavior_events.dart';
import 'memory_store.dart';
import 'user_profile.dart';

/// Full preferences management page at /preferences.
class PreferencesScreen extends ConsumerWidget {
  const PreferencesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final profile = ref.watch(userProfileProvider);
    final store = ref.watch(memoryStoreProvider);

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(title: const Text('我的偏好')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // ── Personalization toggle ──
          _section('个性化推荐'),
          Card(
            child: SwitchListTile(
              title: const Text('启用个性化推荐'),
              subtitle: Text(profile.personalizationEnabled
                  ? '根据你的偏好和浏览行为优化排序'
                  : '关闭后将不再使用偏好影响推荐'),
              value: profile.personalizationEnabled,
              activeColor: AppColors.accent,
              onChanged: (v) =>
                  ref.read(userProfileProvider.notifier).setPersonalizationEnabled(v),
            ),
          ),
          const SizedBox(height: 12),

          // ── Explicit preferences ──
          _section('你主动设置的偏好'),
          Card(
            child: Column(
              children: [
                _editTile(
                  icon: Icons.store,
                  title: '常用平台',
                  value: profile.preferredPlatforms.isEmpty
                      ? '未设置'
                      : profile.preferredPlatforms.join('、'),
                  onTap: () => _editPlatforms(context, ref),
                ),
                const Divider(height: 1),
                _editTile(
                  icon: Icons.category,
                  title: '常买品类',
                  value: profile.preferredCategories.isEmpty
                      ? '未设置'
                      : profile.preferredCategories.join('、'),
                  onTap: () => _editCategories(context, ref),
                ),
                const Divider(height: 1),
                _editTile(
                  icon: Icons.trending_up,
                  title: '更看重',
                  value: profile.decisionFactors.isEmpty
                      ? '未设置'
                      : profile.decisionFactors.map(_factorLabel).join('、'),
                  onTap: () => _editFactors(context, ref),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),

          // ── Inferred preferences ──
          _section('根据使用行为推断的偏好'),
          if (_hasNoInferred(profile))
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Text(
                  '使用一段时间后，这里会根据你的浏览和搜索行为自动推断偏好。',
                  style: const TextStyle(fontSize: 13, color: AppColors.inkSoft),
                ),
              ),
            )
          else
            Card(
              child: Column(
                children: [
                  if (profile.inferredCategories.isNotEmpty)
                    _inferredRow(
                      '常看品类', profile.inferredCategories,
                      onDelete: (v) => ref.read(userProfileProvider.notifier).removeInferredCategory(v),
                    ),
                  if (profile.inferredPlatforms.isNotEmpty) ...[
                    const Divider(height: 1),
                    _inferredRow(
                      '常用平台', profile.inferredPlatforms,
                      onDelete: (v) => ref.read(userProfileProvider.notifier).removeInferredPlatform(v),
                    ),
                  ],
                  if (profile.inferredBrands.isNotEmpty) ...[
                    const Divider(height: 1),
                    _inferredRow(
                      '偏好品牌', profile.inferredBrands,
                      onDelete: (v) => ref.read(userProfileProvider.notifier).removeInferredBrand(v),
                    ),
                  ],
                  if (profile.inferredPriceMin != null) ...[
                    const Divider(height: 1),
                    _inferredRow(
                      '常看价格区间',
                      ['¥${profile.inferredPriceMin!.round()} - ¥${profile.inferredPriceMax!.round()}'],
                      onDelete: (_) {},
                      showDelete: false,
                    ),
                  ],
                ],
              ),
            ),
          const SizedBox(height: 12),

          // ── Privacy ──
          _section('隐私与数据'),
          Card(
            child: Column(
              children: [
                ListTile(
                  leading: const Icon(Icons.security_outlined, color: AppColors.inkSoft),
                  title: const Text('隐私说明'),
                  subtitle: const Text('原始行为留在本地，偏好画像用于推荐排序'),
                  onTap: () => _showPrivacy(context),
                ),
                const Divider(height: 1),
                ListTile(
                  leading: const Icon(Icons.delete_outline, color: AppColors.priceRed),
                  title: const Text('清空所有记忆'),
                  subtitle: const Text('删除所有偏好设置和行为记录'),
                  onTap: () => _confirmClear(context, ref, store),
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),
        ],
      ),
    );
  }

  // ── Section header ─────────────────────────────────────────

  Widget _section(String title) {
    return Padding(
      padding: const EdgeInsets.only(left: 2, bottom: 8),
      child: Text(title,
          style: const TextStyle(
              fontSize: 13, fontWeight: FontWeight.w600, color: AppColors.inkSoft)),
    );
  }

  // ── Editable tile ──────────────────────────────────────────

  Widget _editTile({required IconData icon, required String title, required String value, required VoidCallback onTap}) {
    return ListTile(
      leading: Icon(icon, color: AppColors.accent),
      title: Text(title, style: const TextStyle(fontSize: 14)),
      subtitle: Text(value, style: const TextStyle(fontSize: 12, color: AppColors.inkSoft)),
      trailing: const Icon(Icons.chevron_right, color: AppColors.inkSoft),
      onTap: onTap,
    );
  }

  // ── Inferred row with delete ───────────────────────────────

  Widget _inferredRow(String label, List<String> items,
      {required void Function(String) onDelete, bool showDelete = true}) {
    return Padding(
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: const TextStyle(fontSize: 12, color: AppColors.inkSoft)),
          const SizedBox(height: 6),
          Wrap(
            spacing: 6, runSpacing: 6,
            children: items.map((item) => Chip(
              label: Text(item, style: const TextStyle(fontSize: 12)),
              deleteIcon: showDelete ? const Icon(Icons.close, size: 14) : null,
              onDeleted: showDelete ? () => onDelete(item) : null,
              backgroundColor: AppColors.panelSoft,
              side: const BorderSide(color: AppColors.line),
              visualDensity: VisualDensity.compact,
              materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
            )).toList(),
          ),
        ],
      ),
    );
  }

  bool _hasNoInferred(UserProfile p) =>
      p.inferredCategories.isEmpty &&
      p.inferredPlatforms.isEmpty &&
      p.inferredBrands.isEmpty &&
      p.inferredPriceMin == null;

  // ── Edit dialogs ───────────────────────────────────────────

  void _editPlatforms(BuildContext context, WidgetRef ref) {
    final profile = ref.read(userProfileProvider);
    _multiSelect(
      context, '常用平台', ['拼多多', '淘宝', '天猫', '京东'],
      profile.preferredPlatforms.toSet(),
      (v) {
        ref.read(userProfileProvider.notifier).setPreferredPlatforms(v.toList());
        _recordPrefUpdate(ref);
      },
    );
  }

  void _editCategories(BuildContext context, WidgetRef ref) {
    final profile = ref.read(userProfileProvider);
    _multiSelect(
      context, '常买品类', ['运动鞋', '耳机', '数码配件', '服饰', '日用品'],
      profile.preferredCategories.toSet(),
      (v) {
        ref.read(userProfileProvider.notifier).setPreferredCategories(v.toList());
        _recordPrefUpdate(ref);
      },
    );
  }

  void _editFactors(BuildContext context, WidgetRef ref) {
    final profile = ref.read(userProfileProvider);
    const factors = {
      'low_price': '低价优先',
      'official_store': '官方店铺',
      'after_sale': '售后保障',
      'fast_delivery': '配送速度',
      'high_rating': '评价数量',
      'brand_match': '偏好品牌',
    };
    _multiSelect(
      context, '更看重', factors.entries.map((e) => e.value).toList(),
      profile.decisionFactors.map((k) => factors[k] ?? k).toSet(),
      (selectedLabels) {
        final keys = selectedLabels.map((label) =>
            factors.entries.firstWhere((e) => e.value == label).key).toList();
        ref.read(userProfileProvider.notifier).setDecisionFactors(keys);
        _recordPrefUpdate(ref);
      },
    );
  }

  void _multiSelect(BuildContext context, String title, List<String> options,
      Set<String> initial, void Function(Set<String>) onSave) {
    final selected = Set<String>.from(initial);
    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setState) => AlertDialog(
          title: Text(title),
          content: SizedBox(
            width: double.maxFinite,
            child: ListView(
              shrinkWrap: true,
              children: options.map((opt) => CheckboxListTile(
                title: Text(opt, style: const TextStyle(fontSize: 14)),
                value: selected.contains(opt),
                onChanged: (v) => setState(() =>
                    v! ? selected.add(opt) : selected.remove(opt)),
                dense: true,
                activeColor: AppColors.accent,
              )).toList(),
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('取消')),
            ElevatedButton(
              onPressed: () { onSave(selected); Navigator.pop(ctx); },
              style: ElevatedButton.styleFrom(backgroundColor: AppColors.accent),
              child: const Text('保存'),
            ),
          ],
        ),
      ),
    );
  }

  // ── Privacy ────────────────────────────────────────────────

  void _showPrivacy(BuildContext context) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('隐私说明'),
        content: const Text(
          '• 原始行为事件仅存储在手机本地。\n'
          '• 开启个性化后，推断出的偏好画像（品类、品牌、价位等）会随聊天请求发送至服务器用于排序。\n'
          '• 你可以随时关闭个性化推荐或清空所有记忆。\n'
          '• 我们不会记录任何个人身份信息。\n'
          '• 未来如果接入账号系统，数据会绑定到你的账号。',
          style: TextStyle(fontSize: 14, height: 1.6),
        ),
        actions: [
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('知道了'),
          ),
        ],
      ),
    );
  }

  void _confirmClear(BuildContext context, WidgetRef ref, MemoryStore store) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('清空所有记忆？'),
        content: const Text('将删除所有偏好设置、行为记录和推断数据。此操作不可撤销。'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('取消')),
          ElevatedButton(
            onPressed: () {
              ref.read(userProfileProvider.notifier).clearAll(store);
              Navigator.pop(ctx);
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('已清空所有记忆')),
              );
            },
            style: ElevatedButton.styleFrom(backgroundColor: AppColors.priceRed),
            child: const Text('确认清空'),
          ),
        ],
      ),
    );
  }

  void _recordPrefUpdate(WidgetRef ref) {
    ref.read(behaviorRecorderProvider).record(BehaviorEventType.preferenceUpdate);
  }

  static String _factorLabel(String key) => switch (key) {
    'low_price' => '低价优先',
    'official_store' => '官方店铺',
    'after_sale' => '售后保障',
    'fast_delivery' => '配送速度',
    'high_rating' => '评价数量',
    'brand_match' => '偏好品牌',
    _ => key,
  };
}
