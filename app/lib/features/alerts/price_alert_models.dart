class PriceAlertItem {
  final int id;
  final String productId;
  final String title;
  final String platform;
  final double targetPrice;
  final bool triggered;
  final double? lastObservedPrice;
  final String? note;
  final String createdAt;

  const PriceAlertItem({
    required this.id,
    required this.productId,
    required this.title,
    required this.platform,
    required this.targetPrice,
    required this.triggered,
    this.lastObservedPrice,
    this.note,
    required this.createdAt,
  });

  factory PriceAlertItem.fromJson(Map<String, dynamic> json) {
    return PriceAlertItem(
      id: (json['id'] as num).toInt(),
      productId: json['productId'] as String,
      title: json['title'] as String? ?? '',
      platform: json['platform'] as String? ?? '',
      targetPrice: (json['targetPrice'] as num).toDouble(),
      triggered: json['triggered'] as bool? ?? false,
      lastObservedPrice: (json['lastObservedPrice'] as num?)?.toDouble(),
      note: json['note'] as String?,
      createdAt: json['createdAt'] as String? ?? '',
    );
  }
}

class PriceAlertCheckResult {
  final int checked;
  final int triggered;
  final List<Map<String, dynamic>> results;

  const PriceAlertCheckResult({
    required this.checked,
    required this.triggered,
    required this.results,
  });

  factory PriceAlertCheckResult.fromJson(Map<String, dynamic> json) {
    return PriceAlertCheckResult(
      checked: (json['checked'] as num).toInt(),
      triggered: (json['triggered'] as num).toInt(),
      results: (json['results'] as List?)
              ?.map((e) => (e as Map).cast<String, dynamic>())
              .toList() ??
          [],
    );
  }
}
