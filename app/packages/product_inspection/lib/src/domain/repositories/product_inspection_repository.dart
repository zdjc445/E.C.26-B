import 'package:app_core/app_core.dart';
import '../entities/price_history_entity.dart';
import '../entities/review_summary_entity.dart';

/// Data-access contract for product inspection features.
/// Implemented in the data layer via remote Dio calls.
abstract class ProductInspectionRepository {
  /// Fetch price history for a platform product.
  Future<Either<Failure, PriceHistoryEntity>> getPriceHistory({
    required String platformProductId,
    int days = 90,
  });

  /// Fetch review summary for a platform product.
  Future<Either<Failure, ReviewSummaryEntity>> getReviewSummary({
    required String platformProductId,
  });
}
