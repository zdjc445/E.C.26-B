/// app_search — Product search module barrel.
///
/// Exposes:
///   - SearchTaskEntity, ProductEntity, FilterCriteria, PlatformStats (domain entities)
///   - SearchProvider for state management
///   - SearchResultsScreen route builder
library app_search;

export 'src/domain/entities/search_task_entity.dart';
export 'src/domain/entities/product_entity.dart';
export 'src/domain/entities/filter_criteria.dart';
export 'src/domain/entities/platform_stats.dart';
export 'src/presentation/providers/search_provider.dart'
    show searchProvider, SearchNotifier, SearchState, SearchStatus;
export 'src/presentation/screens/search_results_screen.dart';

import 'package:go_router/go_router.dart';
import 'src/presentation/screens/search_results_screen.dart';

/// Returns the GoRouter route configuration for this package.
List<RouteBase> searchRoutes() => [
  GoRoute(
    path: '/search',
    builder: (context, state) => const SearchResultsScreen(),
  ),
];
