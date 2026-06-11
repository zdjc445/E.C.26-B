import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/network/api_client.dart';
import '../../core/theme/app_theme.dart';
import '../auth/auth_controller.dart';
import '../ecommerce/ecommerce_api.dart';
import 'debug_screen.dart';
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
    final auth = ref.watch(authControllerProvider);
    final health =
        ref.watch(healthStatusProvider).valueOrNull ?? HealthStatus.unknown;
    final ecom = ref.watch(ecommerceStatusProvider).valueOrNull ??
        EcommerceStatus.unknown;

    return Scaffold(
      backgroundColor: AppColors.chatBackground,
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.go('/home'),
        ),
        title: const Text('我的'),
      ),
      body: ListView(
        key: const Key('profile_list'),
        padding: const EdgeInsets.all(16),
        children: [
          // ── User info ──
          _buildUserCard(context, ref, auth),
          const SizedBox(height: 12),

          // ── My stuff ──
          _SectionHeader(title: '我的'),
          Card(
            child: Column(
              children: [
                ListTile(
                  leading: const Icon(Icons.favorite_border),
                  title: const Text('我的收藏'),
                  subtitle: const Text('查看保存的商品'),
                  trailing:
                      const Icon(Icons.chevron_right, color: AppColors.inkSoft),
                  onTap: () => context.push('/favorites'),
                ),
                const Divider(height: 1),
                ListTile(
                  leading: const Icon(Icons.notifications_outlined),
                  title: const Text('价格提醒'),
                  subtitle: const Text('达到目标价时通知你'),
                  trailing:
                      const Icon(Icons.chevron_right, color: AppColors.inkSoft),
                  onTap: () => context.push('/price-alerts'),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),

          // ── Shopping preferences ──
          _SectionHeader(title: '购物偏好'),
          Card(
            child: ListTile(
              leading: const Icon(Icons.psychology_outlined),
              title: const Text('推荐记忆与隐私'),
              subtitle: const Text('查看和管理用于推荐的偏好'),
              trailing:
                  const Icon(Icons.chevron_right, color: AppColors.inkSoft),
              onTap: () => context.push('/preferences'),
            ),
          ),
          const SizedBox(height: 12),

          // ── About ──
          _SectionHeader(title: '关于识价镜'),
          GestureDetector(
            onLongPress: () => Navigator.of(context).push(
              MaterialPageRoute(
                  builder: (_) => DebugScreen(health: health, ecom: ecom)),
            ),
            child: Card(
              child: ListTile(
                leading: const Icon(Icons.info_outlined),
                title: const Text('识价镜'),
                subtitle: const Text('拍照识物 · 多平台比价 · 智能推荐'),
                trailing: const Icon(Icons.chevron_right,
                    size: 18, color: AppColors.inkSoft),
              ),
            ),
          ),
          const SizedBox(height: 24),
        ],
      ),
    );
  }

  Widget _buildUserCard(
      BuildContext context, WidgetRef ref, AuthController auth) {
    return Card(
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
                color: AppColors.accent,
                size: 28,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    auth.currentUser.displayName,
                    style: const TextStyle(
                        fontSize: 16, fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    auth.isAuthenticated
                        ? '@${auth.currentUser.username} · 已登录'
                        : '后端认证未启用 · 使用演示用户',
                    style:
                        const TextStyle(fontSize: 13, color: AppColors.inkSoft),
                  ),
                ],
              ),
            ),
            if (auth.isAuthenticated)
              TextButton(
                onPressed: () =>
                    ref.read(authControllerProvider.notifier).logout(),
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
