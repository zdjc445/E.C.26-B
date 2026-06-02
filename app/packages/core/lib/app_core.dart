/// app_core — Cross-cutting infrastructure for all feature packages.
///
/// Public API surface (barrel):
///   - Failure hierarchy
///   - Either monad
///   - ApiResponse parsing
///   - Money value object
///   - Shared enums
///   - Dio factory + interceptor chain
///   - Cache policy
///   - Token store contract + impl
///   - App theme
library app_core;

// Failure & Either
export 'src/failure.dart';
export 'src/either.dart';

// API response
export 'src/api_response.dart';

// Value objects
export 'src/money.dart';

// Enums
export 'src/enums.dart';

// Network
export 'src/network/dio_factory.dart';
export 'src/network/error_interceptor.dart';
export 'src/network/api_client_provider.dart';

// Cache
export 'src/cache/cache_policy.dart';

// Store
export 'src/store/token_store.dart';

// Theme
export 'src/theme/app_theme.dart';
