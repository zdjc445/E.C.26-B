import 'package:flutter/material.dart';
import '../../core/theme/app_theme.dart';
import '../ecommerce/ecommerce_api.dart';
import 'health_api.dart';

/// Developer debug screen hidden behind long-press on "关于识价镜".
/// Shows backend provider status, auth mode, storage backend, etc.
class DebugScreen extends StatelessWidget {
  final HealthStatus health;
  final EcommerceStatus ecom;
  const DebugScreen({super.key, required this.health, required this.ecom});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(title: const Text('开发者调试')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _SectionHeader(title: '运行状态'),
          Card(
            child: Column(
              children: [
                _row(
                    Icons.smart_toy_outlined, 'AI Provider', health.aiProvider),
                const Divider(height: 1),
                _row(Icons.storage_outlined, '持久化存储', health.persistenceStore),
                const Divider(height: 1),
                _row(Icons.shopping_bag_outlined, '商品数据源', ecom.activeProvider),
                const Divider(height: 1),
                _row(Icons.lock_outlined, '认证模式',
                    health.authEnabled ? 'JWT 启用' : 'authEnabled=false'),
                const Divider(height: 1),
                _row(Icons.mic_outlined, '语音 Provider', health.voiceProvider),
                const Divider(height: 1),
                _row(Icons.developer_mode, '当前阶段', health.stage),
              ],
            ),
          ),
          const SizedBox(height: 12),
          _SectionHeader(title: '电商 Provider 详情'),
          Card(
            child: Column(
              children: [
                _row(Icons.power, 'realProviderEnabled',
                    '${ecom.realProviderEnabled}'),
                const Divider(height: 1),
                _row(Icons.power_outlined, 'realProviderActive',
                    '${ecom.realProviderActive}'),
                const Divider(height: 1),
                _row(Icons.link, 'realProviderBaseUrl',
                    ecom.realProviderBaseUrl ?? 'null'),
              ],
            ),
          ),
          const SizedBox(height: 24),
        ],
      ),
    );
  }

  Widget _row(IconData icon, String label, String value) {
    return ListTile(
      leading: Icon(icon, size: 20, color: AppColors.inkSoft),
      title: Text(label, style: const TextStyle(fontSize: 13)),
      subtitle: Text(value,
          style: const TextStyle(fontSize: 12, color: AppColors.inkSoft)),
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
