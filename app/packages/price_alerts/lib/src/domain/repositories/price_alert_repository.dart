import 'package:app_core/app_core.dart';
import '../entities/price_alert_entity.dart';

/// Contract for price alert data access.
/// Implemented in the data layer via remote Dio calls.
abstract class PriceAlertRepository {
  /// Create a new price alert for a product.
  Future<Either<Failure, PriceAlertEntity>> createAlert({
    required String platformProductId,
    required Money targetPrice,
    bool enabled = true,
  });

  /// Update an existing price alert.
  Future<Either<Failure, PriceAlertEntity>> updateAlert(
    String priceAlertId, {
    Money? targetPrice,
    bool? enabled,
  });

  /// Delete a price alert by its [priceAlertId].
  Future<Either<Failure, void>> deleteAlert(String priceAlertId);

  /// List price alerts with pagination.
  Future<Either<Failure, ({
    List<PriceAlertEntity> items,
    int page,
    int pageSize,
    int total,
  })>> listAlerts({int page = 1, int pageSize = 20});
}
