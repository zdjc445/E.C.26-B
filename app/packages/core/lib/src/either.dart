/// Lightweight Either monad — avoids pulling in dartz just for this.
/// Used as the return type of every UseCase: `Future<Either<Failure, T>>`.
sealed class Either<L, R> {
  const Either();

  bool get isLeft => this is Left<L, R>;
  bool get isRight => this is Right<L, R>;

  L get left => (this as Left<L, R>).value;
  R get right => (this as Right<L, R>).value;

  T fold<T>(T Function(L) onLeft, T Function(R) onRight) {
    if (this is Left<L, R>) {
      return onLeft((this as Left<L, R>).value);
    }
    return onRight((this as Right<L, R>).value);
  }

  Either<T, R> mapLeft<T>(T Function(L) f) {
    if (this is Left<L, R>) return Left(f((this as Left<L, R>).value));
    return Right((this as Right<L, R>).value);
  }

  Either<L, T> mapRight<T>(T Function(R) f) {
    if (this is Right<L, R>) return Right(f((this as Right<L, R>).value));
    return Left((this as Left<L, R>).value);
  }
}

class Left<L, R> extends Either<L, R> {
  final L value;
  const Left(this.value);
}

class Right<L, R> extends Either<L, R> {
  final R value;
  const Right(this.value);
}
