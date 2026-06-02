import 'package:app_core/app_core.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../domain/entities/favorite_entity.dart';
import '../../domain/usecases/add_favorite.dart';
import '../../domain/usecases/remove_favorite.dart';
import '../../domain/usecases/list_favorites.dart';
import '../../data/datasources/favorite_remote_datasource.dart';
import '../../data/repositories/favorite_repository_impl.dart';

// ── Data sources ──────────────────────────────────────────
final _favoriteRemoteProvider = Provider<FavoriteRemoteDataSource>(
  (ref) => FavoriteRemoteDataSource(ref.read(appDioProvider)),
);

final _favoriteRepoProvider = Provider<FavoriteRepositoryImpl>(
  (ref) => FavoriteRepositoryImpl(ref.read(_favoriteRemoteProvider)),
);

// ── Use cases ─────────────────────────────────────────────
final addFavoriteProvider = Provider<AddFavorite>(
  (ref) => AddFavorite(ref.read(_favoriteRepoProvider)),
);

final removeFavoriteProvider = Provider<RemoveFavorite>(
  (ref) => RemoveFavorite(ref.read(_favoriteRepoProvider)),
);

final listFavoritesProvider = Provider<ListFavorites>(
  (ref) => ListFavorites(ref.read(_favoriteRepoProvider)),
);

// ── Favorites state ───────────────────────────────────────
enum FavoritesLoadStatus { initial, loading, loaded, error, empty }

class FavoritesState {
  final FavoritesLoadStatus status;
  final List<FavoriteEntity> favorites;
  final int page;
  final int total;
  final String? error;
  final bool hasMore;

  const FavoritesState({
    this.status = FavoritesLoadStatus.initial,
    this.favorites = const [],
    this.page = 1,
    this.total = 0,
    this.error,
    this.hasMore = true,
  });

  FavoritesState copyWith({
    FavoritesLoadStatus? status,
    List<FavoriteEntity>? favorites,
    int? page,
    int? total,
    String? error,
    bool? hasMore,
  }) {
    return FavoritesState(
      status: status ?? this.status,
      favorites: favorites ?? this.favorites,
      page: page ?? this.page,
      total: total ?? this.total,
      error: error,
      hasMore: hasMore ?? this.hasMore,
    );
  }
}

class FavoriteNotifier extends StateNotifier<FavoritesState> {
  final AddFavorite _addFavorite;
  final RemoveFavorite _removeFavorite;
  final ListFavorites _listFavorites;

  FavoriteNotifier({
    required AddFavorite addFavorite,
    required RemoveFavorite removeFavorite,
    required ListFavorites listFavorites,
  })  : _addFavorite = addFavorite,
        _removeFavorite = removeFavorite,
        _listFavorites = listFavorites,
        super(const FavoritesState());

  /// Load the first page of favorites.
  Future<void> loadFavorites() async {
    state = state.copyWith(status: FavoritesLoadStatus.loading, error: null);
    final result = await _listFavorites(const ListFavoritesParams(page: 1));
    result.fold(
      (failure) => state = state.copyWith(
        status: FavoritesLoadStatus.error,
        error: _failureMessage(failure),
      ),
      (data) => state = FavoritesState(
        status: data.items.isEmpty
            ? FavoritesLoadStatus.empty
            : FavoritesLoadStatus.loaded,
        favorites: data.items,
        page: data.page,
        total: data.total,
        hasMore: data.items.length >= data.pageSize &&
            data.items.length < data.total,
      ),
    );
  }

  /// Load the next page (append to current list).
  Future<void> loadMore() async {
    if (!state.hasMore || state.status == FavoritesLoadStatus.loading) return;
    final nextPage = state.page + 1;
    state = state.copyWith(status: FavoritesLoadStatus.loading);
    final result =
        await _listFavorites(ListFavoritesParams(page: nextPage, pageSize: 20));
    result.fold(
      (failure) => state = state.copyWith(
        status: FavoritesLoadStatus.loaded,
        error: _failureMessage(failure),
      ),
      (data) {
        final allItems = [...state.favorites, ...data.items];
        state = state.copyWith(
          status: FavoritesLoadStatus.loaded,
          favorites: allItems,
          page: data.page,
          total: data.total,
          hasMore: data.items.length >= data.pageSize &&
              allItems.length < data.total,
        );
      },
    );
  }

  /// Add a product to favorites.
  Future<bool> addFavorite(String platformProductId, {String? note}) async {
    final result = await _addFavorite(
        AddFavoriteParams(platformProductId: platformProductId, note: note));
    bool success = false;
    result.fold(
      (failure) => state = state.copyWith(error: _failureMessage(failure)),
      (favorite) {
        state = state.copyWith(
          favorites: [favorite, ...state.favorites],
          total: state.total + 1,
          status: FavoritesLoadStatus.loaded,
          error: null,
        );
        success = true;
      },
    );
    return success;
  }

  /// Remove a favorite by its ID.
  Future<bool> removeFavorite(String favoriteId) async {
    // Optimistically remove.
    final previousFavorites = List<FavoriteEntity>.from(state.favorites);
    state = state.copyWith(
      favorites:
          state.favorites.where((f) => f.favoriteId != favoriteId).toList(),
      total: state.total - 1,
    );
    if (state.favorites.isEmpty) {
      state = state.copyWith(status: FavoritesLoadStatus.empty);
    }

    final result = await _removeFavorite(favoriteId);
    bool success = true;
    result.fold(
      (failure) {
        // Rollback.
        state = state.copyWith(
          favorites: previousFavorites,
          total: state.total + 1,
          error: _failureMessage(failure),
        );
        success = false;
      },
      (_) {},
    );
    return success;
  }

  void clearError() => state = state.copyWith(error: null);

  String _failureMessage(Failure failure) {
    return switch (failure) {
      ServerFailure(:final message) => message,
      NetworkFailure(:final message) => message,
      AuthFailure(:final message) => message,
      ValidationFailure(:final errors) => errors.values.join('；'),
      UnexpectedFailure(:final message) => message,
      CacheFailure(:final message) => message,
    };
  }
}

final favoriteProvider =
    StateNotifierProvider<FavoriteNotifier, FavoritesState>((ref) {
  return FavoriteNotifier(
    addFavorite: ref.read(addFavoriteProvider),
    removeFavorite: ref.read(removeFavoriteProvider),
    listFavorites: ref.read(listFavoritesProvider),
  );
});
