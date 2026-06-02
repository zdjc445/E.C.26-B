/// Cache strategies for offline-first data access.
enum CacheStrategy {
  /// Remote first, cache as fallback.
  remoteFirst,

  /// Cache first, refresh in background.
  cacheFirst,

  /// Remote only — no caching.
  remoteOnly,
}

/// TTL configuration for cached data.
class CachePolicy {
  /// How long cached search results remain valid.
  static const searchResultsTtl = Duration(minutes: 5);

  /// How long cached product details remain valid.
  static const productDetailTtl = Duration(hours: 1);

  /// How long cached price history remains valid.
  static const priceHistoryTtl = Duration(hours: 6);

  /// How long ecommerce status info remains valid.
  static const ecommerceStatusTtl = Duration(minutes: 2);

  const CachePolicy._();
}
