/// Sealed class hierarchy for all possible failures in the app.
/// Every UseCase returns `Either<Failure, T>`, and the presentation layer
/// maps each Failure subclass to appropriate UI (error page, retry, snackbar).
sealed class Failure {
  const Failure();
}

/// 4xx/5xx response from the backend. Carries the API error [code] and [message].
class ServerFailure extends Failure {
  final int code;
  final String message;
  const ServerFailure(this.code, this.message);

  @override
  String toString() => 'ServerFailure($code, $message)';
}

/// Network-level error: timeout, DNS resolution failure, no connectivity.
class NetworkFailure extends Failure {
  final String message;
  const NetworkFailure(this.message);

  @override
  String toString() => 'NetworkFailure($message)';
}

/// 401 — access token expired and refresh also failed.
class AuthFailure extends Failure {
  final String message;
  const AuthFailure(this.message);

  @override
  String toString() => 'AuthFailure($message)';
}

/// Local cache miss or corruption.
class CacheFailure extends Failure {
  final String message;
  const CacheFailure(this.message);

  @override
  String toString() => 'CacheFailure($message)';
}

/// Client-side validation errors (field → message map).
class ValidationFailure extends Failure {
  final Map<String, String> errors;
  const ValidationFailure(this.errors);

  @override
  String toString() => 'ValidationFailure($errors)';
}

/// Generic unexpected error.
class UnexpectedFailure extends Failure {
  final String message;
  const UnexpectedFailure(this.message);

  @override
  String toString() => 'UnexpectedFailure($message)';
}
