import 'package:app_core/app_core.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../domain/entities/search_task_entity.dart';
import '../../domain/entities/product_entity.dart';
import '../../domain/entities/filter_criteria.dart';
import '../../domain/entities/platform_stats.dart';
import '../../domain/usecases/create_search.dart';
import '../../domain/usecases/refine_search.dart';
import '../../domain/usecases/get_search_history.dart';
import '../../data/datasources/search_remote_datasource.dart';
import '../../data/datasources/search_local_cache.dart';
import '../../data/repositories/search_repository_impl.dart';

// ── Data sources ──────────────────────────────────────────
final _searchRemoteProvider = Provider<SearchRemoteDataSource>(
  (ref) => SearchRemoteDataSource(ref.read(appDioProvider)),
);

final _searchCacheProvider = Provider<SearchLocalCache>(
  (ref) => SearchLocalCache(),
);

final _searchRepoProvider = Provider<SearchRepositoryImpl>(
  (ref) => SearchRepositoryImpl(
    ref.read(_searchRemoteProvider),
    ref.read(_searchCacheProvider),
  ),
);

// ── Use cases ─────────────────────────────────────────────
final createSearchUseCaseProvider = Provider<CreateSearch>(
  (ref) => CreateSearch(ref.read(_searchRepoProvider)),
);

final refineSearchUseCaseProvider = Provider<RefineSearch>(
  (ref) => RefineSearch(ref.read(_searchRepoProvider)),
);

final getSearchHistoryUseCaseProvider = Provider<GetSearchHistory>(
  (ref) => GetSearchHistory(ref.read(_searchRepoProvider)),
);

// ── Search state ──────────────────────────────────────────
enum SearchStatus { idle, searching, loaded, refining, error }

class SearchState {
  final SearchStatus status;
  final SearchTaskEntity? currentTask;
  final List<ProductEntity> products;
  final List<PlatformStats> platformStats;
  final int totalResults;
  final FilterCriteria activeFilters;
  final SortMode currentSort;
  final SourceType currentSourceType;
  final Set<Platform> activePlatforms;
  final List<SearchTaskEntity> history;
  final String? error;

  const SearchState({
    this.status = SearchStatus.idle,
    this.currentTask,
    this.products = const [],
    this.platformStats = const [],
    this.totalResults = 0,
    this.activeFilters = const FilterCriteria(),
    this.currentSort = SortMode.comprehensive,
    this.currentSourceType = SourceType.mock,
    this.activePlatforms = const {},
    this.history = const [],
    this.error,
  });

  SearchState copyWith({
    SearchStatus? status,
    SearchTaskEntity? currentTask,
    List<ProductEntity>? products,
    List<PlatformStats>? platformStats,
    int? totalResults,
    FilterCriteria? activeFilters,
    SortMode? currentSort,
    SourceType? currentSourceType,
    Set<Platform>? activePlatforms,
    List<SearchTaskEntity>? history,
    String? error,
  }) {
    return SearchState(
      status: status ?? this.status,
      currentTask: currentTask ?? this.currentTask,
      products: products ?? this.products,
      platformStats: platformStats ?? this.platformStats,
      totalResults: totalResults ?? this.totalResults,
      activeFilters: activeFilters ?? this.activeFilters,
      currentSort: currentSort ?? this.currentSort,
      currentSourceType: currentSourceType ?? this.currentSourceType,
      activePlatforms: activePlatforms ?? this.activePlatforms,
      history: history ?? this.history,
      error: error,
    );
  }
}

class SearchNotifier extends StateNotifier<SearchState> {
  final CreateSearch _createSearch;
  final RefineSearch _refineSearch;
  final GetSearchHistory _getSearchHistory;

  SearchNotifier({
    required CreateSearch createSearch,
    required RefineSearch refineSearch,
    required GetSearchHistory getSearchHistory,
  })  : _createSearch = createSearch,
        _refineSearch = refineSearch,
        _getSearchHistory = getSearchHistory,
        super(const SearchState());

  /// Execute a new search given the current state's parameters and optional overrides.
  Future<void> search({
    String? recognitionId,
    String? query,
  }) async {
    state = state.copyWith(status: SearchStatus.searching, error: null);
    final result = await _createSearch(CreateSearchParams(
      recognitionId: recognitionId,
      query: query,
      platforms: state.activePlatforms.isNotEmpty
          ? state.activePlatforms.toList()
          : null,
      sourceType: state.currentSourceType,
      filters: state.activeFilters.hasFilters ? state.activeFilters : null,
      sortBy: state.currentSort,
    ));
    result.fold(
      (failure) => state = state.copyWith(
        status: SearchStatus.error,
        error: _failureMessage(failure),
      ),
      (task) => _applyTask(task),
    );
  }

  /// Refine the current search with natural language text.
  Future<void> refine(String text) async {
    final taskId = state.currentTask?.taskId;
    if (taskId == null) return;

    state = state.copyWith(status: SearchStatus.refining, error: null);
    final result = await _refineSearch(RefineSearchParams(
      taskId: taskId,
      text: text,
      sortBy: state.currentSort != SortMode.comprehensive
          ? state.currentSort
          : null,
    ));
    result.fold(
      (failure) => state = state.copyWith(
        status: SearchStatus.error,
        error: _failureMessage(failure),
      ),
      (task) => _applyTask(task),
    );
  }

  /// Load search history.
  Future<void> loadHistory({int page = 1}) async {
    final result = await _getSearchHistory(page: page);
    result.fold(
      (_) {}, // Silently ignore history load failures.
      (tasks) => state = state.copyWith(history: tasks),
    );
  }

  void _applyTask(SearchTaskEntity task) {
    state = state.copyWith(
      status: SearchStatus.loaded,
      currentTask: task,
      products: task.results,
      platformStats: task.platformStats,
      totalResults: task.totalResults,
      activeFilters: task.filters ?? state.activeFilters,
      currentSort: task.sortBy ?? state.currentSort,
      error: null,
    );
  }

  // ── Filter / sort / source / platform setters ──────────

  void setSort(SortMode sort) {
    state = state.copyWith(currentSort: sort);
  }

  void setSourceType(SourceType sourceType) {
    state = state.copyWith(currentSourceType: sourceType);
  }

  void togglePlatform(Platform platform) {
    final platforms = Set<Platform>.from(state.activePlatforms);
    if (platforms.contains(platform)) {
      platforms.remove(platform);
    } else {
      platforms.add(platform);
    }
    state = state.copyWith(activePlatforms: platforms);
  }

  void setPriceRange(double? min, double? max) {
    state = state.copyWith(
      activeFilters: state.activeFilters.copyWith(
        priceMin: min,
        priceMax: max,
      ),
    );
  }

  void setMinRating(double? rating) {
    state = state.copyWith(
      activeFilters: state.activeFilters.copyWith(minRating: rating),
    );
  }

  void toggleOfficialOnly() {
    final current = state.activeFilters.officialOnly ?? false;
    state = state.copyWith(
      activeFilters: state.activeFilters.copyWith(officialOnly: !current),
    );
  }

  void toggleSelfOperated() {
    final current = state.activeFilters.selfOperatedOnly ?? false;
    state = state.copyWith(
      activeFilters: state.activeFilters.copyWith(selfOperatedOnly: !current),
    );
  }

  void addBrandFilter(String brand) {
    state = state.copyWith(
      activeFilters: state.activeFilters.copyWith(brand: brand),
    );
  }

  void clearFilters() {
    state = state.copyWith(
      activeFilters: const FilterCriteria(),
      currentSort: SortMode.comprehensive,
      activePlatforms: const {},
    );
  }

  void reset() {
    state = const SearchState();
  }

  String _failureMessage(Failure failure) {
    return switch (failure) {
      ServerFailure(:final message) => message,
      NetworkFailure(:final message) => message,
      ValidationFailure(:final errors) => errors.values.join('；'),
      UnexpectedFailure(:final message) => message,
      _ => '搜索失败，请重试',
    };
  }
}

final searchProvider =
    StateNotifierProvider<SearchNotifier, SearchState>((ref) {
  return SearchNotifier(
    createSearch: ref.read(createSearchUseCaseProvider),
    refineSearch: ref.read(refineSearchUseCaseProvider),
    getSearchHistory: ref.read(getSearchHistoryUseCaseProvider),
  );
});
