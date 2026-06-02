import 'package:app_core/app_core.dart';
import 'package:flutter/material.dart';

/// Segmented control for choosing the data source type.
class SourceTypeSelector extends StatelessWidget {
  final SourceType selected;
  final ValueChanged<SourceType> onChanged;

  const SourceTypeSelector({
    super.key,
    required this.selected,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    const types = SourceType.values;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      child: SegmentedButton<SourceType>(
        segments: types.map((t) {
          return ButtonSegment<SourceType>(
            value: t,
            label: Text(_label(t), style: const TextStyle(fontSize: 12)),
            icon: Icon(_icon(t), size: 16),
          );
        }).toList(),
        selected: {selected},
        onSelectionChanged: (set) => onChanged(set.first),
        style: const ButtonStyle(
          visualDensity: VisualDensity.compact,
          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
        ),
      ),
    );
  }

  String _label(SourceType type) {
    return switch (type) {
      SourceType.mock => '模拟',
      SourceType.officialApi => '官方API',
      SourceType.sampleDataset => '样本',
    };
  }

  IconData _icon(SourceType type) {
    return switch (type) {
      SourceType.mock => Icons.science,
      SourceType.officialApi => Icons.api,
      SourceType.sampleDataset => Icons.dataset,
    };
  }
}
