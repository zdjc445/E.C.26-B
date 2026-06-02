import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../domain/entities/comparison_entity.dart';
import '../providers/comparison_provider.dart';
import '../widgets/comparison_table.dart';

/// Full-screen comparison view showing lowest-price summary,
/// per-platform statistics, and a horizontal comparison table.
class ComparisonScreen extends ConsumerStatefulWidget {
  final String searchTaskId;
  final List<String> platformProductIds;

  const ComparisonScreen({
    super.key,
    required this.searchTaskId,
    required this.platformProductIds,
  });

  @override
  ConsumerState<ComparisonScreen> createState() => _ComparisonScreenState();
}

class _ComparisonScreenState extends ConsumerState<ComparisonScreen> {
  @override
  void initState() {
    super.initState();
    // Trigger comparison on first frame.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(comparisonProvider.notifier).createComparison(
            searchTaskId: widget.searchTaskId,
            platformProductIds: widget.platformProductIds,
          );
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(comparisonProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('价格对比')),
      body: state.isLoading
          ? const Center(child: CircularProgressIndicator())
          : state.error != null
              ? _ErrorView(
                  message: state.error!,
                  onRetry: () {
                    ref.read(comparisonProvider.notifier).createComparison(
                          searchTaskId: widget.searchTaskId,
                          platformProductIds: widget.platformProductIds,
                        );
                  },
                )
              : state.comparison != null
                  ? _ComparisonContent(comparison: state.comparison!)
                  : const SizedBox.shrink(),
    );
  }
}

class _ComparisonContent extends StatelessWidget {
  final ComparisonEntity comparison;

  const _ComparisonContent({required this.comparison});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Lowest price summary card
          _LowestPriceCard(comparison: comparison),
          const SizedBox(height: 16),

          // Platform stats
          Text('平台统计', style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          ...comparison.platformStats.map((stat) => _PlatformStatTile(stat: stat)),
          const SizedBox(height: 16),

          // Comparison table
          Text('横向对比', style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          ComparisonTable(items: comparison.items),
        ],
      ),
    );
  }
}

class _LowestPriceCard extends StatelessWidget {
  final ComparisonEntity comparison;

  const _LowestPriceCard({required this.comparison});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final bestItem = comparison.bestItem;

    return Card(
      color: theme.colorScheme.primaryContainer,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.savings, color: Colors.green),
                const SizedBox(width: 8),
                Text('最低价', style: theme.textTheme.titleMedium),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              '${comparison.lowestPrice.currency} ${comparison.lowestPrice.amount}',
              style: theme.textTheme.headlineSmall?.copyWith(
                fontWeight: FontWeight.bold,
                color: Colors.green,
              ),
            ),
            if (bestItem != null) ...[
              const SizedBox(height: 8),
              Text('来自: ${bestItem.platform} — ${bestItem.title}',
                  style: theme.textTheme.bodyMedium),
              Text('共 ${comparison.totalProductCount} 件商品，'
                  '${comparison.totalInStock} 件有货',
                  style: theme.textTheme.bodySmall),
            ],
          ],
        ),
      ),
    );
  }
}

class _PlatformStatTile extends StatelessWidget {
  final PlatformStat stat;

  const _PlatformStatTile({required this.stat});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Card(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(stat.platform,
                      style: theme.textTheme.titleSmall
                          ?.copyWith(fontWeight: FontWeight.bold)),
                  const SizedBox(height: 4),
                  Text(
                    '${stat.productCount} 件 | 在售 ${stat.inStockCount} 件',
                    style: theme.textTheme.bodySmall,
                  ),
                ],
              ),
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text('最低 ${stat.lowestPrice}',
                    style: theme.textTheme.bodySmall),
                Text('最高 ${stat.highestPrice}',
                    style: theme.textTheme.bodySmall),
                Text('均价 ${stat.averagePrice}',
                    style: theme.textTheme.bodySmall
                        ?.copyWith(fontWeight: FontWeight.w600)),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _ErrorView extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;

  const _ErrorView({required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.error_outline, size: 48, color: Theme.of(context).colorScheme.error),
            const SizedBox(height: 16),
            Text(message, textAlign: TextAlign.center),
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: const Text('重试'),
            ),
          ],
        ),
      ),
    );
  }
}
