import 'package:app_core/app_core.dart';
import '../repositories/favorite_repository.dart';

class RemoveFavorite {
  final FavoriteRepository _repo;

  const RemoveFavorite(this._repo);

  Future<Either<Failure, void>> call(String favoriteId) async {
    if (favoriteId.isEmpty) {
      return const Left(ValidationFailure({
        'favoriteId': '收藏 ID 不能为空',
      }));
    }
    return _repo.removeFavorite(favoriteId);
  }
}
