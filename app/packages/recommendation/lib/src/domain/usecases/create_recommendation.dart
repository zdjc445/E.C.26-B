import 'package:app_core/app_core.dart';
import '../entities/recommendation_entity.dart';
import '../repositories/recommendation_repository.dart';

/// Parameters for creating a recommendation.
class CreateRecommendationParams {
  final String searchTaskId;
  final String userQuery;
  final List<String> candidateIds;

  const CreateRecommendationParams({
    required this.searchTaskId,
    required this.userQuery,
    required this.candidateIds,
  });
}

/// Use case that produces an AI-driven purchase recommendation.
class CreateRecommendation {
  final RecommendationRepository _repository;

  const CreateRecommendation(this._repository);

  Future<Either<Failure, RecommendationEntity>> call(
    CreateRecommendationParams params,
  ) async {
    if (params.searchTaskId.isEmpty) {
      return const Left(ValidationFailure({
        'searchTaskId': '搜索任务 ID 不能为空',
      }));
    }
    if (params.candidateIds.isEmpty) {
      return const Left(ValidationFailure({
        'candidateIds': '请至少选择一个候选商品',
      }));
    }
    return _repository.createRecommendation(
      searchTaskId: params.searchTaskId,
      userQuery: params.userQuery,
      candidateIds: params.candidateIds,
    );
  }
}
