import 'package:app_core/app_core.dart';
import 'package:flutter/material.dart';

/// Horizontal tab bar for sort mode selection.
class SortTabBar extends StatelessWidget {
  final SortMode selected;
  final ValueChanged<SortMode> onChanged;

  const SortTabBar({
    super.key,
    required this.selected,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    const modes = SortMode.values;

    return Container(
      height: 40,
      color: Theme.of(context).colorScheme.surface,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 12),
        itemCount: modes.length,
        separatorBuilder: (_, __) => const SizedBox(width: 4),
        itemBuilder: (context, index) {
          final mode = modes[index];
          final isSelected = mode == selected;
          return TextButton(
            onPressed: () => onChanged(mode),
            style: TextButton.styleFrom(
              foregroundColor: isSelected
                  ? Theme.of(context).colorScheme.primary
                  : Colors.grey,
              backgroundColor: isSelected
                  ? Theme.of(context).colorScheme.primary.withValues(alpha: 0.1)
                  : Colors.transparent,
              padding: const EdgeInsets.symmetric(horizontal: 14),
              minimumSize: const Size(0, 34),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(17),
              ),
            ),
            child: Text(
              mode.displayName,
              style: TextStyle(
                fontSize: 13,
                fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
              ),
            ),
          );
        },
      ),
    );
  }
}
