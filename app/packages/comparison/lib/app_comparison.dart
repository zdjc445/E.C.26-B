/// app_comparison — Price comparison module barrel.
///
/// Exposes:
///   - GoRouter route builders for /comparison/*
///   - ComparisonProvider for state management
///   - Domain entities for other packages
library app_comparison;

// Domain entities
export 'src/domain/entities/comparison_entity.dart';

// Use cases
export 'src/domain/usecases/create_comparison.dart';

// Providers
export 'src/presentation/providers/comparison_provider.dart'
    show comparisonProvider, ComparisonState, ComparisonNotifier;

// Screens
export 'src/presentation/screens/comparison_screen.dart';

// GoRouter helper — returns the route configuration for this package.
import 'package:go_router/go_router.dart';
import 'src/presentation/screens/comparison_screen.dart';

List<RouteBase> comparisonRoutes() => [
  GoRoute(
    path: '/comparison',
    builder: (context, state) {
      final extra = state.extra as Map<String, dynamic>? ?? {};
      final searchTaskId = extra['searchTaskId'] as String? ?? '';
      final platformProductIds =
          (extra['platformProductIds'] as List<dynamic>?)
                  ?.map((e) => e.toString())
                  .toList() ??
              <String>[];
      return ComparisonScreen(
        searchTaskId: searchTaskId,
        platformProductIds: platformProductIds,
      );
    },
  ),
];
