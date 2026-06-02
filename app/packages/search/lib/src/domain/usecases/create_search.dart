import 'package:app_core/app_core.dart';
import '../entities/filter_criteria.dart';
import '../entities/search_task_entity.dart';
import '../repositories/search_repository.dart';

/// Parameters for CreateSearch use case.
class CreateSearchParams {
  final String? recognitionId;
  final String? query;
  final List<Platform>? platforms;
  final SourceType? sourceType;
  final FilterCriteria? filters;
  final SortMode? sortBy;

  const CreateSearchParams({
    this.recognitionId,
    this.query,
    this.platforms,
    this.sourceType,
    this.filters,
    this.sortBy,
  });

  bool get isEmpty => recognitionId == null && (query?.isEmpty ?? true);
}

/// UseCase: Create a new product search task.
class CreateSearch {
  final SearchRepository _repo;
  const CreateSearch(this._repo);

  Future<Either<Failure, SearchTaskEntity>> call(CreateSearchParams params) {
    if (params.isEmpty) {
      return Future.value(
        const Left(ValidationFailure({'search': '请提供图片识别结果或输入搜索关键词'})),
      );
    }
    return _repo.createSearch(
      recognitionId: params.recognitionId,
      query: params.query,
      platforms: params.platforms,
      sourceType: params.sourceType,
      filters: params.filters,
      sortBy: params.sortBy,
    );
  }
}
