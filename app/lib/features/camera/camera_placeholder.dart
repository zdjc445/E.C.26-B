import 'package:flutter/material.dart';
import '../../core/theme/app_theme.dart';

/// Placeholder for camera capture page.
class CameraPlaceholder extends StatelessWidget {
  const CameraPlaceholder({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(title: const Text('拍照识物')),
      body: const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.camera_alt_outlined, size: 64,
                color: AppColors.inkSoft),
            SizedBox(height: 16),
            Text(
              '拍照识物 — 占位',
              style: TextStyle(
                  fontSize: 18, color: AppColors.inkSoft),
            ),
            SizedBox(height: 8),
            Text(
              '相机采集与图片上传功能将在后续迭代实现',
              style: TextStyle(
                  fontSize: 14, color: AppColors.inkSoft),
            ),
          ],
        ),
      ),
    );
  }
}
