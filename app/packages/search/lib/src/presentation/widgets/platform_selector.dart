import 'package:app_core/app_core.dart';
import 'package:flutter/material.dart';

/// Multi-select toggle chips for choosing which platforms to search.
class PlatformSelector extends StatelessWidget {
  final Set<Platform> selectedPlatforms;
  final ValueChanged<Platform> onToggle;

  const PlatformSelector({
    super.key,
    required this.selectedPlatforms,
    required this.onToggle,
  });

  @override
  Widget build(BuildContext context) {
    final platforms = Platform.values.where((p) => p != Platform.other);

    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      child: Row(
        children: platforms.map((p) {
          final isSelected = selectedPlatforms.contains(p);
          return Padding(
            padding: const EdgeInsets.only(right: 6),
            child: FilterChip(
              label: Text(
                _platformName(p),
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
                ),
              ),
              selected: isSelected,
              onSelected: (_) => onToggle(p),
              visualDensity: VisualDensity.compact,
              materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
              avatar: isSelected ? Icon(_platformIcon(p), size: 16) : null,
              selectedColor: _platformColor(p).withValues(alpha: 0.15),
              checkmarkColor: _platformColor(p),
            ),
          );
        }).toList(),
      ),
    );
  }

  String _platformName(Platform platform) {
    return switch (platform) {
      Platform.jd => '京东',
      Platform.taobao => '淘宝',
      Platform.pdd => '拼多多',
      Platform.tmall => '天猫',
      Platform.other => '其他',
    };
  }

  IconData _platformIcon(Platform platform) {
    return switch (platform) {
      Platform.jd => Icons.store,
      Platform.taobao => Icons.shopping_bag,
      Platform.pdd => Icons.discount,
      Platform.tmall => Icons.store_mall_directory,
      Platform.other => Icons.more_horiz,
    };
  }

  Color _platformColor(Platform platform) {
    return switch (platform) {
      Platform.jd => Colors.red,
      Platform.taobao => Colors.orange,
      Platform.pdd => Colors.deepOrange,
      Platform.tmall => Colors.purple,
      Platform.other => Colors.grey,
    };
  }
}
