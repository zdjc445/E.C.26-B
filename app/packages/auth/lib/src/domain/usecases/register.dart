import 'package:app_core/app_core.dart';
import '../repositories/auth_repository.dart';
import '../entities/user.dart';
import 'use_case.dart';

class RegisterParams {
  final String username;
  final String password;
  final String? nickname;
  const RegisterParams({required this.username, required this.password, this.nickname});
}

class RegisterUseCase extends UseCase<RegisterParams, AuthCredentials> {
  final AuthRepository _repo;
  RegisterUseCase(this._repo);

  @override
  Future<Either<Failure, AuthCredentials>> call(RegisterParams params) async {
    if (params.username.length < 3 || params.username.length > 32) {
      return const Left(ValidationFailure({'username': '用户名需要 3-32 个字符'}));
    }
    if (params.password.length < 8) {
      return const Left(ValidationFailure({'password': '密码至少 8 个字符'}));
    }
    return _repo.register(
      username: params.username,
      password: params.password,
      nickname: params.nickname,
    );
  }
}
