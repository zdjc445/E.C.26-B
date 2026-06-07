class FavoriteItem {
  final int id;
  final String productId;
  final String title;
  final String platform;
  final double price;
  final String? shopName;
  final String? brand;
  final String? imageUrl;
  final String? productUrl;
  final String createdAt;

  const FavoriteItem({
    required this.id,
    required this.productId,
    required this.title,
    required this.platform,
    required this.price,
    this.shopName,
    this.brand,
    this.imageUrl,
    this.productUrl,
    required this.createdAt,
  });

  factory FavoriteItem.fromJson(Map<String, dynamic> json) {
    return FavoriteItem(
      id: (json['id'] as num).toInt(),
      productId: json['productId'] as String,
      title: json['title'] as String? ?? '',
      platform: json['platform'] as String? ?? '',
      price: (json['price'] as num?)?.toDouble() ?? 0,
      shopName: json['shopName'] as String?,
      brand: json['brand'] as String?,
      imageUrl: json['imageUrl'] as String?,
      productUrl: json['productUrl'] as String?,
      createdAt: json['createdAt'] as String? ?? '',
    );
  }
}
