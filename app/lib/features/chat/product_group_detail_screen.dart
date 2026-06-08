import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/theme/app_theme.dart';
import '../auth/auth_controller.dart';
import 'chat_models.dart';
import 'chat_providers.dart';

/// Full-screen product group detail page.
/// Shows: hero image, product info, highlights, platform comparison list.
class ProductGroupDetailScreen extends ConsumerWidget {
  final ProductGroup group;

  const ProductGroupDetailScreen({super.key, required this.group});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text('商品详情'),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
        children: [
          _buildHeader(context),
          const SizedBox(height: 16),
          _buildPriceSection(),
          if (group.highlights.isNotEmpty) ...[
            const SizedBox(height: 14),
            _buildHighlights(),
          ],
          const SizedBox(height: 20),
          const Text('平台比价',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
          const SizedBox(height: 10),
          ...group.platforms.map((p) => _buildPlatformCard(context, ref, p)),
        ],
      ),
    );
  }

  Widget _buildHeader(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Large thumbnail
        ClipRRect(
          borderRadius: BorderRadius.circular(10),
          child: _buildThumbnail(),
        ),
        const SizedBox(height: 14),
        // Product title
        Text(group.displayTitle,
            style: const TextStyle(
                fontSize: 20, fontWeight: FontWeight.w700, height: 1.3)),
        const SizedBox(height: 8),
        // Category and brand
        Wrap(
          spacing: 8,
          runSpacing: 6,
          children: [
            if (group.category != null && group.category!.isNotEmpty)
              _infoChip('品类：${group.category}'),
            if (group.brand != null && group.brand!.isNotEmpty)
              _infoChip('品牌：${group.brand}'),
          ],
        ),
      ],
    );
  }

  Widget _buildThumbnail() {
    final url = group.thumbnailUrl?.trim() ?? '';
    if (url.startsWith('http://') || url.startsWith('https://')) {
      return Image.network(
        url,
        width: double.infinity,
        height: 220,
        fit: BoxFit.cover,
        errorBuilder: (_, __, ___) => _thumbnailPlaceholder(),
      );
    }
    return _thumbnailPlaceholder();
  }

  Widget _thumbnailPlaceholder() {
    final accent = switch (group.category ?? '') {
      '耳机' => const Color(0xFF2F343B),
      '吹风机' => const Color(0xFFB23A48),
      '背包' => const Color(0xFFC27A2C),
      '智能手表' => const Color(0xFF4A6FA5),
      _ => AppColors.accent,
    };
    final icon = switch (group.category ?? '') {
      '耳机' => Icons.headphones,
      '吹风机' => Icons.air,
      '背包' => Icons.backpack,
      '智能手表' => Icons.watch,
      _ => Icons.shopping_bag_outlined,
    };
    return Container(
      width: double.infinity,
      height: 220,
      decoration: BoxDecoration(
        color: accent.withAlpha(15),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.line),
      ),
      child: Icon(icon, size: 64, color: accent.withAlpha(120)),
    );
  }

  Widget _buildPriceSection() {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.panel,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text('¥${group.bestPrice.toStringAsFixed(0)}',
                  style: const TextStyle(
                      fontSize: 28,
                      height: 1,
                      fontWeight: FontWeight.w700,
                      color: AppColors.priceRed)),
              if (group.originalPrice > group.bestPrice) ...[
                const SizedBox(width: 10),
                Padding(
                  padding: const EdgeInsets.only(bottom: 3),
                  child: Text('¥${group.originalPrice.toStringAsFixed(0)}',
                      style: const TextStyle(
                          fontSize: 14,
                          color: AppColors.inkSoft,
                          decoration: TextDecoration.lineThrough)),
                ),
              ],
            ],
          ),
          if (group.priceRange != null) ...[
            const SizedBox(height: 6),
            Text(
              '价格区间：¥${group.priceRange!.min.toStringAsFixed(0)} - ¥${group.priceRange!.max.toStringAsFixed(0)}',
              style: const TextStyle(fontSize: 12, color: AppColors.inkSoft),
            ),
          ],
          const SizedBox(height: 6),
          Text('${group.platformCount} 个平台有售',
              style: const TextStyle(fontSize: 12, color: AppColors.inkSoft)),
          if (group.matchLevel != null && group.matchLevel!.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text('匹配状态：${group.matchLevel == "strict" ? "严格匹配" : "放宽匹配"}',
                style: const TextStyle(fontSize: 12, color: AppColors.inkSoft)),
          ],
        ],
      ),
    );
  }

  Widget _buildHighlights() {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: group.highlights.map((h) => _tagBadge(h)).toList(),
    );
  }

  Widget _buildPlatformCard(
      BuildContext context, WidgetRef ref, PlatformOfferSummary p) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.panel,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Platform + shop
          Row(
            children: [
              _platformBadge(p.platform),
              const SizedBox(width: 8),
              Expanded(
                child: Text(p.shopName,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        fontSize: 13, fontWeight: FontWeight.w600)),
              ),
            ],
          ),
          const SizedBox(height: 6),
          // Product title
          if (p.title.isNotEmpty)
            Text(p.title,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 14, height: 1.35)),
          const SizedBox(height: 8),
          // Price row
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text('¥${p.price.toStringAsFixed(0)}',
                  style: const TextStyle(
                      fontSize: 20,
                      height: 1,
                      fontWeight: FontWeight.w700,
                      color: AppColors.priceRed)),
              if (p.originalPrice > p.price) ...[
                const SizedBox(width: 6),
                Padding(
                  padding: const EdgeInsets.only(bottom: 2),
                  child: Text('¥${p.originalPrice.toStringAsFixed(0)}',
                      style: const TextStyle(
                          fontSize: 12,
                          color: AppColors.inkSoft,
                          decoration: TextDecoration.lineThrough)),
                ),
              ],
            ],
          ),
          const SizedBox(height: 8),
          // Rating and sales
          Row(
            children: [
              Text(p.rating > 0 ? '${p.rating.toStringAsFixed(1)}分' : '暂无评分',
                  style:
                      const TextStyle(fontSize: 12, color: AppColors.inkSoft)),
              const SizedBox(width: 10),
              Text(p.sales > 0 ? '${_formatCount(p.sales)}条评价' : '暂无评价',
                  style:
                      const TextStyle(fontSize: 12, color: AppColors.inkSoft)),
            ],
          ),
          // Specs
          if (p.specs.isNotEmpty) ...[
            const SizedBox(height: 8),
            Wrap(
              spacing: 10,
              runSpacing: 4,
              children: p.specs.map((spec) {
                return Text('${spec.label}：${spec.value}',
                    style: const TextStyle(
                        fontSize: 12, color: AppColors.inkSoft));
              }).toList(),
            ),
          ],
          // Tags
          if (p.tags.isNotEmpty) ...[
            const SizedBox(height: 8),
            Wrap(
              spacing: 4,
              runSpacing: 4,
              children: p.tags.map((t) => _tagBadge(t)).toList(),
            ),
          ],
          // Reasons
          if (p.reasons.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(p.reasons.join(' · '),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 11, color: AppColors.inkSoft)),
          ],
          const SizedBox(height: 12),
          // Action buttons
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: () => _showJumpNotice(context, p),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: AppColors.accent,
                    side: const BorderSide(color: AppColors.accent),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8)),
                  ),
                  child: const Text('去平台', style: TextStyle(fontSize: 13)),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: OutlinedButton(
                  onPressed: () => _showPriceAlert(context, ref, p),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: AppColors.inkMain,
                    side: const BorderSide(color: AppColors.line),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8)),
                  ),
                  child: const Text('价格提醒', style: TextStyle(fontSize: 13)),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  void _showJumpNotice(BuildContext context, PlatformOfferSummary p) {
    final platformName = _platformLabel(p.platform);
    showModalBottomSheet(
      context: context,
      builder: (ctx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 14, 16, 16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('即将跳转到$platformName',
                  style: const TextStyle(
                      fontSize: 16, fontWeight: FontWeight.w700)),
              const SizedBox(height: 12),
              Text(p.title.isNotEmpty ? p.title : p.shopName,
                  style: const TextStyle(
                      fontSize: 14, height: 1.35, fontWeight: FontWeight.w600)),
              const SizedBox(height: 6),
              Text(p.shopName,
                  style:
                      const TextStyle(fontSize: 12, color: AppColors.inkSoft)),
              const SizedBox(height: 4),
              Text('¥${p.price.toStringAsFixed(0)}',
                  style: const TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                      color: AppColors.priceRed)),
              const SizedBox(height: 12),
              const Text(
                '当前演示使用 Mock 商品数据，不会打开真实电商页面。正式接入后将跳转到对应平台商品详情页。',
                style: TextStyle(
                    fontSize: 13, height: 1.45, color: AppColors.inkSoft),
              ),
              const SizedBox(height: 14),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: () => Navigator.of(ctx).pop(),
                  child: const Text('知道了'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _showPriceAlert(
      BuildContext context, WidgetRef ref, PlatformOfferSummary p) async {
    final controller = TextEditingController(
        text: p.price > 0 ? p.price.toStringAsFixed(0) : '');
    final result = await showDialog<double>(
      context: context,
      builder: (ctx) {
        return AlertDialog(
          title: const Text('设置价格提醒'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('当 ${p.title.isNotEmpty ? p.title : "该商品"} 价格 ≤ 以下数值时触发：'),
              const SizedBox(height: 8),
              TextField(
                controller: controller,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(prefixText: '¥ '),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(),
              child: const Text('取消'),
            ),
            ElevatedButton(
              onPressed: () {
                final v = double.tryParse(controller.text);
                Navigator.of(ctx).pop(v);
              },
              child: const Text('保存'),
            ),
          ],
        );
      },
    );
    if (result == null || result <= 0) return;
    final messenger = ScaffoldMessenger.of(context);
    try {
      final token = ref.read(authControllerProvider).session?.token;
      await ref.read(priceAlertApiInChatProvider).create({
        'productId': p.productId,
        'title': p.title.isNotEmpty ? p.title : '推荐商品',
        'platform': p.platform,
        'targetPrice': result,
        'note': '从商品详情页创建',
      }, token: token);
      if (context.mounted) {
        messenger.showSnackBar(SnackBar(
          content: Text('已设置价格提醒：¥${result.toStringAsFixed(0)}'),
        ));
      }
    } catch (e) {
      if (context.mounted) {
        messenger.showSnackBar(SnackBar(content: Text('设置失败：$e')));
      }
    }
  }

  Widget _infoChip(String text) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: AppColors.panelSoft,
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: AppColors.line),
      ),
      child: Text(text,
          style: const TextStyle(fontSize: 12, color: AppColors.inkMain)),
    );
  }

  Widget _tagBadge(String text) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
      decoration: BoxDecoration(
        color: AppColors.panelSoft,
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: AppColors.line),
      ),
      child: Text(text,
          style: const TextStyle(fontSize: 11, color: AppColors.inkSoft)),
    );
  }

  Widget _platformBadge(String platform) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
      decoration: BoxDecoration(
        color: AppColors.panelSoft,
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: AppColors.line),
      ),
      child: Text(_platformLabel(platform),
          style: const TextStyle(fontSize: 11, color: AppColors.inkSoft)),
    );
  }

  String _platformLabel(String platform) {
    return switch (platform) {
      '京东-mock' => '京东',
      '拼多多-mock' => '拼多多',
      '淘宝-mock' => '淘宝',
      _ => platform,
    };
  }

  String _formatCount(int value) {
    if (value >= 10000) return '${(value / 10000).toStringAsFixed(1)}万';
    return value.toString();
  }
}
