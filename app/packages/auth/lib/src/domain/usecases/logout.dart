import 'package:app_core/app_core.dart';
import '../repositories/auth_repository.dart';
import 'use_case.dart';

class LogoutUseCase extends UseCase<String, void> {
  final AuthRepository _repo;
  LogoutUseCase(this._repo);

  @override
  Future<Either<Failure, void>> call(String refreshToken) async {
    return _repo.logout(refreshToken);
  }
}
