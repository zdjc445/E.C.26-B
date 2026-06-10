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
      ref.read(behaviorRecorderProvider).record(
            BehaviorEventType.productView,
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
          const SizedBox(height: 14),
          _buildDecisionSummary(),
          if (group.platforms.isNotEmpty) ...[
            const SizedBox(height: 12),
            _buildReviewSummary(),
          ],
          if (group.highlights.isNotEmpty) ...[
            const SizedBox(height: 12),
            _buildHighlights(),
          ],
          const SizedBox(height: 18),
          _sectionHeading('平台比价', '每个平台只保留价格、评价和服务重点'),
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

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(10),
          child: _buildThumbnail(width: 112, height: 112, iconSize: 42),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _buildHeaderText(),
        ),
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
              style: const TextStyle(fontSize: 13, color: AppColors.inkSoft)),
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
      if (platformUrl.startsWith('http://') ||
          platformUrl.startsWith('https://')) {
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
      return Container(
        width: width,
        height: height,
        color: AppColors.panel,
        child: Image.network(
          url,
          width: width,
          height: height,
          fit: BoxFit.contain,
          loadingBuilder: (_, child, progress) {
            if (progress == null) return child;
            return _thumbnailPlaceholder(
                width: width, height: height, iconSize: iconSize);
          },
          errorBuilder: (_, __, ___) => _thumbnailPlaceholder(
              width: width, height: height, iconSize: iconSize),
        ),
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
            child: Icon(colors.icon,
                size: iconSize * 1.2, color: Colors.white.withAlpha(25)),
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
        '运动鞋' => _DetailThumbColors(const Color(0xFF6366F1),
            const Color(0xFF818CF8), Icons.directions_run),
        '耳机' => _DetailThumbColors(
            const Color(0xFF0EA5E9), const Color(0xFF38BDF8), Icons.headphones),
        '吹风机' => _DetailThumbColors(
            const Color(0xFFF43F5E), const Color(0xFFFB7185), Icons.air),
        '背包' => _DetailThumbColors(
            const Color(0xFFF59E0B), const Color(0xFFFBBF24), Icons.backpack),
        '智能手表' => _DetailThumbColors(
            const Color(0xFF10B981), const Color(0xFF34D399), Icons.watch),
        _ => _DetailThumbColors(const Color(0xFF6366F1),
            const Color(0xFF818CF8), Icons.shopping_bag_outlined),
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
        border: Border.all(color: AppColors.line.withAlpha(100)),
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
                    style: TextStyle(fontSize: 14, color: AppColors.inkSoft)),
              ),
              if (group.originalPrice > group.bestPrice) ...[
                const SizedBox(width: 12),
                Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: Text('¥${group.originalPrice.toStringAsFixed(0)}',
                      style: const TextStyle(
                          fontSize: 15,
                          color: AppColors.inkSoft,
                          decoration: TextDecoration.lineThrough)),
                ),
              ],
            ],
          ),
          const SizedBox(height: 8),
          Text(
            '最低来自$cheapestPlatform · ${group.platformCount}个平台有售${showPriceRange ? " · 各平台 ¥${priceRange.min.toStringAsFixed(0)} - ¥${priceRange.max.toStringAsFixed(0)}" : ""}',
            style: const TextStyle(
                fontSize: 12.5, height: 1.4, color: AppColors.inkSoft),
          ),
        ],
      ),
    );
  }

  Widget _buildDecisionSummary() {
    final cheapest = _cheapestOffer();
    if (cheapest == null) {
      return const SizedBox.shrink();
    }
    final topRated = _topRatedOffer();
    final mostReviewed = _mostReviewedOffer();
    final priceRange = group.priceRange;
    final priceGap = priceRange == null ? 0.0 : priceRange.max - priceRange.min;

    final summary = _decisionText(cheapest, topRated, mostReviewed, priceGap);
    final metrics = <_DetailMetricData>[
      _DetailMetricData(
        icon: Icons.savings_outlined,
        label: '最低价',
        value:
            '${_platformLabel(cheapest.platform)} ¥${cheapest.price.toStringAsFixed(0)}',
        note: '优先核对优惠和规格',
        color: AppColors.priceRed,
      ),
    ];

    if (topRated != null) {
      metrics.add(_DetailMetricData(
        icon: Icons.star_border_rounded,
        label: '评分最高',
        value:
            '${_platformLabel(topRated.platform)} ${topRated.rating.toStringAsFixed(1)}',
        note: '口碑优先看这里',
        color: AppColors.warn,
      ));
    }
    if (mostReviewed != null) {
      metrics.add(_DetailMetricData(
        icon: Icons.forum_outlined,
        label: mostReviewed.sales > 0 ? '评价最多' : '评价量',
        value: mostReviewed.sales > 0
            ? '${_platformLabel(mostReviewed.platform)} ${_reviewCountText(mostReviewed.sales)}'
            : '暂无有效评价',
        note: mostReviewed.sales > 0 ? '样本量更充分' : '下单前补看评论区',
        color: AppColors.accent,
      ));
    }
    if (priceGap >= 1) {
      metrics.add(_DetailMetricData(
        icon: Icons.compare_arrows_rounded,
        label: '平台差价',
        value: '¥${priceGap.toStringAsFixed(0)}',
        note: '差价来自样例报价',
        color: AppColors.inkSoft,
      ));
    }

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.panel,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _sectionHeading('购买判断', '先看结论，再看平台细节'),
          const SizedBox(height: 8),
          Text(summary,
              style: const TextStyle(
                  fontSize: 12.5, height: 1.45, color: AppColors.inkSoft)),
          const SizedBox(height: 12),
          _metricGrid(metrics),
        ],
      ),
    );
  }

  Widget _buildReviewSummary() {
    final topRated = _topRatedOffer();
    final mostReviewed = _mostReviewedOffer();
    final totalReviews =
        group.platforms.fold<int>(0, (sum, p) => sum + p.sales);
    final averageRating = group.platforms
            .map((p) => p.rating)
            .fold<double>(0, (sum, rating) => sum + rating) /
        group.platforms.length;

    final reviewNote = totalReviews > 0
        ? '合计 ${_reviewCountText(totalReviews)}，优先看评分和评价量同时靠前的平台。'
        : '评价量较少，先用评分、价格和服务标签辅助判断。';

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.panel,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _sectionHeading('评价概览', '评分和样例口碑集中看'),
          const SizedBox(height: 8),
          Text(reviewNote,
              style: const TextStyle(
                  fontSize: 12.5, height: 1.45, color: AppColors.inkSoft)),
          const SizedBox(height: 12),
          _metricGrid([
            _DetailMetricData(
              icon: Icons.star_half_rounded,
              label: '平均评分',
              value: averageRating.toStringAsFixed(1),
              note: topRated == null
                  ? '暂无最高评分'
                  : '最高 ${_platformLabel(topRated.platform)}',
              color: AppColors.warn,
            ),
            _DetailMetricData(
              icon: Icons.forum_outlined,
              label: '评价量',
              value: _reviewCountText(totalReviews),
              note: totalReviews <= 0
                  ? '暂无有效评价量'
                  : mostReviewed == null
                      ? '暂无平台数据'
                      : '${_platformLabel(mostReviewed.platform)} 最多',
              color: AppColors.accent,
            ),
          ]),
        ],
      ),
    );
  }

  String _decisionText(
      PlatformOfferSummary cheapest,
      PlatformOfferSummary? topRated,
      PlatformOfferSummary? mostReviewed,
      double priceGap) {
    final cheapestName = _platformLabel(cheapest.platform);
    final topRatedName =
        topRated == null ? null : _platformLabel(topRated.platform);
    final reviewedName =
        mostReviewed == null ? null : _platformLabel(mostReviewed.platform);
    if (priceGap >= 1 && topRatedName != null && cheapestName == topRatedName) {
      return '$cheapestName 同时占最低价和高评分，优先看这个平台。';
    }
    if (priceGap >= 1) {
      return '先看 $cheapestName 的低价；如果更重视口碑，再对比 ${topRatedName ?? cheapestName}。';
    }
    if (reviewedName != null) {
      return '各平台价格接近，优先看 $reviewedName 的评价量和售后服务。';
    }
    return '各平台价格接近，优先比较评分和服务保障。';
  }

  Widget _metricGrid(List<_DetailMetricData> metrics) {
    return LayoutBuilder(builder: (context, constraints) {
      final itemWidth = (constraints.maxWidth - 8) / 2;
      return Wrap(
        spacing: 8,
        runSpacing: 8,
        children: metrics
            .map((metric) => SizedBox(
                  width: itemWidth,
                  child: _metricTile(metric),
                ))
            .toList(),
      );
    });
  }

  Widget _metricTile(_DetailMetricData metric) {
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: metric.color.withAlpha(10),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: metric.color.withAlpha(42)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(metric.icon, size: 15, color: metric.color),
              const SizedBox(width: 5),
              Expanded(
                child: Text(metric.label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        fontSize: 11.5,
                        fontWeight: FontWeight.w600,
                        color: AppColors.inkSoft)),
              ),
            ],
          ),
          const SizedBox(height: 7),
          Text(metric.value,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w700,
                  color: AppColors.inkBody)),
          const SizedBox(height: 3),
          Text(metric.note,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 10.5, color: AppColors.inkSoft)),
        ],
      ),
    );
  }

  Widget _sectionHeading(String title, String subtitle) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(title,
            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
        const SizedBox(height: 3),
        Text(subtitle,
            style: const TextStyle(fontSize: 12, color: AppColors.inkSoft)),
      ],
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
      final avg =
          p.priceHistory.reduce((a, b) => a + b) / p.priceHistory.length;
      final min = p.priceHistory.reduce((a, b) => a < b ? a : b);
      final diffFromAvg = ((avg - p.price) / avg * 100).round();
      if (diffFromAvg >= 8) {
        discountLabel = '比30天均价低$diffFromAvg%';
      } else if ((p.price - min).abs() < 1) {
        discountLabel = '近30天低价';
      }
    }
    final roleBadges = _platformRoleBadges(p);
    final sellingPoints = _sellingPoints(p);
    final trendText = _priceTrendText(p);
    final priceNote = _priceNote(p, discountLabel);
    final reviewSnippets = _reviewSnippets(p, shippingLabel, afterSaleLabel);

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.panel,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.line.withAlpha(100)),
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
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Wrap(
                      spacing: 6,
                      runSpacing: 6,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: [
                        _platformBadge(p.platform),
                        ...roleBadges,
                      ],
                    ),
                    const SizedBox(height: 6),
                    Text(p.shopName,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                            fontSize: 14, fontWeight: FontWeight.w700)),
                    if (p.title.isNotEmpty &&
                        p.title != group.displayTitle) ...[
                      const SizedBox(height: 4),
                      Text(p.title,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                              fontSize: 12.5,
                              height: 1.3,
                              color: AppColors.inkSoft)),
                    ],
                  ],
                ),
              ),
              const SizedBox(width: 10),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text('¥${p.price.toStringAsFixed(0)}',
                      style: const TextStyle(
                          fontSize: 23,
                          height: 1,
                          fontWeight: FontWeight.w800,
                          color: AppColors.priceRed)),
                  if (p.originalPrice > p.price) ...[
                    const SizedBox(height: 3),
                    Text('¥${p.originalPrice.toStringAsFixed(0)}',
                        style: const TextStyle(
                            fontSize: 12,
                            color: AppColors.inkSoft,
                            decoration: TextDecoration.lineThrough)),
                  ],
                ],
              ),
            ],
          ),
          const SizedBox(height: 12),
          _compactMetricRow([
            _DetailMetricData(
              icon: Icons.payments_outlined,
              label: '到手价',
              value: '¥${p.price.toStringAsFixed(0)}',
              note: priceNote,
              color: AppColors.priceRed,
            ),
            _DetailMetricData(
              icon: Icons.star_border_rounded,
              label: '口碑',
              value: p.rating.toStringAsFixed(1),
              note: '${_reviewCountText(p.sales)}评价',
              color: AppColors.warn,
            ),
            _DetailMetricData(
              icon: Icons.local_shipping_outlined,
              label: '服务',
              value: shippingLabel,
              note: afterSaleLabel,
              color: AppColors.good,
            ),
          ]),
          if (sellingPoints.isNotEmpty) ...[
            const SizedBox(height: 12),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Padding(
                  padding: EdgeInsets.only(top: 3),
                  child: Text('推荐点',
                      style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                          color: AppColors.inkBody)),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: sellingPoints
                        .take(3)
                        .map((t) => _infoPill(null, t, AppColors.good))
                        .toList(),
                  ),
                ),
              ],
            ),
          ],
          const SizedBox(height: 12),
          _buildReviewBlock(reviewSnippets),
          if (trendText != null) ...[
            const SizedBox(height: 10),
            _detailLine(Icons.show_chart_rounded, trendText),
          ],
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: Container(
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                      colors: [AppColors.userBubble, AppColors.userBubbleEnd],
                    ),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: ElevatedButton(
                    onPressed: () {
                      ref.read(behaviorRecorderProvider).record(
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
                          borderRadius: BorderRadius.circular(10)),
                      padding: const EdgeInsets.symmetric(vertical: 10),
                    ),
                    child: const Text('去看看', style: TextStyle(fontSize: 14)),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              TextButton.icon(
                onPressed: () {
                  ref.read(behaviorRecorderProvider).record(
                        BehaviorEventType.priceAlertCreate,
                        productId: p.productId,
                        platform: p.platform,
                        price: p.price,
                        category: group.category,
                        brand: p.brand,
                      );
                  _showPriceAlert(context, ref, p);
                },
                icon: const Icon(Icons.notifications_outlined, size: 16),
                label: const Text('价格提醒'),
                style: TextButton.styleFrom(
                  foregroundColor: AppColors.inkSoft,
                  padding:
                      const EdgeInsets.symmetric(horizontal: 7, vertical: 10),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(8)),
                ),
              ),
              const SizedBox(width: 4),
              IconButton(
                tooltip: '收藏',
                onPressed: () => _addOfferToFavorites(context, ref, p),
                icon: const Icon(Icons.favorite_border, size: 20),
                color: AppColors.inkSoft,
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(minWidth: 38, minHeight: 38),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _compactMetricRow(List<_DetailMetricData> metrics) {
    return LayoutBuilder(builder: (context, constraints) {
      final itemWidth = (constraints.maxWidth - 16) / 3;
      return Row(
        children: metrics
            .map((metric) => Padding(
                  padding:
                      EdgeInsets.only(right: metric == metrics.last ? 0 : 8),
                  child: SizedBox(
                    width: itemWidth,
                    child: _compactMetricTile(metric),
                  ),
                ))
            .toList(),
      );
    });
  }

  Widget _compactMetricTile(_DetailMetricData metric) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 9),
      decoration: BoxDecoration(
        color: metric.color.withAlpha(9),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: metric.color.withAlpha(34)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(metric.icon, size: 14, color: metric.color),
              const SizedBox(width: 4),
              Expanded(
                child: Text(metric.label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        fontSize: 10.5, color: AppColors.inkSoft)),
              ),
            ],
          ),
          const SizedBox(height: 5),
          Text(metric.value,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                  color: AppColors.inkBody)),
          const SizedBox(height: 2),
          Text(metric.note,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 10, color: AppColors.inkSoft)),
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
            Icon(icon, size: 12, color: accent ?? AppColors.inkSoft),
            const SizedBox(width: 3),
          ],
          Text(text,
              style:
                  TextStyle(fontSize: 11, color: accent ?? AppColors.inkSoft)),
        ],
      ),
    );
  }

  List<Widget> _platformRoleBadges(PlatformOfferSummary p) {
    final badges = <Widget>[];
    if (_sameOffer(_cheapestOffer(), p)) {
      badges.add(_roleBadge('最低价', AppColors.priceRed));
    }
    if (_sameOffer(_topRatedOffer(), p)) {
      badges.add(_roleBadge('评分最高', AppColors.warn));
    }
    if (_sameOffer(_mostReviewedOffer(), p)) {
      badges.add(_roleBadge('评价最多', AppColors.accent));
    }
    return badges;
  }

  Widget _roleBadge(String text, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: color.withAlpha(14),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withAlpha(55)),
      ),
      child: Text(text,
          style: TextStyle(
              fontSize: 11, fontWeight: FontWeight.w700, color: color)),
    );
  }

  List<String> _sellingPoints(PlatformOfferSummary p) {
    final points = <String>[];
    final seen = <String>{};
    void add(String value) {
      final label = _preferenceLabel(value.trim());
      if (label.isNotEmpty && seen.add(label)) {
        points.add(label);
      }
    }

    for (final reason in p.reasons) {
      add(reason);
    }
    for (final matched in p.matchedPreferences) {
      add(matched);
    }
    if (_sameOffer(_cheapestOffer(), p)) {
      add('当前最低价');
    }
    if (p.rating >= 4.8) {
      add('评分较高');
    }
    if (p.sales >= 10000) {
      add('评价量充足');
    }
    return points.take(4).toList();
  }

  String _priceNote(PlatformOfferSummary p, String? discountLabel) {
    if (discountLabel != null) {
      return discountLabel;
    }
    final cheapest = _cheapestOffer();
    if (cheapest == null) {
      return '样例报价';
    }
    final delta = p.price - cheapest.price;
    if (delta.abs() < 1) {
      return '本组最低价';
    }
    return '比最低价高 ¥${delta.toStringAsFixed(0)}';
  }

  String _reviewCountText(int value) {
    if (value <= 0) {
      return '暂无';
    }
    return '${_formatCount(value)}条';
  }

  Widget _buildReviewBlock(List<_ReviewSnippet> snippets) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: AppColors.panelSoft,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: const [
              Icon(Icons.rate_review_outlined,
                  size: 14, color: AppColors.inkSoft),
              SizedBox(width: 5),
              Text('精选评论',
                  style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                      color: AppColors.inkBody)),
              SizedBox(width: 6),
              Text('样例口碑摘要',
                  style: TextStyle(fontSize: 11, color: AppColors.inkSoft)),
            ],
          ),
          const SizedBox(height: 8),
          ...snippets.map(_reviewRow),
        ],
      ),
    );
  }

  Widget _reviewRow(_ReviewSnippet snippet) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 7),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 46,
            padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 3),
            decoration: BoxDecoration(
              color: AppColors.panel,
              borderRadius: BorderRadius.circular(999),
              border: Border.all(color: AppColors.line),
            ),
            child: Text(snippet.label,
                textAlign: TextAlign.center,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style:
                    const TextStyle(fontSize: 10.5, color: AppColors.inkSoft)),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(snippet.text,
                style: const TextStyle(
                    fontSize: 12, height: 1.35, color: AppColors.inkBody)),
          ),
        ],
      ),
    );
  }

  List<_ReviewSnippet> _reviewSnippets(
      PlatformOfferSummary p, String shippingLabel, String afterSaleLabel) {
    final delta = p.price - (_cheapestOffer()?.price ?? p.price);
    final priceText = delta.abs() < 1
        ? '价格是本组最低，适合先加入对比清单。'
        : '价格比最低价高 ¥${delta.toStringAsFixed(0)}，重点看店铺和服务是否值得。';
    final ratingText = p.rating >= 4.8
        ? '评分 ${p.rating.toStringAsFixed(1)}，口碑表现靠前。'
        : p.rating > 0
            ? '评分 ${p.rating.toStringAsFixed(1)}，下单前建议再看实拍和追评。'
            : '暂无评分，建议下单前补看平台评价区。';
    final serviceText = p.tags.any((t) => t.contains('自营') || t.contains('官方'))
        ? '$shippingLabel，$afterSaleLabel，店铺标签偏官方渠道。'
        : '$shippingLabel，$afterSaleLabel，下单前重点核对退换和发货说明。';

    return [
      _ReviewSnippet('价格', priceText),
      _ReviewSnippet('口碑', ratingText),
      _ReviewSnippet('服务', serviceText),
    ];
  }

  String _preferenceLabel(String value) {
    return switch (value) {
      'low_price' => '低价优先',
      'lowest_price' => '低价优先',
      'budget_match' => '预算匹配',
      'official_store' => '官方店铺',
      'after_sale' => '售后保障',
      'fast_delivery' => '配送更快',
      'high_rating' => '高评分',
      'high_sales' => '高销量',
      'top_rated' => '评分领先',
      'brand_match' => '品牌匹配',
      'noise_cancel' => '降噪优先',
      'high_power' => '大功率',
      'portable' => '便携',
      'large_capacity' => '大容量',
      'business' => '商务款',
      'long_battery' => '长续航',
      'sports' => '运动款',
      _ => value,
    };
  }

  String? _priceTrendText(PlatformOfferSummary p) {
    if (p.priceHistory.length < 2) {
      return null;
    }
    final first = p.priceHistory.first;
    final last = p.priceHistory.last;
    final min = p.priceHistory.reduce((a, b) => a < b ? a : b);
    final max = p.priceHistory.reduce((a, b) => a > b ? a : b);
    final trend = last < first - 1
        ? '近期走低'
        : last > first + 1
            ? '近期走高'
            : '近期平稳';
    return '价格走势：$trend · 近30天 ¥${min.toStringAsFixed(0)} - ¥${max.toStringAsFixed(0)}';
  }

  Widget _detailLine(IconData icon, String text) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 15, color: AppColors.inkSoft),
        const SizedBox(width: 6),
        Expanded(
          child: Text(text,
              style: const TextStyle(
                  fontSize: 12, height: 1.35, color: AppColors.inkSoft)),
        ),
      ],
    );
  }

  PlatformOfferSummary? _cheapestOffer() {
    if (group.platforms.isEmpty) {
      return null;
    }
    var result = group.platforms.first;
    for (final p in group.platforms.skip(1)) {
      if (p.price < result.price) {
        result = p;
      }
    }
    return result;
  }

  PlatformOfferSummary? _topRatedOffer() {
    if (group.platforms.isEmpty) {
      return null;
    }
    var result = group.platforms.first;
    for (final p in group.platforms.skip(1)) {
      if (p.rating > result.rating) {
        result = p;
      }
    }
    return result;
  }

  PlatformOfferSummary? _mostReviewedOffer() {
    if (group.platforms.isEmpty) {
      return null;
    }
    var result = group.platforms.first;
    for (final p in group.platforms.skip(1)) {
      if (p.sales > result.sales) {
        result = p;
      }
    }
    return result;
  }

  bool _sameOffer(PlatformOfferSummary? a, PlatformOfferSummary b) {
    return a != null && a.productId == b.productId && a.platform == b.platform;
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
                '当前演示使用样例商品数据，不会打开真实电商页面。正式接入后将跳转到对应平台商品详情页。',
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

  Future<void> _addOfferToFavorites(
      BuildContext context, WidgetRef ref, PlatformOfferSummary p) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      final token = ref.read(authControllerProvider).session?.token;
      await ref.read(favoriteApiInChatProvider).add({
        'productId': p.productId,
        'title': p.title.isNotEmpty ? p.title : group.displayTitle,
        'platform': p.platform,
        'price': p.price,
        'shopName': p.shopName,
        'brand': p.brand.isNotEmpty ? p.brand : group.brand,
        'imageUrl': p.imageUrl.isNotEmpty ? p.imageUrl : group.thumbnailUrl,
        'productUrl': p.productUrl,
      }, token: token);
      ref.read(behaviorRecorderProvider).record(
            BehaviorEventType.favorite,
            productId: p.productId,
            platform: p.platform,
            price: p.price,
            category: group.category,
            brand: p.brand.isNotEmpty ? p.brand : group.brand,
            tags: p.tags,
          );
      if (context.mounted) {
        messenger.showSnackBar(
          const SnackBar(content: Text('已收藏，可在「我的收藏」查看')),
        );
      }
    } catch (e) {
      if (context.mounted) {
        messenger.showSnackBar(SnackBar(content: Text('收藏失败：$e')));
      }
    }
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
          style: TextStyle(
              fontSize: 11, fontWeight: FontWeight.w600, color: color)),
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

class _DetailMetricData {
  final IconData icon;
  final String label;
  final String value;
  final String note;
  final Color color;

  const _DetailMetricData({
    required this.icon,
    required this.label,
    required this.value,
    required this.note,
    required this.color,
  });
}

class _ReviewSnippet {
  final String label;
  final String text;

  const _ReviewSnippet(this.label, this.text);
}
