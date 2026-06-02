import '../../domain/entities/search_task_entity.dart';

/// In-memory cache for search results.
/// Production replacement: Drift (SQLite) with build_runner codegen.
class SearchLocalCache {
  final Map<String, SearchTaskEntity> _tasks = {};
  final List<String> _historyOrder = [];
  final int _maxHistorySize = 50;

  /// Cache a search task result.
  void cacheTask(SearchTaskEntity task) {
    _tasks[task.taskId] = task;
    _historyOrder.remove(task.taskId);
    _historyOrder.insert(0, task.taskId);
    _trimHistory();
  }

  /// Retrieve a cached task by ID, or null if not found.
  SearchTaskEntity? getTask(String taskId) => _tasks[taskId];

  /// Get cached search history (most recent first).
  List<SearchTaskEntity> getHistory({int page = 1, int pageSize = 20}) {
    final start = (page - 1) * pageSize;
    if (start >= _historyOrder.length) return [];

    final end = (start + pageSize).clamp(0, _historyOrder.length);
    return _historyOrder
        .sublist(start, end)
        .map((id) => _tasks[id])
        .whereType<SearchTaskEntity>()
        .toList();
  }

  /// Check whether the cache has a recent entry for the given task ID.
  bool hasTask(String taskId) => _tasks.containsKey(taskId);

  /// Clear all cached data.
  void clear() {
    _tasks.clear();
    _historyOrder.clear();
  }

  void _trimHistory() {
    while (_historyOrder.length > _maxHistorySize) {
      final removed = _historyOrder.removeLast();
      _tasks.remove(removed);
    }
  }
}
