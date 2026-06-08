import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/network/api_client.dart';
import '../alerts/price_alert_api.dart';
import '../favorites/favorite_api.dart';

final favoriteApiInChatProvider = Provider<FavoriteApi>((ref) {
  return FavoriteApi(baseUrl: ref.watch(apiBaseUrlProvider));
});

final priceAlertApiInChatProvider = Provider<PriceAlertApi>((ref) {
  return PriceAlertApi(baseUrl: ref.watch(apiBaseUrlProvider));
});
