import 'package:app_core/app_core.dart';
import '../../domain/entities/product_entity.dart';
import '../models/product_dto.dart';

/// Maps ProductDto to domain ProductEntity and vice versa.
class ProductMapper {
  static ProductEntity fromDto(ProductDto dto) {
    return ProductEntity(
      productId: dto.productId,
      title: dto.title,
      imageUrl: dto.imageUrl,
      price: dto.price,
      originalPrice: dto.originalPrice,
      platform: Platform.fromApi(dto.platform),
      shopName: dto.shopName,
      rating: dto.rating,
      reviewCount: dto.reviewCount,
      salesCount: dto.salesCount,
      sourceType: SourceType.fromApi(dto.sourceType),
      officialOnly: dto.officialOnly,
      selfOperatedOnly: dto.selfOperatedOnly,
      productUrl: dto.productUrl,
      priceTrend: PriceTrend.fromApi(dto.priceTrend),
      extra: dto.extra,
    );
  }

  static ProductDto toDto(ProductEntity entity) {
    return ProductDto(
      productId: entity.productId,
      title: entity.title,
      imageUrl: entity.imageUrl,
      price: entity.price,
      originalPrice: entity.originalPrice,
      platform: entity.platform.apiValue,
      shopName: entity.shopName,
      rating: entity.rating,
      reviewCount: entity.reviewCount,
      salesCount: entity.salesCount,
      sourceType: entity.sourceType.apiValue,
      officialOnly: entity.officialOnly,
      selfOperatedOnly: entity.selfOperatedOnly,
      productUrl: entity.productUrl,
      priceTrend: entity.priceTrend.name,
      extra: entity.extra,
    );
  }

  static List<ProductEntity> fromDtoList(List<ProductDto> dtos) {
    return dtos.map((d) => fromDto(d)).toList();
  }
}
