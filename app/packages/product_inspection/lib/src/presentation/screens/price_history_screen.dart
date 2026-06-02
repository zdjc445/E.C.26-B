import 'package:app_core/app_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../domain/entities/price_history_entity.dart';
import '../../domain/entities/review_summary_entity.dart';
import '../providers/product_inspection_provider.dart';
import '../widgets/price_chart.dart';

/// Full-screen product inspection view showing price history line chart,
/// trend badge, current/lowest/highest prices, and list of price points.
class PriceHistoryScreen extends ConsumerStatefulWidget {
  final String platformProductId;

  const PriceHistoryScreen({
    super.key,
    required this.platformProductId,
  });

  @override
  ConsumerState<PriceHistoryScreen> createState() => _PriceHistoryScreenState();
}

class _PriceHistoryScreenState extends ConsumerState<PriceHistoryScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(productInspectionProvider.notifier).loadAll(
            platformProductId: widget.platformProductId,
          );
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(productInspectionProvider);
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('商品详情'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () {
              ref.read(productInspectionProvider.notifier).loadAll(
                    platformProductId: widget.platformProductId,
                  );
            },
          ),
        ],
      ),
      body: state.isLoadingPrice && state.isLoadingReview
          ? const Center(child: CircularProgressIndicator())
          : state.error != null
              ? Center(
                  child: Padding(
                      padding: const EdgeInsets.all(32),
                      child: Text(state.error!,
                          textAlign: TextAlign.center,
                          style: TextStyle(color: theme.colorScheme.error))),
                )
              : SingleChildScrollView(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // Price history section
                      if (state.priceHistory != null) ...[
                        _PriceHistorySection(history: state.priceHistory!),
                        const SizedBox(height: 24),
                      ],

                      // Review summary section
                      if (state.reviewSummary != null) ...[
                        _ReviewSummarySection(summary: state.reviewSummary!),
                      ],
                    ],
                  ),
                ),
    );
  }
}

class _PriceHistorySection extends StatelessWidget {
  final PriceHistoryEntity history;

  const _PriceHistorySection({required this.history});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text('价格走势', style: theme.textTheme.titleMedium),
            const SizedBox(width: 8),
            _TrendBadge(trend: history.trend),
          ],
        ),
        const SizedBox(height: 8),

        // Price summary cards
        Row(
          children: [
            Expanded(
              child: _PriceCard(
                label: '当前价格',
                price: history.currentPrice,
                color: theme.colorScheme.primary,
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: _PriceCard(
                label: '最低价',
                price: history.lowestPrice,
                color: Colors.green.shade600,
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: _PriceCard(
                label: '最高价',
                price: history.highestPrice,
                color: Colors.red.shade400,
              ),
            ),
          ],
        ),
        const SizedBox(height: 4),
        Text(
          '过去 ${history.days} 天',
          style: theme.textTheme.bodySmall,
        ),
        const SizedBox(height: 12),

        // Line chart
        Card(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(8, 16, 16, 8),
            child: PriceChart(
              points: history.points,
              lowestPrice: history.lowestPrice,
              highestPrice: history.highestPrice,
            ),
          ),
        ),
        const SizedBox(height: 12),

        // Price points list
        if (history.points.isNotEmpty) ...[
          Text('历史价格记录', style: theme.textTheme.titleSmall),
          const SizedBox(height: 8),
          ListView.builder(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            itemCount: history.points.length,
            itemBuilder: (context, index) {
              final point = history.points[index];
              final isLowest = point.price == history.lowestPrice;
              final isHighest = point.price == history.highestPrice;
              return ListTile(
                dense: true,
                leading: Icon(
                  isLowest
                      ? Icons.arrow_downward
                      : isHighest
                          ? Icons.arrow_upward
                          : Icons.circle,
                  size: 16,
                  color: isLowest
                      ? Colors.green
                      : isHighest
                          ? Colors.red
                          : theme.colorScheme.outline,
                ),
                title: Text(
                  '${point.recordedAt.year}-${point.recordedAt.month.toString().padLeft(2, '0')}-${point.recordedAt.day.toString().padLeft(2, '0')}',
                  style: theme.textTheme.bodySmall,
                ),
                trailing: Text(
                  point.price.toStringAsFixed(2),
                  style: theme.textTheme.bodyMedium?.copyWith(
                    fontWeight: isLowest || isHighest ? FontWeight.bold : null,
                  ),
                ),
              );
            },
          ),
        ],
      ],
    );
  }
}

class _TrendBadge extends StatelessWidget {
  final PriceTrend trend;

  const _TrendBadge({required this.trend});

  @override
  Widget build(BuildContext context) {
    final (Color color, String label) = switch (trend) {
      PriceTrend.low => (Colors.green, '低位'),
      PriceTrend.normal => (Colors.blue, '正常'),
      PriceTrend.high => (Colors.red, '高位'),
      PriceTrend.unknown => (Colors.grey, '未知'),
    };

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: color.withAlpha(25),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: color.withAlpha(80)),
      ),
      child: Text(
        label,
        style:
            TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: color),
      ),
    );
  }
}

class _PriceCard extends StatelessWidget {
  final String label;
  final double price;
  final Color color;

  const _PriceCard({
    required this.label,
    required this.price,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          children: [
            Text(label,
                style: theme.textTheme.labelMedium
                    ?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
            const SizedBox(height: 4),
            Text(
              price.toStringAsFixed(2),
              style: theme.textTheme.titleSmall?.copyWith(
                fontWeight: FontWeight.bold,
                color: color,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ReviewSummarySection extends StatelessWidget {
  final ReviewSummaryEntity summary;

  const _ReviewSummarySection({required this.summary});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('评价分析', style: theme.textTheme.titleMedium),
        const SizedBox(height: 8),

        // Rating and risk row
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                // Rating
                Expanded(
                  child: Column(
                    children: [
                      Row(
                        children: [
                          Icon(Icons.star,
                              color: Colors.amber.shade600, size: 20),
                          const SizedBox(width: 4),
                          Text(
                            summary.rating.toStringAsFixed(1),
                            style: theme.textTheme.headlineSmall
                                ?.copyWith(fontWeight: FontWeight.bold),
                          ),
                        ],
                      ),
                      const SizedBox(height: 4),
                      Text(
                        '${summary.reviewCount} 条评价',
                        style: theme.textTheme.bodySmall,
                      ),
                    ],
                  ),
                ),

                // Risk score
                Expanded(
                  child: Column(
                    children: [
                      Row(
                        children: [
                          Icon(Icons.shield,
                              color: summary.riskScore > 0.3
                                  ? Colors.red
                                  : Colors.green,
                              size: 20),
                          const SizedBox(width: 4),
                          Text(
                            '${summary.riskPercent.toStringAsFixed(0)}%',
                            style: theme.textTheme.headlineSmall
                                ?.copyWith(fontWeight: FontWeight.bold),
                          ),
                        ],
                      ),
                      const SizedBox(height: 4),
                      Text('风险指数', style: theme.textTheme.bodySmall),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 12),

        // Positive tags
        if (summary.positiveTags.isNotEmpty) ...[
          Text('优点', style: theme.textTheme.titleSmall),
          const SizedBox(height: 4),
          Wrap(
            spacing: 6,
            runSpacing: 4,
            children: summary.positiveTags
                .map((t) => Chip(
                      avatar: const Icon(Icons.thumb_up, size: 14),
                      label: Text(t, style: const TextStyle(fontSize: 12)),
                      backgroundColor: Colors.green.shade50,
                      side: BorderSide(color: Colors.green.shade200),
                      visualDensity: VisualDensity.compact,
                    ))
                .toList(),
          ),
          const SizedBox(height: 12),
        ],

        // Risk tags
        if (summary.riskTags.isNotEmpty) ...[
          Text('风险点', style: theme.textTheme.titleSmall),
          const SizedBox(height: 4),
          Wrap(
            spacing: 6,
            runSpacing: 4,
            children: summary.riskTags
                .map((t) => Chip(
                      avatar: Icon(Icons.warning_amber_rounded,
                          size: 14, color: Colors.orange.shade800),
                      label: Text(t, style: const TextStyle(fontSize: 12)),
                      backgroundColor: Colors.orange.shade50,
                      side: BorderSide(color: Colors.orange.shade200),
                      visualDensity: VisualDensity.compact,
                    ))
                .toList(),
          ),
          const SizedBox(height: 12),
        ],

        // Summary text
        if (summary.summary.isNotEmpty) ...[
          Text('评价摘要', style: theme.textTheme.titleSmall),
          const SizedBox(height: 4),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Text(summary.summary, style: theme.textTheme.bodyMedium),
            ),
          ),
        ],
      ],
    );
  }
}
