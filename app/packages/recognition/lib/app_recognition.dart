/// app_recognition — Image recognition module barrel.
///
/// Exposes:
///   - RecognitionEntity, SuggestionCard (domain entities)
///   - RecognitionProvider for state management
///   - RecognitionScreen route builder
library app_recognition;

export 'src/domain/entities/recognition_entity.dart';
export 'src/domain/entities/suggestion_card.dart';
export 'src/presentation/providers/recognition_provider.dart'
    show
        recognitionProvider,
        RecognitionNotifier,
        RecognitionState,
        RecognitionStatus;
export 'src/presentation/screens/recognition_screen.dart';

import 'package:go_router/go_router.dart';
import 'src/presentation/screens/recognition_screen.dart';

/// Returns the GoRouter route configuration for this package.
List<RouteBase> recognitionRoutes() => [
  GoRoute(
    path: '/recognition',
    builder: (context, state) => const RecognitionScreen(),
  ),
];
