import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/image_provider.dart';

/// Full-screen camera preview with gallery fallback and upload trigger.
class CameraScreen extends ConsumerStatefulWidget {
  const CameraScreen({super.key});

  @override
  ConsumerState<CameraScreen> createState() => _CameraScreenState();
}

class _CameraScreenState extends ConsumerState<CameraScreen> {
  @override
  void dispose() {
    ref.read(imagePickerProvider.notifier).reset();
    super.dispose();
  }

  void _onPickCamera() {
    ref.read(imagePickerProvider.notifier).pickFromCamera();
  }

  void _onPickGallery() {
    ref.read(imagePickerProvider.notifier).pickFromGallery();
  }

  void _onUpload() {
    ref.read(imagePickerProvider.notifier).uploadImage();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(imagePickerProvider);
    final isUploading = state.status == ImagePickerStatus.uploading;
    final isPicking = state.status == ImagePickerStatus.picking;

    return Scaffold(
      appBar: AppBar(
        title: const Text('拍照识物'),
        actions: [
          if (state.status == ImagePickerStatus.picked ||
              state.status == ImagePickerStatus.error)
            IconButton(
              icon: const Icon(Icons.refresh),
              onPressed: () => ref.read(imagePickerProvider.notifier).reset(),
              tooltip: '重新选择',
            ),
        ],
      ),
      body: Column(
        children: [
          // Image preview area
          Expanded(
            child: _buildPreview(state),
          ),

          // Error message
          if (state.error != null)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              color: Colors.red.shade50,
              child: Row(
                children: [
                  Icon(Icons.error_outline, color: Colors.red.shade700, size: 20),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      state.error!,
                      style: TextStyle(color: Colors.red.shade700, fontSize: 14),
                    ),
                  ),
                ],
              ),
            ),

          // Action buttons
          _buildActionBar(state, isPicking, isUploading),
        ],
      ),
    );
  }

  Widget _buildPreview(ImagePickerState state) {
    if (state.status == ImagePickerStatus.idle) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.photo_camera, size: 80, color: Colors.grey.shade400),
            const SizedBox(height: 16),
            Text(
              '拍照或从相册选择商品图片',
              style: TextStyle(fontSize: 16, color: Colors.grey.shade600),
            ),
          ],
        ),
      );
    }

    if (state.status == ImagePickerStatus.picking) {
      return const Center(child: CircularProgressIndicator());
    }

    if (state.localPath != null) {
      return InteractiveViewer(
        child: Image.file(
          File(state.localPath!),
          fit: BoxFit.contain,
          width: double.infinity,
        ),
      );
    }

    return const SizedBox.shrink();
  }

  Widget _buildActionBar(
    ImagePickerState state,
    bool isPicking,
    bool isUploading,
  ) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (state.status == ImagePickerStatus.idle ||
                state.status == ImagePickerStatus.error ||
                state.status == ImagePickerStatus.picked) ...[
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: isPicking ? null : _onPickCamera,
                      icon: const Icon(Icons.camera_alt),
                      label: const Text('拍照'),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: isPicking ? null : _onPickGallery,
                      icon: const Icon(Icons.photo_library),
                      label: const Text('相册'),
                    ),
                  ),
                ],
              ),
              if (state.status == ImagePickerStatus.picked) ...[
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    onPressed: _onUpload,
                    icon: const Icon(Icons.cloud_upload),
                    label: const Text('上传并识别'),
                  ),
                ),
              ],
            ],
            if (isUploading)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 12),
                child: LinearProgressIndicator(),
              ),
          ],
        ),
      ),
    );
  }
}
