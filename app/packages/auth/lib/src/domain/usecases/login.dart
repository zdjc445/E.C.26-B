import 'package:app_core/app_core.dart';
import '../repositories/auth_repository.dart';
import '../entities/user.dart';
import 'use_case.dart';

class LoginParams {
  final String username;
  final String password;
  const LoginParams({required this.username, required this.password});
}

class LoginUseCase extends UseCase<LoginParams, AuthCredentials> {
  final AuthRepository _repo;
  LoginUseCase(this._repo);

  @override
  Future<Either<Failure, AuthCredentials>> call(LoginParams params) async {
    if (params.username.length < 3) {
      return const Left(ValidationFailure({'username': '用户名至少 3 个字符'}));
    }
    if (params.password.length < 8) {
      return const Left(ValidationFailure({'password': '密码至少 8 个字符'}));
    }
    return _repo.login(username: params.username, password: params.password);
  }
}
