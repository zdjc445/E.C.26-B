import 'package:app_core/app_core.dart';
import '../entities/review_summary_entity.dart';
import '../repositories/product_inspection_repository.dart';

/// Parameters for fetching a review summary.
class GetReviewSummaryParams {
  final String platformProductId;

  const GetReviewSummaryParams({required this.platformProductId});
}

/// Use case that retrieves a product's review summary and risk analysis.
class GetReviewSummary {
  final ProductInspectionRepository _repository;

  const GetReviewSummary(this._repository);

  Future<Either<Failure, ReviewSummaryEntity>> call(
    GetReviewSummaryParams params,
  ) async {
    if (params.platformProductId.isEmpty) {
      return const Left(ValidationFailure({
        'platformProductId': '商品 ID 不能为空',
      }));
    }
    return _repository.getReviewSummary(
      platformProductId: params.platformProductId,
    );
  }
}
