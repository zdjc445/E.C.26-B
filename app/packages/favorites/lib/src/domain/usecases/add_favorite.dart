import 'package:app_core/app_core.dart';
import '../entities/favorite_entity.dart';
import '../repositories/favorite_repository.dart';

class AddFavoriteParams {
  final String platformProductId;
  final String? note;

  const AddFavoriteParams({required this.platformProductId, this.note});
}

class AddFavorite {
  final FavoriteRepository _repo;

  const AddFavorite(this._repo);

  Future<Either<Failure, FavoriteEntity>> call(AddFavoriteParams params) async {
    if (params.platformProductId.isEmpty) {
      return const Left(ValidationFailure({
        'platformProductId': '商品 ID 不能为空',
      }));
    }
    return _repo.addFavorite(
      platformProductId: params.platformProductId,
      note: params.note,
    );
  }
}
