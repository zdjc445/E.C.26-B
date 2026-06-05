import 'package:flutter/material.dart';
import '../../core/theme/app_theme.dart';

/// Placeholder for recognition result page.
class RecognitionPlaceholder extends StatelessWidget {
  const RecognitionPlaceholder({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(title: const Text('识别结果')),
      body: const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.image_search, size: 64,
                color: AppColors.inkSoft),
            SizedBox(height: 16),
            Text(
              '识别结果 — 占位',
              style: TextStyle(
                  fontSize: 18, color: AppColors.inkSoft),
            ),
            SizedBox(height: 8),
            Text(
              '商品类目识别、关键属性提取与建议卡片将在后续迭代实现',
              style: TextStyle(
                  fontSize: 14, color: AppColors.inkSoft),
            ),
          ],
        ),
      ),
    );
  }
}
