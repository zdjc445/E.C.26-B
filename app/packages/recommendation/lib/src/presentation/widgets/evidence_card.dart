import 'package:flutter/material.dart';
import '../../domain/entities/recommendation_entity.dart';

/// A card displaying a single evidence item with its type label.
class EvidenceCard extends StatelessWidget {
  final RecommendationEvidence evidence;

  const EvidenceCard({super.key, required this.evidence});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.secondaryContainer,
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(
                    evidence.type,
                    style: theme.textTheme.labelSmall?.copyWith(
                      color: theme.colorScheme.onSecondaryContainer,
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    '商品 ${evidence.platformProductId}',
                    style: theme.textTheme.bodySmall,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(evidence.content, style: theme.textTheme.bodyMedium),
          ],
        ),
      ),
    );
  }
}
