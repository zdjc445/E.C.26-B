import 'dart:io';

import 'package:app_core/app_core_domain.dart';
import 'package:app_search/src/data/models/search_task_dto.dart';
import 'package:app_search/src/domain/entities/search_task_entity.dart';

void main() {
  final backendSearchTask = <String, dynamic>{
    'searchTaskId': 3016,
    'status': 'completed',
    'query': '500 元以内的黑色降噪耳机，要长续航，只看官方',
    'sourceType': 'mock',
    'filters': {
      'maxPrice': {'amount': '500.00', 'currency': 'CNY'},
      'officialOnly': true,
      'minRating': 4.8,
    },
    'recognition': {
      'recognitionId': 2008,
    },
    'items': [
      {
        'platformProductId': 5010,
        'productId': 101,
        'platform': 'jd',
        'title': 'Auralis ANC-20 京东自营降噪耳机 黑色',
        'imageUrl': 'https://example.com/headphones.jpg',
        'price': {'amount': '329.00', 'currency': 'CNY'},
        'originalPrice': {'amount': '399.00', 'currency': 'CNY'},
        'url': 'https://example.com/p/5010',
        'shopName': '京东自营',
        'tags': ['官方', '自营'],
        'salesVolume': 16800,
        'rating': 4.8,
        'isOfficial': true,
        'isSelfOperated': true,
        'matchScore': 0.81,
        'matchReasons': ['黑色', '长续航'],
        'sourceType': 'mock',
      },
    ],
    'platformStats': [
      {
        'platform': 'jd',
        'lowestPrice': {'amount': '329.00', 'currency': 'CNY'},
        'averagePrice': {'amount': '329.00', 'currency': 'CNY'},
        'productCount': 1,
      },
    ],
    'createdAt': '2026-06-01T20:56:35+08:00',
  };

  final dto = SearchTaskDto.fromJson(backendSearchTask);
  _check(dto.taskId == '3016', 'SearchTaskDto.taskId');
  _check(dto.recognitionId == '2008', 'SearchTaskDto.recognitionId');
  _check(dto.results.length == 1, 'SearchTaskDto.results');
  _check(dto.totalResults == 1, 'SearchTaskDto.totalResults');
  _check(dto.platforms.single == 'jd', 'SearchTaskDto.platforms');

  final entity = SearchTaskEntity.fromJson(backendSearchTask);
  _check(entity.taskId == '3016', 'SearchTaskEntity.taskId');
  _check(entity.recognitionId == '2008', 'SearchTaskEntity.recognitionId');
  _check(entity.sourceType == SourceType.mock, 'SearchTaskEntity.sourceType');
  _check(entity.filters?.priceMax == 500, 'FilterCriteria.maxPrice');
  _check(entity.filters?.officialOnly == true, 'FilterCriteria.officialOnly');
  _check(entity.results.single.productId == '5010', 'ProductEntity.productId');
  _check(entity.results.single.price == 329, 'ProductEntity.price');
  _check(
    entity.results.single.originalPrice == 399,
    'ProductEntity.originalPrice',
  );
  _check(entity.results.single.salesCount == 16800, 'ProductEntity.salesCount');
  _check(entity.results.single.officialOnly, 'ProductEntity.officialOnly');
  _check(entity.platformStats.single.resultCount == 1, 'PlatformStats.count');
  _check(entity.platformStats.single.minPrice == 329, 'PlatformStats.minPrice');
  _check(entity.platformStats.single.avgPrice == 329, 'PlatformStats.avgPrice');

  stdout.writeln('search contract ok');
}

void _check(bool condition, String label) {
  if (!condition) {
    throw StateError('Contract check failed: $label');
  }
}
