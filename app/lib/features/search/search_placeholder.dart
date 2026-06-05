import 'package:flutter/material.dart';
import '../../core/theme/app_theme.dart';

/// Placeholder for search results page.
class SearchPlaceholder extends StatelessWidget {
  const SearchPlaceholder({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(title: const Text('搜索结果')),
      body: const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.search, size: 64, color: AppColors.inkSoft),
            SizedBox(height: 16),
            Text(
              '搜索结果 — 占位',
              style: TextStyle(
                  fontSize: 18, color: AppColors.inkSoft),
            ),
            SizedBox(height: 8),
            Text(
              '商品搜索、自然语言筛选与排序将在后续迭代实现',
              style: TextStyle(
                  fontSize: 14, color: AppColors.inkSoft),
            ),
          ],
        ),
      ),
    );
  }
}
