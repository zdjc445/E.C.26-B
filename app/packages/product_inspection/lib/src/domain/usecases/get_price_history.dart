import 'package:app_core/app_core.dart';
import '../entities/price_history_entity.dart';
import '../repositories/product_inspection_repository.dart';

/// Parameters for fetching price history.
class GetPriceHistoryParams {
  final String platformProductId;
  final int days;

  const GetPriceHistoryParams({
    required this.platformProductId,
    this.days = 90,
  });
}

/// Use case that retrieves a product's price history chart data.
class GetPriceHistory {
  final ProductInspectionRepository _repository;

  const GetPriceHistory(this._repository);

  Future<Either<Failure, PriceHistoryEntity>> call(
    GetPriceHistoryParams params,
  ) async {
    if (params.platformProductId.isEmpty) {
      return const Left(ValidationFailure({
        'platformProductId': '商品 ID 不能为空',
      }));
    }
    return _repository.getPriceHistory(
      platformProductId: params.platformProductId,
      days: params.days,
    );
  }
}
