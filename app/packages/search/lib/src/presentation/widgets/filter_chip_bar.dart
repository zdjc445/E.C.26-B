import 'package:flutter/material.dart';
import '../../domain/entities/filter_criteria.dart';

/// Horizontal scrollable row of active filter chips with clear-all option.
class FilterChipBar extends StatelessWidget {
  final FilterCriteria filters;
  final VoidCallback? onClearAll;
  final VoidCallback? onPriceTap;
  final VoidCallback? onRatingTap;
  final VoidCallback? onOfficialTap;
  final VoidCallback? onSelfOperatedTap;
  final VoidCallback? onBrandTap;

  const FilterChipBar({
    super.key,
    required this.filters,
    this.onClearAll,
    this.onPriceTap,
    this.onRatingTap,
    this.onOfficialTap,
    this.onSelfOperatedTap,
    this.onBrandTap,
  });

  @override
  Widget build(BuildContext context) {
    if (!filters.hasFilters) {
      return const SizedBox(height: 4);
    }

    final chips = <Widget>[];

    if (filters.isPriceFilterApplied) {
      final label = StringBuffer('价格: ');
      if (filters.priceMin != null) label.write('\u{ffe5}${filters.priceMin!.toStringAsFixed(0)}');
      label.write(' - ');
      if (filters.priceMax != null) label.write('\u{ffe5}${filters.priceMax!.toStringAsFixed(0)}');
      chips.add(_chip(label.toString(), onPriceTap));
    }
    if (filters.minRating != null) {
      chips.add(_chip('${filters.minRating!.toStringAsFixed(1)}分以上', onRatingTap));
    }
    if (filters.officialOnly == true) {
      chips.add(_chip('官方旗舰', onOfficialTap));
    }
    if (filters.selfOperatedOnly == true) {
      chips.add(_chip('自营', onSelfOperatedTap));
    }
    if (filters.brand != null && filters.brand!.isNotEmpty) {
      chips.add(_chip('品牌: ${filters.brand}', onBrandTap));
    }

    chips.add(
      ActionChip(
        avatar: const Icon(Icons.close, size: 14),
        label: const Text('清除', style: TextStyle(fontSize: 11)),
        onPressed: onClearAll,
        visualDensity: VisualDensity.compact,
        materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
      ),
    );

    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      child: Row(children: chips.map((c) => Padding(
        padding: const EdgeInsets.only(right: 6),
        child: c,
      )).toList()),
    );
  }

  Widget _chip(String label, VoidCallback? onTap) {
    return FilterChip(
      label: Text(label, style: const TextStyle(fontSize: 11)),
      selected: true,
      onSelected: (_) => onTap?.call(),
      visualDensity: VisualDensity.compact,
      materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
    );
  }
}
