import 'package:app_core/app_core.dart';
import '../entities/user.dart';

/// Contract for authentication data access.
/// Implemented in the data layer (remote Dio calls + local token storage).
abstract class AuthRepository {
  Future<Either<Failure, AuthCredentials>> login({
    required String username,
    required String password,
  });

  Future<Either<Failure, AuthCredentials>> register({
    required String username,
    required String password,
    String? nickname,
  });

  Future<Either<Failure, AuthCredentials>> refreshToken(String refreshToken);

  Future<Either<Failure, void>> logout(String refreshToken);

  Future<Either<Failure, User>> getCurrentUser();

  /// Try to restore a session from stored tokens. Returns null if no session.
  Future<AuthCredentials?> restoreSession();

  /// Clear all stored session data.
  Future<void> clearSession();
}
