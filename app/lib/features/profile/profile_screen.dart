import 'package:flutter/material.dart';
import '../../core/theme/app_theme.dart';

/// User profile / settings page at /me.
class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(title: const Text('我的')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // ── User info ──
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                children: [
                  Container(
                    width: 48,
                    height: 48,
                    decoration: BoxDecoration(
                      color: AppColors.accent.withAlpha(20),
                      borderRadius: BorderRadius.circular(24),
                    ),
                    child: const Icon(Icons.person,
                        color: AppColors.accent, size: 28),
                  ),
                  const SizedBox(width: 12),
                  const Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('演示用户',
                          style: TextStyle(
                              fontSize: 16, fontWeight: FontWeight.w600)),
                      SizedBox(height: 4),
                      Text('未接入真实登录',
                          style: TextStyle(
                              fontSize: 13, color: AppColors.inkSoft)),
                    ],
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),

          // ── Shopping preferences ──
          _SectionHeader(title: '购物偏好'),
          Card(
            child: Column(
              children: [
                SwitchListTile(
                  title: const Text('价格优先'),
                  subtitle: const Text('优先推荐价格最低的商品'),
                  value: true,
                  onChanged: (_) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(
                          content: Text('偏好设置功能即将上线')),
                    );
                  },
                ),
                const Divider(height: 1),
                SwitchListTile(
                  title: const Text('官方店铺优先'),
                  subtitle: const Text('优先推荐官方旗舰店商品'),
                  value: false,
                  onChanged: (_) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(
                          content: Text('偏好设置功能即将上线')),
                    );
                  },
                ),
                const Divider(height: 1),
                SwitchListTile(
                  title: const Text('配送更快'),
                  subtitle: const Text('优先推荐配送速度快的商品'),
                  value: false,
                  onChanged: (_) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(
                          content: Text('偏好设置功能即将上线')),
                    );
                  },
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),

          // ── Notifications & price alerts ──
          _SectionHeader(title: '通知与价格提醒'),
          Card(
            child: Column(
              children: [
                ListTile(
                  leading: const Icon(Icons.notifications_outlined),
                  title: const Text('价格提醒'),
                  subtitle: const Text('占位'),
                  trailing: const Icon(Icons.chevron_right,
                      color: AppColors.inkSoft),
                  onTap: () {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('价格提醒功能即将上线')),
                    );
                  },
                ),
                const Divider(height: 1),
                ListTile(
                  leading: const Icon(Icons.recommend_outlined),
                  title: const Text('推荐通知'),
                  subtitle: const Text('占位'),
                  trailing: const Icon(Icons.chevron_right,
                      color: AppColors.inkSoft),
                  onTap: () {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('推荐通知功能即将上线')),
                    );
                  },
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),

          // ── Privacy & data ──
          _SectionHeader(title: '隐私与数据'),
          Card(
            child: Column(
              children: [
                ListTile(
                  leading: const Icon(Icons.cleaning_services_outlined),
                  title: const Text('清理本地缓存'),
                  subtitle: const Text('占位'),
                  trailing: const Icon(Icons.chevron_right,
                      color: AppColors.inkSoft),
                  onTap: () {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('缓存清理功能即将上线')),
                    );
                  },
                ),
                const Divider(height: 1),
                ListTile(
                  leading: const Icon(Icons.download_outlined),
                  title: const Text('数据导出'),
                  subtitle: const Text('占位'),
                  trailing: const Icon(Icons.chevron_right,
                      color: AppColors.inkSoft),
                  onTap: () {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('数据导出功能即将上线')),
                    );
                  },
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),

          // ── API status ──
          _SectionHeader(title: '接口状态'),
          Card(
            child: Column(
              children: const [
                ListTile(
                  leading: Icon(Icons.smart_toy_outlined),
                  title: Text('AI Provider'),
                  subtitle: Text('mock'),
                ),
                Divider(height: 1),
                ListTile(
                  leading: Icon(Icons.storage_outlined),
                  title: Text('历史存储'),
                  subtitle: Text('memory'),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),

          // ── About ──
          _SectionHeader(title: '关于项目'),
          Card(
            child: const ListTile(
              leading: Icon(Icons.info_outline),
              title: Text('当前阶段'),
              subtitle: Text('聊天式 Mock Agent 闭环阶段'),
            ),
          ),
          const SizedBox(height: 24),
        ],
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final String title;
  const _SectionHeader({required this.title});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(left: 2, bottom: 8),
      child: Text(title,
          style: const TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w600,
              color: AppColors.inkSoft)),
    );
  }
}
