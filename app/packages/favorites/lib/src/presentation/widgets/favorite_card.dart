import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';
import '../../domain/entities/favorite_entity.dart';

/// A card displaying a single favorited product.
class FavoriteCard extends StatelessWidget {
  final FavoriteEntity favorite;
  final VoidCallback? onDelete;
  final VoidCallback? onTap;

  const FavoriteCard({
    super.key,
    required this.favorite,
    this.onDelete,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Dismissible(
      key: Key(favorite.favoriteId),
      direction: DismissDirection.endToStart,
      background: Container(
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: 24),
        color: AppColors.priceRed,
        child: const Icon(Icons.delete_outline, color: Colors.white),
      ),
      confirmDismiss: (direction) async {
        return await showDialog<bool>(
          context: context,
          builder: (ctx) => AlertDialog(
            title: const Text('确认删除'),
            content: Text('确定要删除收藏「${favorite.title}」吗？'),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(ctx, false),
                child: const Text('取消'),
              ),
              TextButton(
                onPressed: () => Navigator.pop(ctx, true),
                child: const Text('删除',
                    style: TextStyle(color: AppColors.priceRed)),
              ),
            ],
          ),
        );
      },
      onDismissed: (_) => onDelete?.call(),
      child: Card(
        margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(8),
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Product info
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // Platform badge
                      _PlatformBadge(platform: favorite.platform),
                      const SizedBox(height: 8),
                      // Title
                      Text(
                        favorite.title,
                        style: theme.textTheme.bodyLarge,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: 8),
                      // Price
                      Text(
                        '${favorite.price.amountAsDouble.toStringAsFixed(2)} ${favorite.price.currency}',
                        style: theme.textTheme.titleMedium?.copyWith(
                          color: AppColors.priceRed,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      // Note
                      if (favorite.note != null &&
                          favorite.note!.isNotEmpty) ...[
                        const SizedBox(height: 6),
                        Text(
                          favorite.note!,
                          style: theme.textTheme.bodySmall,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ],
                      const SizedBox(height: 6),
                      // Created date
                      Text(
                        _formatDate(favorite.createdAt),
                        style: theme.textTheme.bodySmall,
                      ),
                    ],
                  ),
                ),
                // Delete button
                if (onDelete != null)
                  IconButton(
                    icon: const Icon(Icons.delete_outline, size: 20),
                    color: AppColors.inkSoft,
                    onPressed: onDelete,
                    tooltip: '删除收藏',
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  String _formatDate(DateTime dt) {
    return '${dt.year}-${dt.month.toString().padLeft(2, '0')}-${dt.day.toString().padLeft(2, '0')}';
  }
}

class _PlatformBadge extends StatelessWidget {
  final String platform;
  const _PlatformBadge({required this.platform});

  @override
  Widget build(BuildContext context) {
    Color badgeColor;
    String label;

    switch (platform.toLowerCase()) {
      case 'jd':
        badgeColor = const Color(0xFFC91623);
        label = '京东';
      case 'taobao':
        badgeColor = const Color(0xFFFF5000);
        label = '淘宝';
      case 'pdd':
        badgeColor = const Color(0xFFE02E24);
        label = '拼多多';
      case 'tmall':
        badgeColor = const Color(0xFFC91623);
        label = '天猫';
      default:
        badgeColor = AppColors.inkSoft;
        label = platform;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: badgeColor.withAlpha(30),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: badgeColor.withAlpha(100)),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w600,
          color: badgeColor,
        ),
      ),
    );
  }
}
