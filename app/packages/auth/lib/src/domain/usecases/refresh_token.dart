import 'package:app_core/app_core.dart';
import '../repositories/auth_repository.dart';
import '../entities/user.dart';
import 'use_case.dart';

class RefreshTokenUseCase extends UseCase<String, AuthCredentials> {
  final AuthRepository _repo;
  RefreshTokenUseCase(this._repo);

  @override
  Future<Either<Failure, AuthCredentials>> call(String refreshToken) async {
    if (refreshToken.isEmpty) {
      return const Left(AuthFailure('没有可用的刷新令牌'));
    }
    return _repo.refreshToken(refreshToken);
  }
}
