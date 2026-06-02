import 'package:app_core/app_core.dart';
import '../entities/comparison_entity.dart';

/// Data-access contract for product comparisons.
/// Implemented in the data layer via remote Dio calls.
abstract class ComparisonRepository {
  /// Create a new comparison across the given platform products.
  Future<Either<Failure, ComparisonEntity>> createComparison({
    required String searchTaskId,
    required List<String> platformProductIds,
  });
}
