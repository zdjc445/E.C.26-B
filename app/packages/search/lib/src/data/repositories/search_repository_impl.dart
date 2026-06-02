import 'package:app_core/app_core.dart';
import 'package:dio/dio.dart';
import '../../domain/entities/filter_criteria.dart';
import '../../domain/entities/search_task_entity.dart';
import '../../domain/repositories/search_repository.dart';
import '../datasources/search_remote_datasource.dart';
import '../datasources/search_local_cache.dart';
import '../mappers/search_mapper.dart';

/// Offline-first search repository implementation.
/// Tries remote first; caches successful results for instant replay.
class SearchRepositoryImpl implements SearchRepository {
  final SearchRemoteDataSource _remote;
  final SearchLocalCache _cache;

  SearchRepositoryImpl(this._remote, this._cache);

  @override
  Future<Either<Failure, SearchTaskEntity>> createSearch({
    String? recognitionId,
    String? query,
    List<Platform>? platforms,
    SourceType? sourceType,
    FilterCriteria? filters,
    SortMode? sortBy,
  }) async {
    try {
      final dto = await _remote.createSearch(
        recognitionId: recognitionId,
        query: query,
        platforms: platforms?.map((p) => p.apiValue).toList(),
        sourceType: sourceType?.apiValue,
        filters: filters?.toJson(),
        sortBy: sortBy?.apiValue,
      );
      final task = SearchMapper.fromDto(dto);
      _cache.cacheTask(task);
      return Right(task);
    } on DioException catch (e) {
      return Left(mapDioError(e));
    }
  }

  @override
  Future<Either<Failure, SearchTaskEntity>> refineSearch({
    required String taskId,
    required String text,
    SortMode? sortBy,
  }) async {
    try {
      final dto = await _remote.refineSearch(
        taskId: taskId,
        text: text,
        sortBy: sortBy?.apiValue,
      );
      final task = SearchMapper.fromDto(dto);
      _cache.cacheTask(task);
      return Right(task);
    } on DioException catch (e) {
      // Fallback to cache on network failure for refinement.
      final cached = _cache.getTask(taskId);
      if (cached != null) {
        return Right(cached);
      }
      return Left(mapDioError(e));
    }
  }

  @override
  Future<Either<Failure, List<SearchTaskEntity>>> getSearchHistory({
    int page = 1,
    int pageSize = 20,
  }) async {
    try {
      final dtos = await _remote.getSearchHistory(
        page: page,
        pageSize: pageSize,
      );
      final tasks = SearchMapper.fromDtoList(dtos);
      for (final task in tasks) {
        _cache.cacheTask(task);
      }
      return Right(tasks);
    } on DioException catch (e) {
      // Fallback to local cache on network failure.
      final cached = _cache.getHistory(page: page, pageSize: pageSize);
      if (cached.isNotEmpty) {
        return Right(cached);
      }
      return Left(mapDioError(e));
    }
  }
}
