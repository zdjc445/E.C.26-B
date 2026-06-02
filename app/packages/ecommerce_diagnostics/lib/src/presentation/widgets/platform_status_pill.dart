import 'package:flutter/material.dart';
import 'package:app_core/app_core.dart';
import '../../domain/entities/ecommerce_status_entity.dart';

/// A compact pill-shaped chip showing a platform's status.
class PlatformStatusPill extends StatelessWidget {
  final EcommerceProviderStatus status;

  const PlatformStatusPill({super.key, required this.status});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    Color pillColor;
    String label;
    IconData icon;

    if (status.configured) {
      pillColor = AppColors.good;
      label = '已配置';
      icon = Icons.check_circle;
    } else if (status.enabled) {
      pillColor = AppColors.warn;
      label = '配置中';
      icon = Icons.settings;
    } else {
      pillColor = AppColors.inkSoft;
      label = '未启用';
      icon = Icons.block;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: pillColor.withAlpha(30),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: pillColor.withAlpha(80)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: pillColor),
          const SizedBox(width: 5),
          Text(
            _platformLabel(status.platform),
            style: theme.textTheme.bodyMedium?.copyWith(
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(width: 8),
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: pillColor,
            ),
          ),
          const SizedBox(width: 4),
          Text(
            label,
            style: TextStyle(
              fontSize: 11,
              color: pillColor,
              fontWeight: FontWeight.w500,
            ),
          ),
          if (status.missingConfig.isNotEmpty) ...[
            const SizedBox(width: 8),
            Tooltip(
              message: '缺少: ${status.missingConfig.join(', ')}',
              child: Icon(
                Icons.info_outline,
                size: 14,
                color: pillColor,
              ),
            ),
          ],
        ],
      ),
    );
  }

  String _platformLabel(String platform) {
    switch (platform.toLowerCase()) {
      case 'jd':
        return '京东';
      case 'taobao':
        return '淘宝';
      case 'pdd':
        return '拼多多';
      case 'tmall':
        return '天猫';
      default:
        return platform;
    }
  }
}
