import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/network/api_client.dart';
import '../../core/theme/app_theme.dart';
import '../auth/auth_controller.dart';
import 'favorite_api.dart';
import 'favorite_models.dart';

final favoriteApiProvider = Provider<FavoriteApi>((ref) {
  return FavoriteApi(baseUrl: ref.watch(apiBaseUrlProvider));
});

class FavoritesScreen extends ConsumerStatefulWidget {
  const FavoritesScreen({super.key});

  @override
  ConsumerState<FavoritesScreen> createState() => _FavoritesScreenState();
}

class _FavoritesScreenState extends ConsumerState<FavoritesScreen> {
  Future<List<FavoriteItem>>? _future;

  @override
  void initState() {
    super.initState();
    _load();
  }

  void _load() {
    final api = ref.read(favoriteApiProvider);
    final token = ref.read(authControllerProvider).session?.token;
    setState(() {
      _future = api.list(token: token);
    });
  }

  Future<void> _delete(String productId) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      final api = ref.read(favoriteApiProvider);
      final token = ref.read(authControllerProvider).session?.token;
      await api.delete(productId, token: token);
      messenger.showSnackBar(const SnackBar(content: Text('已取消收藏')));
      _load();
    } catch (e) {
      messenger.showSnackBar(SnackBar(content: Text('取消收藏失败：$e')));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text('我的收藏'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _load,
          ),
        ],
      ),
      body: FutureBuilder<List<FavoriteItem>>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text('加载失败：${snapshot.error}',
                    style: const TextStyle(color: AppColors.priceRed)),
              ),
            );
          }
          final items = snapshot.data ?? [];
          if (items.isEmpty) {
            return const Center(
              child: Text('暂无收藏，去聊天页面长按推荐商品试试',
                  style: TextStyle(color: AppColors.inkSoft)),
            );
          }
          return ListView.separated(
            padding: const EdgeInsets.all(12),
            itemCount: items.length,
            separatorBuilder: (_, __) => const SizedBox(height: 8),
            itemBuilder: (context, i) {
              final f = items[i];
              return Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: AppColors.panel,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: AppColors.line),
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(f.title,
                              style: const TextStyle(
                                  fontSize: 14, fontWeight: FontWeight.w600)),
                          const SizedBox(height: 4),
                          Wrap(spacing: 6, runSpacing: 4, children: [
                            _badge(f.platform),
                            if (f.brand != null && f.brand!.isNotEmpty)
                              _badge(f.brand!),
                            if (f.shopName != null && f.shopName!.isNotEmpty)
                              _badge(f.shopName!),
                          ]),
                          const SizedBox(height: 6),
                          Text('¥${f.price.toStringAsFixed(2)}',
                              style: const TextStyle(
                                  fontSize: 16,
                                  fontWeight: FontWeight.w700,
                                  color: AppColors.priceRed)),
                        ],
                      ),
                    ),
                    IconButton(
                      icon: const Icon(Icons.delete_outline,
                          color: AppColors.priceRed),
                      onPressed: () => _delete(f.productId),
                    ),
                  ],
                ),
              );
            },
          );
        },
      ),
    );
  }

  Widget _badge(String label) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
      decoration: BoxDecoration(
        color: AppColors.background,
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(label,
          style: const TextStyle(fontSize: 11, color: AppColors.inkSoft)),
    );
  }
}
