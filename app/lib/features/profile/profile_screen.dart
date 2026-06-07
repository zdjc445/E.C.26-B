import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/network/api_client.dart';
import '../../core/theme/app_theme.dart';
import '../auth/auth_controller.dart';
import '../ecommerce/ecommerce_api.dart';
import 'health_api.dart';

/// Provider for HealthApi.
final healthApiProvider = Provider<HealthApi>((ref) {
  final baseUrl = ref.watch(apiBaseUrlProvider);
  return HealthApi(baseUrl: baseUrl);
});

final healthStatusProvider = FutureProvider<HealthStatus>((ref) async {
  try {
    return await ref.watch(healthApiProvider).fetch();
  } catch (_) {
    return HealthStatus.unknown;
  }
});

final ecommerceApiProvider = Provider<EcommerceApi>((ref) {
  return EcommerceApi(baseUrl: ref.watch(apiBaseUrlProvider));
});

final ecommerceStatusProvider = FutureProvider<EcommerceStatus>((ref) async {
  try {
    return await ref.watch(ecommerceApiProvider).status();
  } catch (_) {
    return EcommerceStatus.unknown;
  }
});

/// User profile / settings page at /me.
class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final healthAsync = ref.watch(healthStatusProvider);
    final health = healthAsync.valueOrNull ?? HealthStatus.unknown;
    final ecomAsync = ref.watch(ecommerceStatusProvider);
    final ecom = ecomAsync.valueOrNull ?? EcommerceStatus.unknown;
    final auth = ref.watch(authControllerProvider);

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(title: const Text('我的')),
      body: ListView(
        key: const Key('profile_list'),
        padding: const EdgeInsets.all(16),
        children: [
          // ── User info ──
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                children: [
                  Container(
                    width: 48,
                    height: 48,
                    decoration: BoxDecoration(
                      color: AppColors.accent.withAlpha(20),
                      borderRadius: BorderRadius.circular(24),
                    ),
                    child: Icon(
                      auth.isAuthenticated ? Icons.verified_user : Icons.person,
                      color: AppColors.accent, size: 28),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(auth.currentUser.displayName,
                            style: const TextStyle(
                                fontSize: 16, fontWeight: FontWeight.w600)),
                        const SizedBox(height: 4),
                        Text(
                            auth.isAuthenticated
                                ? '@${auth.currentUser.username} · JWT 已登录'
                                : (auth.currentUser.authEnabled
                                    ? '未登录，请先登录'
                                    : '后端认证未启用 · 使用演示用户'),
                            style: const TextStyle(
                                fontSize: 13, color: AppColors.inkSoft)),
                      ],
                    ),
                  ),
                  if (auth.isAuthenticated)
                    TextButton(
                      onPressed: () {
                        ref.read(authControllerProvider.notifier).logout();
                      },
                      child: const Text('登出'),
                    )
                  else
                    TextButton(
                      onPressed: () => context.go('/login'),
                      child: const Text('登录'),
                    ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),

          // ── Quick entries ──
          _SectionHeader(title: '我的'),
          Card(
            child: Column(
              children: [
                ListTile(
                  leading: const Icon(Icons.favorite_border),
                  title: const Text('我的收藏'),
                  subtitle: const Text('查看长按推荐卡保存的商品'),
                  trailing: const Icon(Icons.chevron_right,
                      color: AppColors.inkSoft),
                  onTap: () => context.push('/favorites'),
                ),
                const Divider(height: 1),
                ListTile(
                  leading: const Icon(Icons.notifications_outlined),
                  title: const Text('价格提醒'),
                  subtitle: const Text('达到目标价时触发，支持立即检测'),
                  trailing: const Icon(Icons.chevron_right,
                      color: AppColors.inkSoft),
                  onTap: () => context.push('/price-alerts'),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),

          // ── Shopping preferences ──
          _SectionHeader(title: '购物偏好'),
          Card(
            child: Column(
              children: [
                SwitchListTile(
                  title: const Text('价格优先'),
                  subtitle: const Text('优先推荐价格最低的商品'),
                  value: true,
                  onChanged: (_) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('偏好已保存在会话内（演示用）')),
                    );
                  },
                ),
                const Divider(height: 1),
                SwitchListTile(
                  title: const Text('官方店铺优先'),
                  subtitle: const Text('优先推荐官方旗舰店商品'),
                  value: false,
                  onChanged: (_) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('偏好已保存在会话内（演示用）')),
                    );
                  },
                ),
                const Divider(height: 1),
                SwitchListTile(
                  title: const Text('配送更快'),
                  subtitle: const Text('优先推荐配送速度快的商品'),
                  value: false,
                  onChanged: (_) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('偏好已保存在会话内（演示用）')),
                    );
                  },
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),

          // ── Privacy & data ──
          _SectionHeader(title: '隐私与数据'),
          Card(
            child: Column(
              children: [
                ListTile(
                  leading: const Icon(Icons.cleaning_services_outlined),
                  title: const Text('清理本地缓存'),
                  subtitle: const Text('占位'),
                  trailing: const Icon(Icons.chevron_right,
                      color: AppColors.inkSoft),
                  onTap: () {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('缓存清理功能即将上线')),
                    );
                  },
                ),
                const Divider(height: 1),
                ListTile(
                  leading: const Icon(Icons.download_outlined),
                  title: const Text('数据导出'),
                  subtitle: const Text('占位'),
                  trailing: const Icon(Icons.chevron_right,
                      color: AppColors.inkSoft),
                  onTap: () {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('数据导出功能即将上线')),
                    );
                  },
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),

          // ── API status ──
          _SectionHeader(title: '接口状态'),
          Card(
            child: Column(
              children: [
                ListTile(
                  leading: const Icon(Icons.smart_toy_outlined),
                  title: const Text('AI Provider'),
                  subtitle: Text(health.aiProvider),
                ),
                const Divider(height: 1),
                ListTile(
                  leading: const Icon(Icons.storage_outlined),
                  title: const Text('历史存储'),
                  subtitle: Text(health.chatHistoryStore),
                ),
                const Divider(height: 1),
                ListTile(
                  leading: const Icon(Icons.shopping_bag_outlined),
                  title: const Text('电商 Provider'),
                  subtitle: Text(
                      '${ecom.activeProvider} · real ${ecom.realProviderActive ? "ON" : "OFF"}'),
                ),
                const Divider(height: 1),
                ListTile(
                  leading: const Icon(Icons.lock_outline),
                  title: const Text('认证模式'),
                  subtitle:
                      Text(health.authEnabled ? '启用 JWT' : '演示模式（authEnabled=false）'),
                ),
                const Divider(height: 1),
                ListTile(
                  leading: const Icon(Icons.mic_outlined),
                  title: const Text('语音 Provider'),
                  subtitle: Text(health.voiceProvider),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),

          // ── About ──
          _SectionHeader(title: '关于项目'),
          Card(
            child: ListTile(
              leading: const Icon(Icons.info_outlined),
              title: const Text('当前阶段'),
              subtitle: Text(health.stage),
            ),
          ),
          const SizedBox(height: 24),
        ],
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final String title;
  const _SectionHeader({required this.title});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(left: 2, bottom: 8),
      child: Text(title,
          style: const TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w600,
              color: AppColors.inkSoft)),
    );
  }
}
