import 'package:flutter/material.dart';
import '../../domain/entities/comparison_entity.dart';

/// Horizontally scrollable comparison table showing all product items
/// side by side with key attributes as rows.
class ComparisonTable extends StatelessWidget {
  final List<ComparisonItem> items;

  const ComparisonTable({super.key, required this.items});

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) {
      return const Center(child: Text('暂无对比数据'));
    }

    final theme = Theme.of(context);

    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: DataTable(
        columnSpacing: 16,
        headingRowColor: WidgetStateProperty.all(
          theme.colorScheme.surfaceContainerHighest,
        ),
        columns: [
          const DataColumn(label: Text('属性')),
          ...items.map((item) => DataColumn(
                label: SizedBox(
                  width: 140,
                  child: Text(
                    item.platform,
                    textAlign: TextAlign.center,
                    style: theme.textTheme.titleSmall
                        ?.copyWith(fontWeight: FontWeight.bold),
                  ),
                ),
              )),
        ],
        rows: [
          _buildRow(context, '商品名称', items.map((i) => i.title).toList()),
          _buildRow(
            context,
            '价格',
            items.map((i) => '${i.price.currency} ${i.price.amount}').toList(),
          ),
          _buildRow(
            context,
            '店铺',
            items.map((i) => i.store ?? '-').toList(),
          ),
          _buildRow(
            context,
            '评分',
            items
                .map((i) =>
                    i.rating != null ? i.rating!.toStringAsFixed(1) : '-')
                .toList(),
          ),
          _buildRow(
            context,
            '评价数',
            items.map((i) => i.reviewCount?.toString() ?? '-').toList(),
          ),
          _buildRow(
            context,
            '库存',
            items.map((i) => i.inStock ? '有货' : '缺货').toList(),
          ),
          _buildRow(
            context,
            '配送',
            items.map((i) => i.deliveryInfo ?? '-').toList(),
          ),
          _buildRow(
            context,
            '特点',
            items
                .map((i) =>
                    i.features.join('、').isEmpty ? '-' : i.features.join('、'))
                .toList(),
          ),
        ],
      ),
    );
  }

  DataRow _buildRow(BuildContext context, String label, List<String> values) {
    return DataRow(cells: [
      DataCell(
          Text(label, style: const TextStyle(fontWeight: FontWeight.w600))),
      ...values.map((v) => DataCell(SizedBox(
            width: 140,
            child: Text(v, textAlign: TextAlign.center),
          ))),
    ]);
  }
}
