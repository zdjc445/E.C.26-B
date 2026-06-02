import 'package:app_core/app_core.dart';
import '../entities/favorite_entity.dart';

/// Contract for favorites data access.
/// Implemented in the data layer via remote Dio calls.
abstract class FavoriteRepository {
  /// Add a product to favorites. Optionally attach a [note].
  Future<Either<Failure, FavoriteEntity>> addFavorite({
    required String platformProductId,
    String? note,
  });

  /// Remove a favorite by its [favoriteId].
  Future<Either<Failure, void>> removeFavorite(String favoriteId);

  /// List favorites with pagination.
  Future<Either<Failure, ({
    List<FavoriteEntity> items,
    int page,
    int pageSize,
    int total,
  })>> listFavorites({int page = 1, int pageSize = 20});
}
