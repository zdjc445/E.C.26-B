import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:app_core/app_core.dart';
import 'package:app_auth/app_auth.dart';
import 'package:app_image_picker/app_image_picker.dart';
import 'package:app_recognition/app_recognition.dart';
import 'package:app_search/app_search.dart';
import 'package:app_comparison/app_comparison.dart';
import 'package:app_recommendation/app_recommendation.dart';
import 'package:app_product_inspection/app_product_inspection.dart';
import 'package:app_favorites/app_favorites.dart';
import 'package:app_price_alerts/app_price_alerts.dart';
import 'package:app_ecommerce_diagnostics/app_ecommerce_diagnostics.dart';

/// Central router that assembles routes from all 11 feature packages.
///
/// Each package exports a `<name>Routes()` function returning `List<RouteBase>`
/// — the shell simply collects them with the spread operator.
final appRouterProvider = Provider<GoRouter>((ref) {
  final authState = ref.watch(authProvider);

  return GoRouter(
    initialLocation: '/auth/login',
    redirect: (context, state) {
      final isLoggedIn = authState.status == AuthStatus.authenticated;
      final isAuthRoute = state.matchedLocation == '/auth/login';

      if (!isLoggedIn && !isAuthRoute) {
        return '/auth/login';
      }
      if (isLoggedIn && isAuthRoute) {
        return '/home';
      }
      return null;
    },
    routes: [
      // ── Auth (public) ──
      ...authRoutes(),

      // ── Shell: bottom navigation for main workspace ──
      ShellRoute(
        builder: (context, state, child) => _AppShell(child: child),
        routes: [
          // Home
          GoRoute(
            path: '/home',
            builder: (context, state) => const _HomeScreen(),
          ),

          // Feature routes
          ...imagePickerRoutes(),
          ...recognitionRoutes(),
          GoRoute(
            path: '/search',
            builder: (context, state) {
              final extra = state.extra as Map<String, dynamic>? ?? {};
              return SearchResultsScreen(
                initialImageId: state.uri.queryParameters['imageId'] ??
                    extra['imageId']?.toString(),
                onProductAction: (context, product, searchState) =>
                    _showProductActionSheet(context, ref, product, searchState),
              );
            },
          ),
          ...comparisonRoutes(),
          ...recommendationRoutes(),
          ...inspectionRoutes(),
          ...favoritesRoutes(),
          ...priceAlertsRoutes(),
          ...diagnosticsRoutes(),
        ],
      ),
    ],
  );
});

Future<void> _showProductActionSheet(
  BuildContext context,
  Ref ref,
  ProductEntity product,
  SearchState searchState,
) {
  final taskId = searchState.currentTask?.taskId ?? '';
  final candidateIds = searchState.products
      .map((p) => p.productId)
      .where((id) => id.isNotEmpty)
      .take(3)
      .toList();

  void showSnack(String message) {
    if (!context.mounted) return;
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(message)));
  }

  void openComparison() {
    if (taskId.isEmpty || candidateIds.isEmpty) {
      showSnack('请先完成一次搜索，再进入比价。');
      return;
    }
    context.push('/comparison', extra: {
      'searchTaskId': taskId,
      'platformProductIds': candidateIds,
    });
  }

  void openRecommendation() {
    if (taskId.isEmpty || candidateIds.isEmpty) {
      showSnack('请先完成一次搜索，再生成推荐。');
      return;
    }
    context.push('/recommendation', extra: {
      'searchTaskId': taskId,
      'userQuery': searchState.currentTask?.query ?? '',
      'candidateIds': candidateIds,
    });
  }

  Future<void> addFavorite() async {
    final success = await ref
        .read(favoriteProvider.notifier)
        .addFavorite(product.productId, note: '来自移动端搜索');
    final error = ref.read(favoriteProvider).error;
    showSnack(success ? '已加入收藏。' : error ?? '收藏失败，请稍后重试。');
  }

  Future<void> createAlert() async {
    final targetPrice = await _promptTargetPrice(context, product);
    if (targetPrice == null) return;
    final success = await ref.read(priceAlertProvider.notifier).createAlert(
          platformProductId: product.productId,
          targetPrice: Money(amount: targetPrice.toStringAsFixed(2)),
        );
    final error = ref.read(priceAlertProvider).actionError;
    showSnack(success ? '目标价提醒已创建。' : error ?? '提醒创建失败，请稍后重试。');
  }

  return showModalBottomSheet<void>(
    context: context,
    showDragHandle: true,
    builder: (sheetContext) => SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 12),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              product.title,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 4),
            Text(
              '${product.platformLabel.toUpperCase()} · ¥${product.price.toStringAsFixed(2)}',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 10),
            _ProductActionTile(
              icon: Icons.insights_outlined,
              label: '商品洞察',
              meta: '价格走势与评价风险',
              onTap: () {
                Navigator.of(sheetContext).pop();
                context.push('/inspection/${product.productId}');
              },
            ),
            _ProductActionTile(
              icon: Icons.compare_arrows,
              label: '比价',
              meta: '对比当前搜索的候选商品',
              onTap: () {
                Navigator.of(sheetContext).pop();
                openComparison();
              },
            ),
            _ProductActionTile(
              icon: Icons.auto_awesome_outlined,
              label: 'Agent 推荐',
              meta: '生成决策分、信号和证据链',
              onTap: () {
                Navigator.of(sheetContext).pop();
                openRecommendation();
              },
            ),
            _ProductActionTile(
              icon: Icons.favorite_border,
              label: '收藏',
              meta: '沉淀到商品资产',
              onTap: () {
                Navigator.of(sheetContext).pop();
                addFavorite();
              },
            ),
            _ProductActionTile(
              icon: Icons.notifications_outlined,
              label: '目标价提醒',
              meta: '默认按当前价 95% 生成',
              onTap: () {
                Navigator.of(sheetContext).pop();
                createAlert();
              },
            ),
          ],
        ),
      ),
    ),
  );
}

Future<double?> _promptTargetPrice(
  BuildContext context,
  ProductEntity product,
) async {
  final controller = TextEditingController(
    text: (product.price * 0.95).toStringAsFixed(2),
  );
  try {
    return showDialog<double>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('设置目标价'),
        content: TextField(
          controller: controller,
          autofocus: true,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: const InputDecoration(
            prefixText: '¥ ',
            labelText: '目标价',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () {
              final value = double.tryParse(controller.text.trim());
              if (value == null || value <= 0) return;
              Navigator.of(dialogContext).pop(value);
            },
            child: const Text('创建'),
          ),
        ],
      ),
    );
  } finally {
    controller.dispose();
  }
}

class _ProductActionTile extends StatelessWidget {
  final IconData icon;
  final String label;
  final String meta;
  final VoidCallback onTap;

  const _ProductActionTile({
    required this.icon,
    required this.label,
    required this.meta,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return ListTile(
      contentPadding: EdgeInsets.zero,
      leading: Container(
        width: 38,
        height: 38,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: AppColors.accent.withAlpha(20),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Icon(icon, color: AppColors.accent),
      ),
      title: Text(label, style: const TextStyle(fontWeight: FontWeight.w800)),
      subtitle: Text(meta),
      trailing: const Icon(Icons.chevron_right),
      onTap: onTap,
    );
  }
}

/// Wraps all authenticated screens with a common [BottomNavigationBar].
class _AppShell extends ConsumerWidget {
  final Widget child;
  const _AppShell({required this.child});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final location = GoRouterState.of(context).matchedLocation;
    final authState = ref.watch(authProvider);
    final user = authState.user;

    return Scaffold(
      appBar: AppBar(
        title: const Text('E.C.26-B'),
        actions: [
          if (user != null)
            PopupMenuButton<String>(
              icon: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.account_circle, size: 20),
                  const SizedBox(width: 4),
                  Text(user.displayName, style: const TextStyle(fontSize: 14)),
                ],
              ),
              onSelected: (value) {
                if (value == 'profile') context.go('/profile');
                if (value == 'diagnostics') {
                  context.go('/ecommerce/diagnostics');
                }
                if (value == 'favorites') context.go('/favorites');
                if (value == 'price-alerts') context.go('/price-alerts');
                if (value == 'logout') {
                  ref.read(authProvider.notifier).logout();
                }
              },
              itemBuilder: (_) => const [
                PopupMenuItem(value: 'favorites', child: Text('收藏')),
                PopupMenuItem(value: 'price-alerts', child: Text('价格提醒')),
                PopupMenuItem(value: 'diagnostics', child: Text('电商诊断')),
                PopupMenuItem(value: 'logout', child: Text('退出登录')),
              ],
            ),
        ],
      ),
      body: child,
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _navIndex(location),
        onTap: (index) {
          final routes = ['/home', '/camera', '/search'];
          if (index < routes.length) context.go(routes[index]);
        },
        items: const [
          BottomNavigationBarItem(icon: Icon(Icons.home_outlined), label: '首页'),
          BottomNavigationBarItem(
              icon: Icon(Icons.camera_alt_outlined), label: '拍照'),
          BottomNavigationBarItem(icon: Icon(Icons.history), label: '历史'),
        ],
      ),
    );
  }

  int _navIndex(String location) {
    if (location == '/camera') return 1;
    if (location.startsWith('/search')) return 2;
    return 0;
  }
}

class _HomeScreen extends ConsumerWidget {
  const _HomeScreen();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const _WorkspaceHeader(),
          const SizedBox(height: 16),
          Text('工作区', style: theme.textTheme.titleMedium),
          const SizedBox(height: 12),
          GridView(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: 2,
              mainAxisSpacing: 10,
              crossAxisSpacing: 10,
              childAspectRatio: 1.48,
            ),
            children: [
              _QuickActionCard(
                icon: Icons.camera_alt_outlined,
                label: '拍照',
                meta: '识别入口',
                color: AppColors.accent,
                onTap: () => context.go('/camera'),
              ),
              _QuickActionCard(
                icon: Icons.search,
                label: '搜索',
                meta: '候选列表',
                color: AppColors.signal,
                onTap: () => context.go('/search'),
              ),
              _QuickActionCard(
                icon: Icons.favorite_border,
                label: '收藏',
                meta: '商品资产',
                color: AppColors.warn,
                onTap: () => context.go('/favorites'),
              ),
              _QuickActionCard(
                icon: Icons.notifications_outlined,
                label: '提醒',
                meta: '目标价',
                color: AppColors.good,
                onTap: () => context.go('/price-alerts'),
              ),
            ],
          ),
          const SizedBox(height: 16),
          _StatusStrip(
            items: const [
              _StatusItem(label: '证据链', value: '5+6'),
              _StatusItem(label: '候选矩阵', value: '已接入'),
              _StatusItem(label: '数据源', value: 'Mock/API'),
            ],
            onTap: () => context.go('/ecommerce/diagnostics'),
          ),
        ],
      ),
    );
  }
}

class _WorkspaceHeader extends StatelessWidget {
  const _WorkspaceHeader();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.panel,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.line),
      ),
      child: Row(
        children: [
          Container(
            width: 42,
            height: 42,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: AppColors.accent,
              borderRadius: BorderRadius.circular(8),
            ),
            child: const Text(
              'EC',
              style:
                  TextStyle(color: Colors.white, fontWeight: FontWeight.w900),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('购物决策工作台', style: theme.textTheme.headlineSmall),
                const SizedBox(height: 3),
                Text('候选、比价、证据、提醒', style: theme.textTheme.bodySmall),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _StatusItem {
  final String label;
  final String value;

  const _StatusItem({required this.label, required this.value});
}

class _StatusStrip extends StatelessWidget {
  final List<_StatusItem> items;
  final VoidCallback onTap;

  const _StatusStrip({required this.items, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(8),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: items
                .map(
                  (item) => Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(item.label,
                            style: Theme.of(context).textTheme.labelMedium),
                        const SizedBox(height: 4),
                        Text(
                          item.value,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            color: AppColors.inkMain,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                      ],
                    ),
                  ),
                )
                .toList(),
          ),
        ),
      ),
    );
  }
}

class _QuickActionCard extends StatelessWidget {
  final IconData icon;
  final String label;
  final String meta;
  final Color color;
  final VoidCallback onTap;

  const _QuickActionCard({
    required this.icon,
    required this.label,
    required this.meta,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(8),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 34,
                height: 34,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: color.withAlpha(24),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: color.withAlpha(70)),
                ),
                child: Icon(icon, color: color, size: 19),
              ),
              const Spacer(),
              Text(label, style: const TextStyle(fontWeight: FontWeight.w800)),
              Text(meta, style: Theme.of(context).textTheme.bodySmall),
            ],
          ),
        ),
      ),
    );
  }
}
