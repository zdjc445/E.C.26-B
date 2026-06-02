import 'package:app_core/app_core.dart';
import '../entities/filter_criteria.dart';
import '../entities/search_task_entity.dart';

/// Contract for search data access (offline-first).
abstract class SearchRepository {
  /// Create a new search task and return the results.
  Future<Either<Failure, SearchTaskEntity>> createSearch({
    String? recognitionId,
    String? query,
    List<Platform>? platforms,
    SourceType? sourceType,
    FilterCriteria? filters,
    SortMode? sortBy,
  });

  /// Refine an existing search task with new natural-language input.
  Future<Either<Failure, SearchTaskEntity>> refineSearch({
    required String taskId,
    required String text,
    SortMode? sortBy,
  });

  /// Get paginated search history.
  Future<Either<Failure, List<SearchTaskEntity>>> getSearchHistory({
    int page = 1,
    int pageSize = 20,
  });
}
