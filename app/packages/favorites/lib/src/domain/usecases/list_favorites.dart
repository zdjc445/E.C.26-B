import 'package:app_core/app_core.dart';
import '../entities/favorite_entity.dart';
import '../repositories/favorite_repository.dart';

class ListFavoritesParams {
  final int page;
  final int pageSize;

  const ListFavoritesParams({this.page = 1, this.pageSize = 20})
    : assert(page >= 1),
      assert(pageSize >= 1 && pageSize <= 100);
}

class ListFavorites {
  final FavoriteRepository _repo;

  const ListFavorites(this._repo);

  Future<Either<Failure, ({
    List<FavoriteEntity> items,
    int page,
    int pageSize,
    int total,
  })>> call(ListFavoritesParams params) async {
    return _repo.listFavorites(page: params.page, pageSize: params.pageSize);
  }
}
