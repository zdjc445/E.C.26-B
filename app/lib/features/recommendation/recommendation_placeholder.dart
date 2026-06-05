import 'package:flutter/material.dart';
import '../../core/theme/app_theme.dart';

/// Placeholder for recommendation page.
class RecommendationPlaceholder extends StatelessWidget {
  const RecommendationPlaceholder({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(title: const Text('购买推荐')),
      body: const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.recommend, size: 64,
                color: AppColors.inkSoft),
            SizedBox(height: 16),
            Text(
              '购买推荐 — 占位',
              style: TextStyle(
                  fontSize: 18, color: AppColors.inkSoft),
            ),
            SizedBox(height: 8),
            Text(
              'Agent 决策推荐与证据链展示将在后续迭代实现',
              style: TextStyle(
                  fontSize: 14, color: AppColors.inkSoft),
            ),
          ],
        ),
      ),
    );
  }
}
