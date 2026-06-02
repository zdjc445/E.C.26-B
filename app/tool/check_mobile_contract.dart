import 'dart:io';

import 'package:app_comparison/src/data/mappers/comparison_mapper.dart';
import 'package:app_comparison/src/data/models/comparison_dto.dart';
import 'package:app_favorites/src/data/mappers/favorite_mapper.dart';
import 'package:app_favorites/src/data/models/favorite_dto.dart';
import 'package:app_price_alerts/src/data/mappers/price_alert_mapper.dart';
import 'package:app_price_alerts/src/data/models/price_alert_dto.dart';
import 'package:app_product_inspection/src/data/mappers/price_mapper.dart';
import 'package:app_product_inspection/src/data/models/price_dto.dart';
import 'package:app_product_inspection/src/data/models/review_dto.dart';
import 'package:app_recommendation/src/data/mappers/recommendation_mapper.dart';
import 'package:app_recommendation/src/data/models/recommendation_dto.dart';

void main() {
  _checkFavoriteContract();
  _checkPriceAlertContract();
  _checkProductInspectionContract();
  _checkComparisonContract();
  _checkRecommendationContract();
  stdout.writeln('mobile purchase contract ok');
}

void _checkFavoriteContract() {
  final dto = FavoriteDto.fromJson({
    'favoriteId': 91,
    'platformProductId': 5010,
    'platform': 'jd',
    'title': 'Auralis ANC-20',
    'price': {'amount': '329.00', 'currency': 'CNY'},
    'note': '来自移动端搜索',
    'createdAt': '2026-06-01T12:00:00Z',
  });
  final entity = FavoriteMapper.fromDto(dto);
  _check(entity.favoriteId == '91', 'Favorite.id');
  _check(entity.platformProductId == '5010', 'Favorite.platformProductId');
  _check(entity.price.amountAsDouble == 329, 'Favorite.price');
}

void _checkPriceAlertContract() {
  final dto = PriceAlertDto.fromJson({
    'priceAlertId': 37,
    'platformProductId': 5010,
    'title': 'Auralis ANC-20',
    'currentPrice': {'amount': '329.00', 'currency': 'CNY'},
    'targetPrice': {'amount': '299.00', 'currency': 'CNY'},
    'enabled': true,
    'createdAt': '2026-06-01T12:00:00Z',
    'updatedAt': '2026-06-01T12:00:00Z',
  });
  final entity = PriceAlertMapper.fromDto(dto);
  _check(entity.priceAlertId == '37', 'PriceAlert.id');
  _check(entity.platformProductId == '5010', 'PriceAlert.platformProductId');
  _check(entity.currentPrice.amountAsDouble == 329, 'PriceAlert.currentPrice');
  _check(entity.targetPrice.amountAsDouble == 299, 'PriceAlert.targetPrice');
}

void _checkProductInspectionContract() {
  final priceDto = PriceDto.fromJson({
    'platformProductId': 5010,
    'days': 90,
    'currentPrice': {'amount': '329.00', 'currency': 'CNY'},
    'lowestPrice': {'amount': '299.00', 'currency': 'CNY'},
    'highestPrice': {'amount': '399.00', 'currency': 'CNY'},
    'trend': 'normal',
    'points': [
      {
        'recordedAt': '2026-05-01T12:00:00Z',
        'price': {'amount': '319.00', 'currency': 'CNY'},
      },
      {
        'recordedAt': '2026-06-01T12:00:00Z',
        'price': {'amount': '329.00', 'currency': 'CNY'},
      },
    ],
  });
  final history = PriceMapper.priceHistoryFromDto(priceDto);
  _check(history.platformProductId == '5010', 'PriceHistory.platformProductId');
  _check(history.currentPrice == 329, 'PriceHistory.currentPrice');
  _check(history.lowestPrice == 299, 'PriceHistory.lowestPrice');
  _check(history.points.first.price == 319, 'PriceHistory.point.price');

  final reviewDto = ReviewDto.fromJson({
    'platformProductId': 5010,
    'rating': 4.7,
    'reviewCount': 1860,
    'positiveTags': ['降噪强', '佩戴舒服'],
    'riskTags': ['低频偏重'],
    'riskScore': 0.22,
    'summary': '整体评价稳定。',
  });
  final review = PriceMapper.reviewSummaryFromDto(reviewDto);
  _check(review.platformProductId == '5010', 'Review.platformProductId');
  _check(review.reviewCount == 1860, 'Review.reviewCount');
  _check(review.riskTags.single == '低频偏重', 'Review.riskTags');
}

void _checkComparisonContract() {
  final dto = ComparisonDto.fromJson({
    'comparisonId': 18,
    'searchTaskId': 3016,
    'lowestPlatformProductId': 5010,
    'lowestPrice': {'amount': '329.00', 'currency': 'CNY'},
    'platformStats': [
      {
        'platform': 'jd',
        'lowestPrice': {'amount': '329.00', 'currency': 'CNY'},
        'averagePrice': {'amount': '349.00', 'currency': 'CNY'},
        'productCount': 2,
      },
    ],
    'items': [
      {
        'platformProductId': 5010,
        'platform': 'jd',
        'title': 'Auralis ANC-20',
        'price': {'amount': '329.00', 'currency': 'CNY'},
        'imageUrl': 'https://example.test/headphones.png',
        'shopName': '京东自营',
        'url': 'https://example.test/p/5010',
        'tags': ['自营', '满减'],
        'salesVolume': 16800,
        'rating': 4.8,
        'isSelfOperated': true,
      },
    ],
    'createdAt': '2026-06-01T12:00:00Z',
  });
  final entity = ComparisonMapper.entityFromDto(dto);
  _check(entity.comparisonId == '18', 'Comparison.id');
  _check(entity.searchTaskId == '3016', 'Comparison.searchTaskId');
  _check(entity.lowestPlatformProductId == '5010', 'Comparison.lowestId');
  _check(entity.lowestPrice.amountAsDouble == 329, 'Comparison.lowestPrice');
  _check(entity.platformStats.single.productCount == 2, 'Comparison.stats');
  _check(entity.items.single.store == '京东自营', 'Comparison.item.store');
  _check(entity.items.single.features.first == '自营', 'Comparison.item.tags');

  final request = const CreateComparisonRequest(
    searchTaskId: '3016',
    platformProductIds: ['5010', '5011'],
  ).toJson();
  _check(request['searchTaskId'] is int, 'ComparisonRequest.searchTaskId');
  _check(
    (request['platformProductIds'] as List).every((id) => id is int),
    'ComparisonRequest.platformProductIds',
  );
}

void _checkRecommendationContract() {
  final dto = RecommendationDto.fromJson({
    'recommendationId': 77,
    'searchTaskId': 3016,
    'suggestion': 'buy',
    'recommendedPlatformProduct': {
      'platformProductId': 5010,
      'platform': 'jd',
      'title': 'Auralis ANC-20',
      'price': {'amount': '329.00', 'currency': 'CNY'},
      'matchScore': 0.93,
    },
    'decisionScore': 91,
    'decisionSignals': [
      {
        'key': 'price',
        'label': '价格',
        'score': 88,
        'explanation': '当前价格接近低位。',
      },
    ],
    'decisionTrace': [
      {
        'key': 'collect',
        'label': '采集候选',
        'status': 'done',
        'confidence': 92,
        'observation': '已比较主流平台。',
      },
    ],
    'candidateAnalyses': [
      {
        'platformProductId': 5010,
        'platform': 'jd',
        'title': 'Auralis ANC-20',
        'price': {'amount': '329.00', 'currency': 'CNY'},
        'rank': 1,
        'decisionScore': 91,
        'verdict': 'buy',
        'strengths': ['价格稳定'],
        'weaknesses': ['颜色可选少'],
      },
    ],
    'reasons': ['价格和评价平衡'],
    'risks': ['可再观察大促'],
    'evidence': [
      {
        'type': 'price_history',
        'platformProductId': 5010,
        'content': '90 天内接近低点。',
      },
    ],
    'createdAt': '2026-06-01T12:00:00Z',
  });
  final entity = RecommendationMapper.entityFromDto(dto);
  _check(entity.recommendationId == '77', 'Recommendation.id');
  _check(entity.searchTaskId == '3016', 'Recommendation.searchTaskId');
  _check(
    entity.recommendedPlatformProduct.platformProductId == '5010',
    'Recommendation.productId',
  );
  _check(entity.decisionScore == 91, 'Recommendation.decisionScore');
  _check(entity.evidence.single.platformProductId == '5010', 'Evidence.id');

  final request = const CreateRecommendationRequest(
    searchTaskId: '3016',
    userQuery: '通勤降噪耳机',
    candidateIds: ['5010', '5011'],
  ).toJson();
  _check(request['searchTaskId'] is int, 'RecommendationRequest.searchTaskId');
  _check(
    (request['candidateIds'] as List).every((id) => id is int),
    'RecommendationRequest.candidateIds',
  );
}

void _check(bool condition, String label) {
  if (!condition) {
    throw StateError(label);
  }
}
