import 'package:app_core/app_core.dart';
import 'package:dio/dio.dart';
import '../../domain/entities/user.dart';
import '../../domain/repositories/auth_repository.dart';
import '../datasources/auth_remote.dart';
import '../mappers/user_mapper.dart';

class AuthRepositoryImpl implements AuthRepository {
  final AuthRemoteDataSource _remote;
  final TokenStore _tokenStore;

  AuthRepositoryImpl(this._remote, this._tokenStore);

  @override
  Future<Either<Failure, AuthCredentials>> login({
    required String username,
    required String password,
  }) async {
    try {
      final dto = await _remote.login(username: username, password: password);
      final credentials = AuthMapper.credentialsFromDto(dto);
      await _tokenStore.saveTokens(
        accessToken: credentials.accessToken,
        refreshToken: credentials.refreshToken,
      );
      return Right(credentials);
    } on DioException catch (e) {
      return Left(mapDioError(e));
    }
  }

  @override
  Future<Either<Failure, AuthCredentials>> register({
    required String username,
    required String password,
    String? nickname,
  }) async {
    try {
      final dto = await _remote.register(
        username: username,
        password: password,
        nickname: nickname,
      );
      final credentials = AuthMapper.credentialsFromDto(dto);
      await _tokenStore.saveTokens(
        accessToken: credentials.accessToken,
        refreshToken: credentials.refreshToken,
      );
      return Right(credentials);
    } on DioException catch (e) {
      return Left(mapDioError(e));
    }
  }

  @override
  Future<Either<Failure, AuthCredentials>> refreshToken(String refreshToken) async {
    try {
      final userResult = await getCurrentUser();
      if (userResult.isLeft) return Left((userResult as Left).value);

      final dto = await _remote.refresh(refreshToken);
      final credentials = AuthMapper.credentialsFromRefreshDto(
        dto,
        (userResult as Right).value,
      );
      await _tokenStore.saveTokens(
        accessToken: credentials.accessToken,
        refreshToken: credentials.refreshToken,
      );
      return Right(credentials);
    } on DioException catch (e) {
      return Left(mapDioError(e));
    }
  }

  @override
  Future<Either<Failure, void>> logout(String refreshToken) async {
    try {
      await _remote.logout(refreshToken);
      await _tokenStore.clear();
      return const Right(null);
    } on DioException catch (e) {
      await _tokenStore.clear();
      return Left(mapDioError(e));
    }
  }

  @override
  Future<Either<Failure, User>> getCurrentUser() async {
    try {
      final json = await _remote.getCurrentUser();
      return Right(User.fromJson(json));
    } on DioException catch (e) {
      return Left(mapDioError(e));
    }
  }

  @override
  Future<AuthCredentials?> restoreSession() async {
    final accessToken = await _tokenStore.getAccessToken();
    final refreshToken = await _tokenStore.getRefreshToken();
    if (accessToken == null || refreshToken == null) return null;

    // Verify the access token is still valid by fetching current user.
    final userResult = await getCurrentUser();
    if (userResult.isRight) {
      return AuthCredentials(
        accessToken: accessToken,
        refreshToken: refreshToken,
        expiresIn: 7200,
        user: (userResult as Right).value,
      );
    }

    // Access token expired — try refresh.
    final refreshResult = await this.refreshToken(refreshToken);
    if (refreshResult.isRight) return (refreshResult as Right).value;

    // Both failed — clear session.
    await _tokenStore.clear();
    return null;
  }

  @override
  Future<void> clearSession() => _tokenStore.clear();
}
