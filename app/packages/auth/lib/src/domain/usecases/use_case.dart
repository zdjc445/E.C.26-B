import 'package:app_core/app_core.dart';

/// Abstraction for a single-use-case input object.
abstract class UseCase<Input, Output> {
  Future<Either<Failure, Output>> call(Input params);
}

/// UseCase that needs no parameters.
abstract class NoParamsUseCase<Output> {
  Future<Either<Failure, Output>> call();
}
