import 'package:app_core/app_core.dart';
import '../entities/search_task_entity.dart';
import '../repositories/search_repository.dart';

/// UseCase: Get paginated search history.
class GetSearchHistory {
  final SearchRepository _repo;
  const GetSearchHistory(this._repo);

  Future<Either<Failure, List<SearchTaskEntity>>> call({
    int page = 1,
    int pageSize = 20,
  }) {
    return _repo.getSearchHistory(page: page, pageSize: pageSize);
  }
}
