import 'package:flutter/material.dart';
import '../../core/theme/app_theme.dart';

/// Placeholder for cross-platform price comparison page.
class ComparisonPlaceholder extends StatelessWidget {
  const ComparisonPlaceholder({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(title: const Text('跨平台比价')),
      body: const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.compare_arrows, size: 64,
                color: AppColors.inkSoft),
            SizedBox(height: 16),
            Text(
              '跨平台比价 — 占位',
              style: TextStyle(
                  fontSize: 18, color: AppColors.inkSoft),
            ),
            SizedBox(height: 8),
            Text(
              '多平台价格聚合与对比将在后续迭代实现',
              style: TextStyle(
                  fontSize: 14, color: AppColors.inkSoft),
            ),
          ],
        ),
      ),
    );
  }
}
