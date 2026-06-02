import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import '../../domain/entities/price_history_entity.dart';

/// A fl_chart LineChart wrapper that renders a product's price history curve.
class PriceChart extends StatelessWidget {
  final List<PricePoint> points;
  final double lowestPrice;
  final double highestPrice;

  const PriceChart({
    super.key,
    required this.points,
    required this.lowestPrice,
    required this.highestPrice,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    if (points.isEmpty) {
      return const SizedBox(
        height: 200,
        child: Center(child: Text('暂无价格历史数据')),
      );
    }

    // Sort points chronologically.
    final sorted = List<PricePoint>.from(points)
      ..sort((a, b) => a.recordedAt.compareTo(b.recordedAt));

    final padding = (highestPrice - lowestPrice) * 0.1;
    final minY = (lowestPrice - padding).clamp(0.0, double.infinity);
    final maxY = highestPrice + padding;

    final spots = sorted
        .asMap()
        .entries
        .map((entry) => FlSpot(
              entry.key.toDouble(),
              entry.value.price,
            ))
        .toList();

    return SizedBox(
      height: 240,
      child: LineChart(
        LineChartData(
          minY: minY,
          maxY: maxY,
          gridData: FlGridData(
            show: true,
            drawVerticalLine: false,
            horizontalInterval: (maxY - minY) / 4,
            getDrawingHorizontalLine: (value) => FlLine(
              color: theme.colorScheme.outline.withAlpha(40),
              strokeWidth: 1,
            ),
          ),
          titlesData: FlTitlesData(
            topTitles: const AxisTitles(
              sideTitles: SideTitles(showTitles: false),
            ),
            rightTitles: const AxisTitles(
              sideTitles: SideTitles(showTitles: false),
            ),
            bottomTitles: AxisTitles(
              axisNameWidget: Text('日期', style: theme.textTheme.bodySmall),
              sideTitles: SideTitles(
                showTitles: true,
                reservedSize: 30,
                interval: (sorted.length / 5)
                    .ceilToDouble()
                    .clamp(1, double.infinity),
                getTitlesWidget: (value, meta) {
                  final idx = value.toInt();
                  if (idx < 0 || idx >= sorted.length) {
                    return const SizedBox.shrink();
                  }
                  final date = sorted[idx].recordedAt;
                  return Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: Text(
                      '${date.month}/${date.day}',
                      style: theme.textTheme.labelSmall,
                    ),
                  );
                },
              ),
            ),
            leftTitles: AxisTitles(
              axisNameWidget: Text('价格', style: theme.textTheme.bodySmall),
              sideTitles: SideTitles(
                showTitles: true,
                reservedSize: 42,
                getTitlesWidget: (value, meta) {
                  return Text(
                    value.toStringAsFixed(0),
                    style: theme.textTheme.labelSmall,
                  );
                },
              ),
            ),
          ),
          borderData: FlBorderData(
            show: true,
            border: Border(
              bottom: BorderSide(color: theme.colorScheme.outline),
              left: BorderSide(color: theme.colorScheme.outline),
            ),
          ),
          lineTouchData: LineTouchData(
            touchTooltipData: LineTouchTooltipData(
              getTooltipItems: (touchedSpots) {
                return touchedSpots.map((spot) {
                  final idx = spot.x.toInt();
                  final date = (idx >= 0 && idx < sorted.length)
                      ? sorted[idx].recordedAt
                      : null;
                  return LineTooltipItem(
                    '${date != null ? '${date.month}/${date.day}' : ''}  ${spot.y.toStringAsFixed(2)}',
                    TextStyle(
                      color: theme.colorScheme.onInverseSurface,
                      fontSize: 12,
                    ),
                  );
                }).toList();
              },
            ),
          ),
          lineBarsData: [
            LineChartBarData(
              spots: spots,
              isCurved: true,
              color: theme.colorScheme.primary,
              barWidth: 2.5,
              dotData: FlDotData(
                show: sorted.length <= 30,
              ),
              belowBarData: BarAreaData(
                show: true,
                color: theme.colorScheme.primary.withAlpha(25),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
