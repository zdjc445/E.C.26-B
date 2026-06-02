import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:app_core/app_core.dart';
import '../providers/favorite_provider.dart';
import '../widgets/favorite_card.dart';

/// Screen displaying the user's favorites list with swipe-to-delete support.
class FavoritesScreen extends ConsumerStatefulWidget {
  const FavoritesScreen({super.key});

  @override
  ConsumerState<FavoritesScreen> createState() => _FavoritesScreenState();
}

class _FavoritesScreenState extends ConsumerState<FavoritesScreen> {
  final _scrollController = ScrollController();

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScroll);
    // Load favorites on first frame.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(favoriteProvider.notifier).loadFavorites();
    });
  }

  void _onScroll() {
    if (_scrollController.position.pixels >=
        _scrollController.position.maxScrollExtent - 200) {
      ref.read(favoriteProvider.notifier).loadMore();
    }
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(favoriteProvider);
    final theme = Theme.of(context);

    // Show error snackbar if needed.
    ref.listen(favoriteProvider, (prev, next) {
      if (next.error != null && next.error != prev?.error) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(next.error!),
            backgroundColor: AppColors.priceRed,
            action: SnackBarAction(
              label: '重试',
              textColor: Colors.white,
              onPressed: () =>
                  ref.read(favoriteProvider.notifier).loadFavorites(),
            ),
          ),
        );
        ref.read(favoriteProvider.notifier).clearError();
      }
    });

    return Scaffold(
      appBar: AppBar(
        title: const Text('我的收藏'),
        actions: [
          if (state.favorites.isNotEmpty)
            Text(
              '共 ${state.total} 件',
              style: theme.textTheme.bodySmall,
            ),
          const SizedBox(width: 16),
        ],
      ),
      body: _buildBody(state, theme),
    );
  }

  Widget _buildBody(FavoritesState state, ThemeData theme) {
    switch (state.status) {
      case FavoritesLoadStatus.initial:
      case FavoritesLoadStatus.loading:
        if (state.favorites.isEmpty) {
          return const Center(child: CircularProgressIndicator());
        }
        return _buildList(state, theme);

      case FavoritesLoadStatus.error:
        if (state.favorites.isEmpty) {
          return _buildError(theme);
        }
        return _buildList(state, theme);

      case FavoritesLoadStatus.empty:
        return _buildEmpty(theme);

      case FavoritesLoadStatus.loaded:
        return _buildList(state, theme);
    }
  }

  Widget _buildList(FavoritesState state, ThemeData theme) {
    return RefreshIndicator(
      onRefresh: () => ref.read(favoriteProvider.notifier).loadFavorites(),
      child: ListView.builder(
        controller: _scrollController,
        padding: const EdgeInsets.only(top: 8, bottom: 24),
        itemCount: state.favorites.length + (state.hasMore ? 1 : 0),
        itemBuilder: (context, index) {
          if (index >= state.favorites.length) {
            return const Padding(
              padding: EdgeInsets.all(16),
              child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
            );
          }
          final favorite = state.favorites[index];
          return FavoriteCard(
            favorite: favorite,
            onDelete: () {
              ref
                  .read(favoriteProvider.notifier)
                  .removeFavorite(favorite.favoriteId);
            },
            onTap: () {
              // Navigate to product detail — hook into your router here.
            },
          );
        },
      ),
    );
  }

  Widget _buildEmpty(ThemeData theme) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.favorite_border, size: 64, color: AppColors.inkSoft),
          const SizedBox(height: 16),
          Text(
            '还没有收藏任何商品',
            style: theme.textTheme.titleMedium?.copyWith(
              color: AppColors.inkSoft,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            '浏览商品时点击收藏按钮即可添加',
            style: theme.textTheme.bodySmall,
          ),
        ],
      ),
    );
  }

  Widget _buildError(ThemeData theme) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.error_outline, size: 64, color: AppColors.inkSoft),
          const SizedBox(height: 16),
          Text(
            '加载失败，请重试',
            style: theme.textTheme.titleMedium?.copyWith(
              color: AppColors.inkSoft,
            ),
          ),
          const SizedBox(height: 16),
          ElevatedButton.icon(
            onPressed: () =>
                ref.read(favoriteProvider.notifier).loadFavorites(),
            icon: const Icon(Icons.refresh, size: 18),
            label: const Text('重试'),
          ),
        ],
      ),
    );
  }
}
