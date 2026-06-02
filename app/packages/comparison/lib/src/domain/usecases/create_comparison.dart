import 'package:app_core/app_core.dart';
import '../entities/comparison_entity.dart';
import '../repositories/comparison_repository.dart';

/// Parameters for creating a comparison.
class CreateComparisonParams {
  final String searchTaskId;
  final List<String> platformProductIds;

  const CreateComparisonParams({
    required this.searchTaskId,
    required this.platformProductIds,
  });
}

/// Use case that creates a cross-platform product comparison.
class CreateComparison {
  final ComparisonRepository _repository;

  const CreateComparison(this._repository);

  Future<Either<Failure, ComparisonEntity>> call(
    CreateComparisonParams params,
  ) async {
    if (params.searchTaskId.isEmpty) {
      return const Left(ValidationFailure({
        'searchTaskId': '搜索任务 ID 不能为空',
      }));
    }
    if (params.platformProductIds.isEmpty) {
      return const Left(ValidationFailure({
        'platformProductIds': '请至少选择一个商品进行对比',
      }));
    }
    return _repository.createComparison(
      searchTaskId: params.searchTaskId,
      platformProductIds: params.platformProductIds,
    );
  }
}
