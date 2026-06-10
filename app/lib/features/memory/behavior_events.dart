import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'memory_store.dart';

/// Unified behavior event recorder.
///
/// All user actions (search, view, click, favorite, etc.) flow through this
/// module so event recording is consistent and not scattered across pages.
final behaviorRecorderProvider = Provider<BehaviorRecorder>((ref) {
  return BehaviorRecorder(ref.watch(memoryStoreProvider));
});

/// Event types matching the defined taxonomy.
enum BehaviorEventType {
  search,
  productView,
  productClick,
  favorite,
  unfavorite,
  platformJump,
  priceAlertCreate,
  filterApply,
  preferenceUpdate,
}

class BehaviorRecorder {
  final MemoryStore _store;
  BehaviorRecorder(this._store);

  /// Record a single event. Fields auto-filled where possible.
  Future<void> record(BehaviorEventType type, {
    String? query,
    String? productId,
    String? category,
    String? brand,
    double? price,
    String? platform,
    List<String>? tags,
    Map<String, String>? filters,
    String? optionId,
  }) async {
    final events = await _store.loadEvents();
    events.add({
      'userId': 'demo',           // future: use real user id
      'type': type.name,
      'timestamp': DateTime.now().toIso8601String(),
      if (query != null) 'query': query,
      if (productId != null) 'productId': productId,
      if (category != null) 'category': category,
      if (brand != null) 'brand': brand,
      if (price != null) 'price': price,
      if (platform != null) 'platform': platform,
      if (tags != null) 'tags': tags,
      if (filters != null) 'filters': filters,
      if (optionId != null) 'optionId': optionId,
    });
    await _store.saveEvents(events);
  }

  /// Load all events for the current user.
  Future<List<Map<String, dynamic>>> loadAll() => _store.loadEvents();

  /// Count events of a given type.
  Future<int> count(BehaviorEventType type) async {
    final events = await _store.loadEvents();
    return events.where((e) => e['type'] == type.name).length;
  }
}
