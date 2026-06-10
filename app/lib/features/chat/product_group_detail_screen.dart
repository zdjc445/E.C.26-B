import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/theme/app_theme.dart';
import '../auth/auth_controller.dart';
import '../memory/behavior_events.dart';
import 'chat_models.dart';
import 'chat_providers.dart';

/// Full-screen product group detail page.
/// Shows: hero image, product info, highlights, platform comparison list.
class ProductGroupDetailScreen extends ConsumerWidget {
  final ProductGroup group;

  const ProductGroupDetailScreen({super.key, required this.group});

  // Track viewed products in-session to avoid duplicate productView events
  static final _viewedThisSession = <String>{};

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Record product view event once per session
    if (_viewedThisSession.add(group.groupId)) {
      final cheapest = group.platforms.isNotEmpty
          ? group.platforms.reduce((a, b) => a.price < b.price ? a : b)
          : null;
      ref.read(behaviorRecorderProvider).record(BehaviorEventType.productView,
        productId: group.groupId,
        category: group.category,
        brand: group.brand,
        price: group.bestPrice,
        platform: cheapest?.platform,
        tags: cheapest?.tags,
      );
    }

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
    final hasThumbnail = _hasRemoteThumbnail();
    if (!hasThumbnail) {
      return Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(8),
            child: _buildThumbnail(width: 88, height: 88, iconSize: 34),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: _buildHeaderText(),
          ),
        ],
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(10),
          child: _buildThumbnail(height: 184, iconSize: 56),
        ),
        const SizedBox(height: 14),
        _buildHeaderText(),
      ],
    );
  }

  Widget _buildHeaderText() {
    // Build a natural subtitle: "Nike · 跑步鞋" instead of template chips
    final subtitleParts = <String>[];
    if (group.brand != null && group.brand!.isNotEmpty) {
      subtitleParts.add(group.brand!);
    }
    if (group.category != null && group.category!.isNotEmpty) {
      subtitleParts.add(group.category!);
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(group.displayTitle,
            style: const TextStyle(
                fontSize: 20, fontWeight: FontWeight.w700, height: 1.25)),
        if (subtitleParts.isNotEmpty) ...[
          const SizedBox(height: 6),
          Text(subtitleParts.join(' · '),
              style: const TextStyle(
                  fontSize: 13, color: AppColors.inkSoft)),
        ],
      ],
    );
  }

  bool _hasRemoteThumbnail() {
    return _bestThumbnailUrl.isNotEmpty;
  }

  String get _bestThumbnailUrl {
    // Prefer the group's thumbnailUrl, then the first platform's imageUrl.
    final groupUrl = group.thumbnailUrl?.trim() ?? '';
    if (groupUrl.startsWith('http://') || groupUrl.startsWith('https://')) {
      return groupUrl;
    }
    if (group.platforms.isNotEmpty) {
      final platformUrl = group.platforms.first.imageUrl.trim();
      if (platformUrl.startsWith('http://') || platformUrl.startsWith('https://')) {
        return platformUrl;
      }
    }
    return '';
  }

  Widget _buildThumbnail(
      {double width = double.infinity,
      required double height,
      required double iconSize}) {
    final url = _bestThumbnailUrl;
    if (url.isNotEmpty) {
      return Image.network(
        url,
        width: width,
        height: height,
        fit: BoxFit.cover,
        loadingBuilder: (_, child, progress) {
          if (progress == null) return child;
          return _thumbnailPlaceholder(
              width: width, height: height, iconSize: iconSize);
        },
        errorBuilder: (_, __, ___) => _thumbnailPlaceholder(
            width: width, height: height, iconSize: iconSize),
      );
    }
    return _thumbnailPlaceholder(
        width: width, height: height, iconSize: iconSize);
  }

  Widget _thumbnailPlaceholder(
      {required double width,
      required double height,
      required double iconSize}) {
    final colors = _detailThumbColors(group.category ?? '');
    final brand = group.brand ?? '';
    final initial = brand.isNotEmpty ? brand[0] : '商';

    return Container(
      key: const Key('product_detail_thumbnail_placeholder'),
      width: width,
      height: height,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(12),
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [colors.bg, colors.bg2],
        ),
      ),
      child: Stack(
        children: [
          Positioned(
            right: -width * 0.1,
            bottom: -height * 0.05,
            child: Icon(colors.icon, size: iconSize * 1.2,
                color: Colors.white.withAlpha(25)),
          ),
          Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(initial,
                    style: TextStyle(
                        fontSize: iconSize * 0.55,
                        fontWeight: FontWeight.w700,
                        color: Colors.white)),
                if (brand.length > 1)
                  Text(brand,
                      style: TextStyle(
                          fontSize: iconSize * 0.2,
                          fontWeight: FontWeight.w500,
                          color: Colors.white.withAlpha(200))),
              ],
            ),
          ),
        ],
      ),
    );
  }

  _DetailThumbColors _detailThumbColors(String cat) => switch (cat) {
    '运动鞋' => _DetailThumbColors(const Color(0xFF6366F1), const Color(0xFF818CF8), Icons.directions_run),
    '耳机' => _DetailThumbColors(const Color(0xFF0EA5E9), const Color(0xFF38BDF8), Icons.headphones),
    '吹风机' => _DetailThumbColors(const Color(0xFFF43F5E), const Color(0xFFFB7185), Icons.air),
    '背包' => _DetailThumbColors(const Color(0xFFF59E0B), const Color(0xFFFBBF24), Icons.backpack),
    '智能手表' => _DetailThumbColors(const Color(0xFF10B981), const Color(0xFF34D399), Icons.watch),
    _ => _DetailThumbColors(const Color(0xFF6366F1), const Color(0xFF818CF8), Icons.shopping_bag_outlined),
  };

  Widget _buildPriceSection() {
    final priceRange = group.priceRange;
    final showPriceRange =
        priceRange != null && (priceRange.max - priceRange.min).abs() >= 1;

    // Find the cheapest platform
    String cheapestPlatform = '';
    double minPrice = double.infinity;
    for (final p in group.platforms) {
      if (p.price < minPrice) {
        minPrice = p.price;
        cheapestPlatform = _platformLabel(p.platform);
      }
    }

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [AppColors.panel, AppColors.primaryMuted],
        ),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
            color: AppColors.line.withAlpha(100)),
        boxShadow: [
          BoxShadow(
              color: Colors.black.withAlpha(7),
              blurRadius: 12,
              offset: const Offset(0, 3)),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text('¥${group.bestPrice.toStringAsFixed(0)}',
                  style: const TextStyle(
                      fontSize: 32,
                      height: 1,
                      fontWeight: FontWeight.w800,
                      color: AppColors.priceRed,
                      letterSpacing: -0.8)),
              const SizedBox(width: 8),
              const Padding(
                padding: EdgeInsets.only(bottom: 3),
                child: Text('起',
                    style: TextStyle(
                        fontSize: 14,
                        color: AppColors.inkSoft)),
              ),
              if (group.originalPrice > group.bestPrice) ...[
                const SizedBox(width: 12),
                Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: Text(
                      '¥${group.originalPrice.toStringAsFixed(0)}',
                      style: const TextStyle(
                          fontSize: 15,
                          color: AppColors.inkSoft,
                          decoration:
                              TextDecoration.lineThrough)),
                ),
              ],
            ],
          ),
          const SizedBox(height: 8),
          Text(
            '最低来自$cheapestPlatform · ${group.platformCount}个平台有售${showPriceRange ? " · 各平台 ¥${priceRange.min.toStringAsFixed(0)} - ¥${priceRange.max.toStringAsFixed(0)}" : ""}',
            style: const TextStyle(
                fontSize: 12.5,
                height: 1.4,
                color: AppColors.inkSoft),
          ),
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
    // Platform-specific info
    final (shippingLabel, afterSaleLabel) = switch (p.platform) {
      '京东-mock' => ('京仓发货', '上门换新'),
      '天猫-mock' => ('菜鸟配送', '7天无理由'),
      '淘宝-mock' => ('浙江发货', '7天无理由'),
      '拼多多-mock' => ('包邮', '放心退'),
      _ => ('平台发货', '7天无理由'),
    };
    // Compute discount label from price history (preferred) or original price comparison
    String? discountLabel;
    if (p.priceHistory.length >= 3) {
      final avg = p.priceHistory.reduce((a, b) => a + b) / p.priceHistory.length;
      final min = p.priceHistory.reduce((a, b) => a < b ? a : b);
      final diffFromAvg = ((avg - p.price) / avg * 100).round();
      if (diffFromAvg >= 8) {
        discountLabel = '比30天均价低$diffFromAvg%';
      } else if ((p.price - min).abs() < 1) {
        discountLabel = '近30天低价';
      }
    }

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.panel,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
            color: AppColors.line.withAlpha(100)),
        boxShadow: [
          BoxShadow(
              color: Colors.black.withAlpha(6),
              blurRadius: 8,
              offset: const Offset(0, 2)),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header: platform badge + shop name
          Row(
            children: [
              _platformBadge(p.platform),
              const SizedBox(width: 8),
              Expanded(
                child: Text(p.shopName,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        fontSize: 14, fontWeight: FontWeight.w600)),
              ),
              if (discountLabel != null)
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(
                    color: AppColors.priceRed.withAlpha(16),
                    borderRadius: BorderRadius.circular(4),
                    border: Border.all(
                        color: AppColors.priceRed.withAlpha(60)),
                  ),
                  child: Text(discountLabel,
                      style: const TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                          color: AppColors.priceRed)),
                ),
            ],
          ),
          const SizedBox(height: 10),
          // Price row
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text('¥${p.price.toStringAsFixed(0)}',
                  style: const TextStyle(
                      fontSize: 22,
                      height: 1,
                      fontWeight: FontWeight.w700,
                      color: AppColors.priceRed)),
              if (p.originalPrice > p.price) ...[
                const SizedBox(width: 8),
                Padding(
                  padding: const EdgeInsets.only(bottom: 2),
                  child: Text('¥${p.originalPrice.toStringAsFixed(0)}',
                      style: const TextStyle(
                          fontSize: 13,
                          color: AppColors.inkSoft,
                          decoration: TextDecoration.lineThrough)),
                ),
              ],
            ],
          ),
          const SizedBox(height: 8),
          // Info pills: rating | reviews | shipping | after-sale
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              _infoPill(
                  Icons.star, '${p.rating.toStringAsFixed(1)}分', null),
              _infoPill(null, '${_formatCount(p.sales)}条评价', null),
              _infoPill(null, shippingLabel, null),
              _infoPill(null, afterSaleLabel, null),
              if (p.tags.isNotEmpty)
                ...p.tags
                    .where((t) =>
                        t != '包邮' &&
                        t != '正品保障' &&
                        t != '京东物流' &&
                        t != '7天无理由' &&
                        t != '放心退' &&
                        t != '先用后付')
                    .take(2)
                    .map((t) => _infoPill(null, t, AppColors.accent)),
            ],
          ),
          const SizedBox(height: 12),
          // Action buttons — "去看看" primary, "价格提醒" subtle
          Row(
            children: [
              Expanded(
                child: Container(
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                      colors: [
                        AppColors.userBubble,
                        AppColors.userBubbleEnd
                      ],
                    ),
                    borderRadius:
                        BorderRadius.circular(10),
                  ),
                  child: ElevatedButton(
                    onPressed: () {
                      ref
                          .read(behaviorRecorderProvider)
                          .record(
                        BehaviorEventType.platformJump,
                        productId: p.productId,
                        platform: p.platform,
                        price: p.price,
                        category: group.category,
                        brand: p.brand,
                      );
                      _showJumpNotice(context, p);
                    },
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.transparent,
                      foregroundColor: Colors.white,
                      elevation: 0,
                      shadowColor: Colors.transparent,
                      shape: RoundedRectangleBorder(
                          borderRadius:
                              BorderRadius.circular(10)),
                      padding: const EdgeInsets.symmetric(
                          vertical: 10),
                    ),
                    child: const Text('去看看',
                        style: TextStyle(fontSize: 14)),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              TextButton.icon(
                onPressed: () {
                  ref.read(behaviorRecorderProvider).record(
                    BehaviorEventType.priceAlertCreate,
                    productId: p.productId, platform: p.platform,
                    price: p.price, category: group.category, brand: p.brand,
                  );
                  _showPriceAlert(context, ref, p);
                },
                icon: const Icon(Icons.notifications_outlined, size: 16),
                label: const Text('价格提醒'),
                style: TextButton.styleFrom(
                  foregroundColor: AppColors.inkSoft,
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 10),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(8)),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  /// Compact info pill for platform card details.
  Widget _infoPill(IconData? icon, String text, Color? accent) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: accent != null ? accent.withAlpha(12) : AppColors.panelSoft,
        borderRadius: BorderRadius.circular(4),
        border: Border.all(
            color: accent != null ? accent.withAlpha(50) : AppColors.line),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon,
                size: 12,
                color: accent ?? AppColors.inkSoft),
            const SizedBox(width: 3),
          ],
          Text(text,
              style: TextStyle(
                  fontSize: 11,
                  color: accent ?? AppColors.inkSoft)),
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
    final color = switch (platform) {
      '京东-mock' => const Color(0xFFC41A22),
      '拼多多-mock' => const Color(0xFFE53A30),
      '淘宝-mock' => const Color(0xFFFF5000),
      '天猫-mock' => const Color(0xFFFF0033),
      _ => AppColors.inkSoft,
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withAlpha(18),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: color.withAlpha(70)),
      ),
      child: Text(_platformLabel(platform),
          style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: color)),
    );
  }

  String _platformLabel(String platform) {
    return switch (platform) {
      '京东-mock' => '京东',
      '拼多多-mock' => '拼多多',
      '淘宝-mock' => '淘宝',
      '天猫-mock' => '天猫',
      _ => platform,
    };
  }

  String _formatCount(int value) {
    if (value >= 10000) return '${(value / 10000).toStringAsFixed(1)}万';
    return value.toString();
  }
}

class _DetailThumbColors {
  final Color bg, bg2;
  final IconData icon;
  const _DetailThumbColors(this.bg, this.bg2, this.icon);
}
