import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';
import '../../domain/entities/ecommerce_diagnostics_entity.dart';

/// A card showing diagnostic results for a single e-commerce provider.
class DiagnosticsCard extends StatelessWidget {
  final EcommerceProviderDiagnostic diagnostic;

  const DiagnosticsCard({super.key, required this.diagnostic});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header: platform name + status badge
            Row(
              children: [
                Text(
                  _platformLabel(diagnostic.platform),
                  style: theme.textTheme.titleMedium,
                ),
                const SizedBox(width: 10),
                _StatusBadge(diagnostic: diagnostic),
                const Spacer(),
                if (diagnostic.configured)
                  Text(
                    '${diagnostic.durationMs}ms',
                    style: theme.textTheme.bodySmall,
                  ),
              ],
            ),
            const SizedBox(height: 10),
            // Metrics row
            if (diagnostic.configured) ...[
              Row(
                children: [
                  _MetricChip(
                    label: '结果数',
                    value: '${diagnostic.itemCount}',
                    color: AppColors.accent,
                  ),
                  const SizedBox(width: 12),
                  _MetricChip(
                    label: '耗时',
                    value: '${diagnostic.durationMs}ms',
                    color: AppColors.inkSoft,
                  ),
                ],
              ),
            ],
            // Sample titles
            if (diagnostic.sampleTitles.isNotEmpty) ...[
              const SizedBox(height: 10),
              Text('样本商品', style: theme.textTheme.bodySmall),
              const SizedBox(height: 4),
              ...diagnostic.sampleTitles.map(
                (title) => Padding(
                  padding: const EdgeInsets.only(bottom: 2),
                  child: Row(
                    children: [
                      const Icon(Icons.shopping_bag_outlined,
                          size: 14, color: AppColors.inkSoft),
                      const SizedBox(width: 6),
                      Expanded(
                        child: Text(
                          title,
                          style: theme.textTheme.bodyMedium,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
            // Error message
            if (diagnostic.errorMessage != null) ...[
              const SizedBox(height: 10),
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: AppColors.priceRed.withAlpha(15),
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(color: AppColors.priceRed.withAlpha(50)),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.error_outline,
                        size: 16, color: AppColors.priceRed),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          if (diagnostic.errorCode != null)
                            Text(
                              diagnostic.errorCode!,
                              style: const TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                                color: AppColors.priceRed,
                              ),
                            ),
                          Text(
                            diagnostic.errorMessage!,
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: AppColors.priceRed,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ],
            // Missing config
            if (diagnostic.missingConfig.isNotEmpty) ...[
              const SizedBox(height: 10),
              Wrap(
                spacing: 6,
                runSpacing: 4,
                children: diagnostic.missingConfig.map((cfg) {
                  return Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                    decoration: BoxDecoration(
                      color: AppColors.warn.withAlpha(30),
                      borderRadius: BorderRadius.circular(4),
                      border: Border.all(color: AppColors.warn.withAlpha(80)),
                    ),
                    child: Text(
                      cfg,
                      style: const TextStyle(
                        fontSize: 11,
                        color: AppColors.warn,
                      ),
                    ),
                  );
                }).toList(),
              ),
            ],
          ],
        ),
      ),
    );
  }

  String _platformLabel(String platform) {
    switch (platform.toLowerCase()) {
      case 'jd':
        return '京东';
      case 'taobao':
        return '淘宝';
      case 'pdd':
        return '拼多多';
      case 'tmall':
        return '天猫';
      default:
        return platform;
    }
  }
}

class _StatusBadge extends StatelessWidget {
  final EcommerceProviderDiagnostic diagnostic;
  const _StatusBadge({required this.diagnostic});

  @override
  Widget build(BuildContext context) {
    Color color;
    String label;
    IconData icon;

    if (!diagnostic.configured) {
      color = AppColors.inkSoft;
      label = '未配置';
      icon = Icons.block;
    } else if (diagnostic.success) {
      color = AppColors.good;
      label = '成功';
      icon = Icons.check_circle;
    } else {
      color = AppColors.priceRed;
      label = '失败';
      icon = Icons.cancel;
    }

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

class _MetricChip extends StatelessWidget {
  final String label;
  final String value;
  final Color color;

  const _MetricChip({
    required this.label,
    required this.value,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          '$label: ',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        Text(
          value,
          style: TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w700,
            color: color,
          ),
        ),
      ],
    );
  }
}
