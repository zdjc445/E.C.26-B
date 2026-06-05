import 'package:flutter/material.dart';
import '../../core/theme/app_theme.dart';

/// Placeholder for login / entry page.
class LoginPlaceholder extends StatelessWidget {
  const LoginPlaceholder({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(title: const Text('登录')),
      body: const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.login, size: 64, color: AppColors.inkSoft),
            SizedBox(height: 16),
            Text(
              '登录页面 — 占位',
              style: TextStyle(
                  fontSize: 18, color: AppColors.inkSoft),
            ),
            SizedBox(height: 8),
            Text(
              '用户认证功能将在后续迭代实现',
              style: TextStyle(
                  fontSize: 14, color: AppColors.inkSoft),
            ),
          ],
        ),
      ),
    );
  }
}
