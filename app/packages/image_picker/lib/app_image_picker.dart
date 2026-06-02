/// app_image_picker — Image capture and upload module barrel.
///
/// Exposes:
///   - ImageEntity (domain)
///   - StateNotifier provider for image picking/uploading
///   - CameraScreen route builder
library app_image_picker;

export 'src/domain/entities/image_entity.dart';
export 'src/presentation/providers/image_provider.dart'
    show imagePickerProvider, ImagePickerNotifier, ImagePickerState, ImagePickerStatus;
export 'src/presentation/screens/camera_screen.dart';

import 'package:go_router/go_router.dart';
import 'src/presentation/screens/camera_screen.dart';

/// Returns the GoRouter route configuration for this package.
List<RouteBase> imagePickerRoutes() => [
  GoRoute(
    path: '/camera',
    builder: (context, state) => const CameraScreen(),
  ),
];
