/// app_recommendation — AI recommendation module barrel.
///
/// Exposes:
///   - GoRouter route builders for /recommendation/*
///   - RecommendationProvider for state management
///   - Domain entities for other packages
library app_recommendation;

// Domain entities
export 'src/domain/entities/recommendation_entity.dart';

// Use cases
export 'src/domain/usecases/create_recommendation.dart';

// Providers
export 'src/presentation/providers/recommendation_provider.dart'
    show recommendationProvider, RecommendationState, RecommendationNotifier;

// Screens
export 'src/presentation/screens/recommendation_screen.dart';

// GoRouter helper — returns the route configuration for this package.
import 'package:go_router/go_router.dart';
import 'src/presentation/screens/recommendation_screen.dart';

List<RouteBase> recommendationRoutes() => [
  GoRoute(
    path: '/recommendation',
    builder: (context, state) {
      final extra = state.extra as Map<String, dynamic>? ?? {};
      final searchTaskId = extra['searchTaskId'] as String? ?? '';
      final userQuery = extra['userQuery'] as String? ?? '';
      final candidateIds =
          (extra['candidateIds'] as List<dynamic>?)
                  ?.map((e) => e.toString())
                  .toList() ??
              <String>[];
      return RecommendationScreen(
        searchTaskId: searchTaskId,
        userQuery: userQuery,
        candidateIds: candidateIds,
      );
    },
  ),
];
