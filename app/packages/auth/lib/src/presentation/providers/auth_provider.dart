import 'package:app_core/app_core.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../domain/entities/user.dart';
import '../../domain/usecases/login.dart';
import '../../domain/usecases/register.dart';
import '../../domain/usecases/refresh_token.dart';
import '../../domain/usecases/logout.dart';
import '../../data/datasources/auth_remote.dart';
import '../../data/repositories/auth_repo_impl.dart';

// ── Data sources ──────────────────────────────────────────
final _authRemoteProvider = Provider<AuthRemoteDataSource>(
  (ref) => AuthRemoteDataSource(ref.read(appDioProvider)),
);

final _authRepoProvider = Provider<AuthRepositoryImpl>(
  (ref) => AuthRepositoryImpl(
    ref.read(_authRemoteProvider),
    ref.read(sharedTokenStoreProvider),
  ),
);

// ── Use cases ─────────────────────────────────────────────
final loginUseCaseProvider = Provider<LoginUseCase>(
  (ref) => LoginUseCase(ref.read(_authRepoProvider)),
);
final registerUseCaseProvider = Provider<RegisterUseCase>(
  (ref) => RegisterUseCase(ref.read(_authRepoProvider)),
);
final refreshTokenUseCaseProvider = Provider<RefreshTokenUseCase>(
  (ref) => RefreshTokenUseCase(ref.read(_authRepoProvider)),
);
final logoutUseCaseProvider = Provider<LogoutUseCase>(
  (ref) => LogoutUseCase(ref.read(_authRepoProvider)),
);

// ── Auth state ────────────────────────────────────────────
enum AuthStatus { initial, authenticated, unauthenticated }

class AuthState {
  final AuthStatus status;
  final User? user;
  final String? error;

  const AuthState({
    this.status = AuthStatus.initial,
    this.user,
    this.error,
  });

  AuthState copyWith({AuthStatus? status, User? user, String? error}) {
    return AuthState(
      status: status ?? this.status,
      user: user ?? this.user,
      error: error,
    );
  }
}

class AuthNotifier extends StateNotifier<AuthState> {
  final AuthRepositoryImpl _repo;
  final TokenStore _tokenStore;
  final LoginUseCase _loginUseCase;
  final RegisterUseCase _registerUseCase;
  final LogoutUseCase _logoutUseCase;

  AuthNotifier({
    required AuthRepositoryImpl repo,
    required TokenStore tokenStore,
    required LoginUseCase loginUseCase,
    required RegisterUseCase registerUseCase,
    required LogoutUseCase logoutUseCase,
  })  : _repo = repo,
        _tokenStore = tokenStore,
        _loginUseCase = loginUseCase,
        _registerUseCase = registerUseCase,
        _logoutUseCase = logoutUseCase,
        super(const AuthState());

  /// Attempt to restore a previous session from secure storage.
  Future<void> restoreSession() async {
    final credentials = await _repo.restoreSession();
    if (credentials != null) {
      state =
          AuthState(status: AuthStatus.authenticated, user: credentials.user);
    } else {
      state = const AuthState(status: AuthStatus.unauthenticated);
    }
  }

  Future<void> login(String username, String password) async {
    final result = await _loginUseCase(
        LoginParams(username: username, password: password));
    result.fold(
      (failure) => state = state.copyWith(error: _failureMessage(failure)),
      (credentials) => state =
          AuthState(status: AuthStatus.authenticated, user: credentials.user),
    );
  }

  Future<void> register(
      String username, String password, String? nickname) async {
    final result = await _registerUseCase(
      RegisterParams(
          username: username, password: password, nickname: nickname),
    );
    result.fold(
      (failure) => state = state.copyWith(error: _failureMessage(failure)),
      (credentials) => state =
          AuthState(status: AuthStatus.authenticated, user: credentials.user),
    );
  }

  Future<void> logout() async {
    final refreshToken = await _tokenStore.getRefreshToken();
    if (refreshToken == null) {
      await _repo.clearSession();
    } else {
      await _logoutUseCase(refreshToken);
    }
    state = const AuthState(status: AuthStatus.unauthenticated);
  }

  void clearError() {
    state = state.copyWith(error: null);
  }

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

final authProvider = StateNotifierProvider<AuthNotifier, AuthState>((ref) {
  return AuthNotifier(
    repo: ref.read(_authRepoProvider),
    tokenStore: ref.read(sharedTokenStoreProvider),
    loginUseCase: ref.read(loginUseCaseProvider),
    registerUseCase: ref.read(registerUseCaseProvider),
    logoutUseCase: ref.read(logoutUseCaseProvider),
  );
});
