import 'package:app_core/app_core.dart';
import '../entities/search_task_entity.dart';
import '../repositories/search_repository.dart';

/// Parameters for RefineSearch use case.
class RefineSearchParams {
  final String taskId;
  final String text;
  final SortMode? sortBy;

  const RefineSearchParams({
    required this.taskId,
    required this.text,
    this.sortBy,
  });
}

/// UseCase: Refine an existing search with natural-language text input.
class RefineSearch {
  final SearchRepository _repo;
  const RefineSearch(this._repo);

  Future<Either<Failure, SearchTaskEntity>> call(RefineSearchParams params) {
    if (params.taskId.isEmpty) {
      return Future.value(
        const Left(ValidationFailure({'taskId': '搜索任务ID不能为空'})),
      );
    }
    if (params.text.trim().isEmpty) {
      return Future.value(
        const Left(ValidationFailure({'text': '请输入进一步的搜索描述'})),
      );
    }
    return _repo.refineSearch(
      taskId: params.taskId,
      text: params.text.trim(),
      sortBy: params.sortBy,
    );
  }
}
