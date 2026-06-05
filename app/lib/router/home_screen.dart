import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../core/theme/app_theme.dart';

/// Home screen with navigation to all placeholder feature pages.
class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(title: const Text('E.C.26-B')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _NavCard(
            icon: Icons.login,
            title: '登录 / 入口',
            subtitle: '用户认证占位页面',
            onTap: () => context.go('/login'),
          ),
          _NavCard(
            icon: Icons.camera_alt_outlined,
            title: '拍照识物',
            subtitle: '相机采集与上传占位',
            onTap: () => context.go('/camera'),
          ),
          _NavCard(
            icon: Icons.image_search,
            title: '识别结果',
            subtitle: '商品识别结果展示占位',
            onTap: () => context.go('/recognition'),
          ),
          _NavCard(
            icon: Icons.search,
            title: '搜索结果',
            subtitle: '商品搜索与筛选占位',
            onTap: () => context.go('/search'),
          ),
          _NavCard(
            icon: Icons.compare_arrows,
            title: '跨平台比价',
            subtitle: '多平台价格对比占位',
            onTap: () => context.go('/comparison'),
          ),
          _NavCard(
            icon: Icons.recommend,
            title: '购买推荐',
            subtitle: 'Agent 决策推荐占位',
            onTap: () => context.go('/recommendation'),
          ),
        ],
      ),
    );
  }
}

class _NavCard extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  const _NavCard({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: Icon(icon, color: AppColors.accent),
        title: Text(title),
        subtitle: Text(subtitle),
        trailing:
            const Icon(Icons.chevron_right, color: AppColors.inkSoft),
        onTap: onTap,
      ),
    );
  }
}
