import 'package:app_core/app_core.dart';
import '../entities/recommendation_entity.dart';

/// Data-access contract for AI recommendations.
/// Implemented in the data layer via remote Dio calls.
abstract class RecommendationRepository {
  /// Request an AI recommendation based on the search context and candidate products.
  Future<Either<Failure, RecommendationEntity>> createRecommendation({
    required String searchTaskId,
    required String userQuery,
    required List<String> candidateIds,
  });
}
