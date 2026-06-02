import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';
import '../../domain/entities/price_alert_entity.dart';

/// A card displaying a single price alert with toggle and delete actions.
class PriceAlertCard extends StatelessWidget {
  final PriceAlertEntity alert;
  final VoidCallback? onToggleEnabled;
  final VoidCallback? onEdit;
  final VoidCallback? onDelete;
  final VoidCallback? onTap;

  const PriceAlertCard({
    super.key,
    required this.alert,
    this.onToggleEnabled,
    this.onEdit,
    this.onDelete,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(8),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Title row with enabled switch
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Text(
                      alert.title,
                      style: theme.textTheme.bodyLarge,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  if (onToggleEnabled != null)
                    SizedBox(
                      height: 24,
                      child: Switch(
                        value: alert.enabled,
                        onChanged: (_) => onToggleEnabled!.call(),
                        materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      ),
                    ),
                ],
              ),
              const SizedBox(height: 10),
              // Price comparison row
              Row(
                children: [
                  // Current price
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '当前价格',
                          style: theme.textTheme.bodySmall,
                        ),
                        const SizedBox(height: 2),
                        Text(
                          '${alert.currentPrice.amountAsDouble.toStringAsFixed(2)} ${alert.currentPrice.currency}',
                          style: theme.textTheme.titleMedium?.copyWith(
                            color: alert.isTriggered
                                ? AppColors.good
                                : AppColors.inkMain,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ],
                    ),
                  ),
                  // Arrow
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                    child: Icon(
                      Icons.trending_down,
                      color: alert.isTriggered
                          ? AppColors.good
                          : AppColors.inkSoft,
                      size: 20,
                    ),
                  ),
                  // Target price
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '目标价格',
                          style: theme.textTheme.bodySmall,
                        ),
                        const SizedBox(height: 2),
                        Text(
                          '${alert.targetPrice.amountAsDouble.toStringAsFixed(2)} ${alert.targetPrice.currency}',
                          style: theme.textTheme.titleMedium?.copyWith(
                            color: AppColors.accent,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              // Bottom row: status + actions
              Row(
                children: [
                  // Triggered badge
                  _TriggerBadge(isTriggered: alert.isTriggered),
                  const SizedBox(width: 8),
                  // Updated date
                  Text(
                    '更新于 ${_formatDate(alert.updatedAt)}',
                    style: theme.textTheme.bodySmall,
                  ),
                  const Spacer(),
                  // Edit button
                  if (onEdit != null)
                    IconButton(
                      icon: const Icon(Icons.edit_outlined, size: 18),
                      color: AppColors.inkSoft,
                      onPressed: onEdit,
                      tooltip: '编辑',
                      constraints:
                          const BoxConstraints(minWidth: 36, minHeight: 36),
                      padding: EdgeInsets.zero,
                    ),
                  // Delete button
                  if (onDelete != null)
                    IconButton(
                      icon: const Icon(Icons.delete_outline, size: 18),
                      color: AppColors.inkSoft,
                      onPressed: () => _confirmDelete(context),
                      tooltip: '删除',
                      constraints:
                          const BoxConstraints(minWidth: 36, minHeight: 36),
                      padding: EdgeInsets.zero,
                    ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _confirmDelete(BuildContext context) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('确认删除'),
        content: Text('确定要删除「${alert.title}」的价格提醒吗？'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('取消'),
          ),
          TextButton(
            onPressed: () {
              Navigator.pop(ctx, true);
            },
            child:
                const Text('删除', style: TextStyle(color: AppColors.priceRed)),
          ),
        ],
      ),
    );

    if (confirmed == true) {
      onDelete?.call();
    }
  }

  String _formatDate(DateTime dt) {
    return '${dt.year}-${dt.month.toString().padLeft(2, '0')}-${dt.day.toString().padLeft(2, '0')}';
  }
}

class _TriggerBadge extends StatelessWidget {
  final bool isTriggered;
  const _TriggerBadge({required this.isTriggered});

  @override
  Widget build(BuildContext context) {
    final color = isTriggered ? AppColors.good : AppColors.warn;
    final label = isTriggered ? '已触发' : '监控中';
    final icon = isTriggered ? Icons.notifications_active : Icons.notifications;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withAlpha(30),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withAlpha(100)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 12, color: color),
          const SizedBox(width: 4),
          Text(
            label,
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w600,
              color: color,
            ),
          ),
        ],
      ),
    );
  }
}
