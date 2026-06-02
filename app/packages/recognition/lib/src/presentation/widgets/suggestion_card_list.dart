import 'package:app_core/app_core.dart';
import 'package:flutter/material.dart';
import '../../domain/entities/suggestion_card.dart';
import 'suggestion_card_widget.dart';

class SuggestionCardList extends StatelessWidget {
  final List<SuggestionCard> cards;
  final void Function(SuggestionCard card)? onCardTap;

  const SuggestionCardList({
    super.key,
    required this.cards,
    this.onCardTap,
  });

  @override
  Widget build(BuildContext context) {
    if (cards.isEmpty) {
      return const SizedBox.shrink();
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Text('下一步建议', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                '基于识别结果生成',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 4),
              decoration: BoxDecoration(
                color: AppColors.panelSoft,
                borderRadius: BorderRadius.circular(6),
                border: Border.all(color: AppColors.line),
              ),
              child: Text(
                '${cards.length} 项',
                style: Theme.of(context).textTheme.labelMedium,
              ),
            ),
          ],
        ),
        const SizedBox(height: 10),
        Container(
          decoration: BoxDecoration(
            color: AppColors.panel,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: AppColors.line),
          ),
          child: Column(
            children: [
              for (var index = 0; index < cards.length; index++) ...[
                SuggestionCardWidget(
                  card: cards[index],
                  onTap:
                      onCardTap != null ? () => onCardTap!(cards[index]) : null,
                ),
                if (index != cards.length - 1)
                  const Divider(height: 1, indent: 62),
              ],
            ],
          ),
        ),
      ],
    );
  }
}
