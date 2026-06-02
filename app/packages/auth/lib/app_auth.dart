/// app_auth — Authentication module barrel.
///
/// Exposes:
///   - GoRouter route configuration for /auth/*
///   - AuthProvider for shell-level session management
///   - Domain entities for other packages that depend on user info
library app_auth;

export 'src/domain/entities/user.dart';
export 'src/presentation/providers/auth_provider.dart' show authProvider, AuthState, AuthStatus, AuthNotifier;
export 'src/presentation/screens/login_screen.dart';
export 'src/domain/usecases/login.dart';
export 'src/domain/usecases/register.dart';
export 'src/domain/usecases/refresh_token.dart';
export 'src/domain/usecases/logout.dart';

// GoRouter helper — returns the route configuration for this package.
import 'package:go_router/go_router.dart';
import 'src/presentation/screens/login_screen.dart';

List<RouteBase> authRoutes() => [
  GoRoute(
    path: '/auth/login',
    builder: (context, state) => const LoginScreen(),
  ),
];
