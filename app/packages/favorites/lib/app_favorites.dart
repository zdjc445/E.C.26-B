/// app_favorites — Favorites module barrel.
///
/// Exposes:
///   - GoRouter route configuration for /favorites
///   - FavoriteProvider for state management
///   - Domain entities for other packages that may need them
library app_favorites;

// Entities
export 'src/domain/entities/favorite_entity.dart' show FavoriteEntity;

// Use cases
export 'src/domain/usecases/add_favorite.dart' show AddFavorite, AddFavoriteParams;
export 'src/domain/usecases/remove_favorite.dart' show RemoveFavorite;
export 'src/domain/usecases/list_favorites.dart' show ListFavorites, ListFavoritesParams;

// Provider
export 'src/presentation/providers/favorite_provider.dart'
    show favoriteProvider, FavoriteNotifier, FavoritesState, FavoritesLoadStatus;

// Screen
export 'src/presentation/screens/favorites_screen.dart' show FavoritesScreen;

// Widgets
export 'src/presentation/widgets/favorite_card.dart' show FavoriteCard;

// Route builder
import 'package:go_router/go_router.dart';
import 'src/presentation/screens/favorites_screen.dart';

List<RouteBase> favoritesRoutes() => [
      GoRoute(
        path: '/favorites',
        builder: (context, state) => const FavoritesScreen(),
      ),
    ];
