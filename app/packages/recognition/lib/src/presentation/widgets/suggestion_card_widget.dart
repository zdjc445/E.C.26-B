import 'package:app_core/app_core.dart';
import 'package:flutter/material.dart';
import '../../domain/entities/suggestion_card.dart';

class SuggestionCardWidget extends StatelessWidget {
  final SuggestionCard card;
  final VoidCallback? onTap;

  const SuggestionCardWidget({
    super.key,
    required this.card,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final tone = _tone(card.action);
    final actionText = card.actionLabel ?? _defaultActionLabel(card.action);

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(8),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 11),
        child: Row(
          children: [
            Container(
              width: 38,
              height: 38,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: tone.color.withAlpha(18),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: tone.color.withAlpha(62)),
              ),
              child:
                  Icon(_actionIcon(card.action), color: tone.color, size: 20),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          card.title,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style:
                              Theme.of(context).textTheme.titleSmall?.copyWith(
                                    fontWeight: FontWeight.w600,
                                  ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Text(
                        actionText,
                        style: TextStyle(
                          color: tone.color,
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                  if (card.description.isNotEmpty) ...[
                    const SizedBox(height: 4),
                    Text(
                      card.description,
                      style: Theme.of(context).textTheme.bodySmall,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(width: 8),
            Icon(
              Icons.chevron_right,
              color: onTap == null ? AppColors.line : AppColors.inkSoft,
              size: 20,
            ),
          ],
        ),
      ),
    );
  }

  IconData _actionIcon(SuggestionAction action) {
    return switch (action) {
      SuggestionAction.buy => Icons.shopping_bag_outlined,
      SuggestionAction.wait => Icons.schedule,
      SuggestionAction.avoid => Icons.warning_amber_outlined,
      SuggestionAction.compare => Icons.compare_arrows,
    };
  }

  String _defaultActionLabel(SuggestionAction action) {
    return switch (action) {
      SuggestionAction.buy => '可购买',
      SuggestionAction.wait => '先观察',
      SuggestionAction.avoid => '需谨慎',
      SuggestionAction.compare => '去比较',
    };
  }

  _SuggestionTone _tone(SuggestionAction action) {
    return switch (action) {
      SuggestionAction.buy => const _SuggestionTone(AppColors.good),
      SuggestionAction.wait => const _SuggestionTone(AppColors.warn),
      SuggestionAction.avoid => const _SuggestionTone(AppColors.priceRed),
      SuggestionAction.compare => const _SuggestionTone(AppColors.signal),
    };
  }
}

class _SuggestionTone {
  final Color color;

  const _SuggestionTone(this.color);
}
