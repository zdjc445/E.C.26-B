import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:app_core/app_core.dart';
import 'package:go_router/go_router.dart';
import '../../domain/entities/product_entity.dart';
import '../providers/search_provider.dart';
import '../widgets/product_grid.dart';
import '../widgets/sort_tab_bar.dart';
import '../widgets/filter_chip_bar.dart';
import '../widgets/source_type_selector.dart';
import '../widgets/platform_selector.dart';

/// Full-screen search results with sort bar, filter chips, source/platform selectors,
/// product grid, and a natural-language refine input at the bottom.
class SearchResultsScreen extends ConsumerStatefulWidget {
  /// Optional imageId from a prior image upload flow to auto-trigger search.
  final String? initialImageId;
  final ProductActionHandler? onProductAction;

  const SearchResultsScreen({
    super.key,
    this.initialImageId,
    this.onProductAction,
  });

  @override
  ConsumerState<SearchResultsScreen> createState() =>
      _SearchResultsScreenState();
}

class _SearchResultsScreenState extends ConsumerState<SearchResultsScreen> {
  final TextEditingController _refineController = TextEditingController();
  final TextEditingController _searchController = TextEditingController();
  final FocusNode _refineFocus = FocusNode();

  @override
  void initState() {
    super.initState();
    if (widget.initialImageId != null && widget.initialImageId!.isNotEmpty) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        ref
            .read(searchProvider.notifier)
            .search(recognitionId: widget.initialImageId);
      });
    }
  }

  @override
  void dispose() {
    _refineController.dispose();
    _searchController.dispose();
    _refineFocus.dispose();
    ref.read(searchProvider.notifier).reset();
    super.dispose();
  }

  void _onSearch() {
    final query = _searchController.text.trim();
    if (query.isEmpty) return;
    ref.read(searchProvider.notifier).search(query: query);
    _refineController.clear();
  }

  void _onRefine() {
    final text = _refineController.text.trim();
    if (text.isEmpty) return;
    ref.read(searchProvider.notifier).refine(text);
    _refineController.clear();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(searchProvider);
    final isLoading = state.status == SearchStatus.searching ||
        state.status == SearchStatus.refining;

    return Scaffold(
      appBar: AppBar(
        title: const Text('商品搜索'),
        actions: [
          if (state.status == SearchStatus.idle)
            IconButton(
              icon: const Icon(Icons.history),
              tooltip: '搜索历史',
              onPressed: () => _showHistorySheet(context),
            ),
        ],
      ),
      body: Column(
        children: [
          if (state.status == SearchStatus.idle) _buildSearchBar(context),
          if (state.status == SearchStatus.searching ||
              state.status == SearchStatus.loaded ||
              state.status == SearchStatus.refining ||
              state.status == SearchStatus.error)
            _buildActiveSearchHeader(state, isLoading),
          if (state.status == SearchStatus.loaded ||
              state.status == SearchStatus.searching)
            SortTabBar(
              selected: state.currentSort,
              onChanged: (sort) =>
                  ref.read(searchProvider.notifier).setSort(sort),
            ),
          FilterChipBar(
            filters: state.activeFilters,
            onClearAll: () => ref.read(searchProvider.notifier).clearFilters(),
          ),
          if (state.status == SearchStatus.loaded ||
              state.status == SearchStatus.idle)
            SourceTypeSelector(
              selected: state.currentSourceType,
              onChanged: (type) =>
                  ref.read(searchProvider.notifier).setSourceType(type),
            ),
          PlatformSelector(
            selectedPlatforms: state.activePlatforms,
            onToggle: (p) =>
                ref.read(searchProvider.notifier).togglePlatform(p),
          ),
          if (state.status == SearchStatus.loaded)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
              child: Row(
                children: [
                  Text(
                    '共 ${state.totalResults} 个结果',
                    style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                  ),
                  const Spacer(),
                  if (state.currentTask?.recognitionId != null)
                    const Chip(
                      avatar: Icon(Icons.image_search, size: 14),
                      label: Text('图片识别', style: TextStyle(fontSize: 10)),
                      visualDensity: VisualDensity.compact,
                      materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    ),
                ],
              ),
            ),
          const Divider(height: 1),
          Expanded(
            child: CustomScrollView(
              slivers: [
                ProductGrid(
                  products: state.products,
                  isLoading: isLoading,
                  emptyMessage: state.status == SearchStatus.error
                      ? state.error ?? '搜索失败'
                      : null,
                  onProductTap: (product) =>
                      _handleProductTap(context, product, state),
                ),
              ],
            ),
          ),
          if (state.error != null &&
              state.status != SearchStatus.idle &&
              state.products.isNotEmpty)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              color: Colors.red.shade50,
              child: Row(
                children: [
                  Icon(Icons.error_outline,
                      size: 16, color: Colors.red.shade700),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      state.error!,
                      style:
                          TextStyle(fontSize: 12, color: Colors.red.shade700),
                    ),
                  ),
                ],
              ),
            ),
          if (state.status == SearchStatus.loaded)
            _buildRefineBar(context, isLoading),
        ],
      ),
    );
  }

  Future<void> _handleProductTap(
    BuildContext context,
    ProductEntity product,
    SearchState state,
  ) async {
    if (widget.onProductAction != null) {
      await widget.onProductAction!(context, product, state);
      return;
    }
    if (!context.mounted) return;
    await _showDefaultProductSheet(context, product, state);
  }

  Future<void> _showDefaultProductSheet(
    BuildContext context,
    ProductEntity product,
    SearchState state,
  ) {
    final taskId = state.currentTask?.taskId ?? '';
    final candidateIds = state.products
        .map((p) => p.productId)
        .where((id) => id.isNotEmpty)
        .take(3)
        .toList();

    return showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (sheetContext) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.insights_outlined),
              title: const Text('商品洞察'),
              subtitle: Text(product.title,
                  maxLines: 1, overflow: TextOverflow.ellipsis),
              onTap: () {
                Navigator.of(sheetContext).pop();
                context.push('/inspection/${product.productId}');
              },
            ),
            ListTile(
              leading: const Icon(Icons.compare_arrows),
              title: const Text('进入比价'),
              onTap: taskId.isEmpty
                  ? null
                  : () {
                      Navigator.of(sheetContext).pop();
                      context.push('/comparison', extra: {
                        'searchTaskId': taskId,
                        'platformProductIds': candidateIds,
                      });
                    },
            ),
            ListTile(
              leading: const Icon(Icons.auto_awesome_outlined),
              title: const Text('生成推荐'),
              onTap: taskId.isEmpty
                  ? null
                  : () {
                      Navigator.of(sheetContext).pop();
                      context.push('/recommendation', extra: {
                        'searchTaskId': taskId,
                        'userQuery': state.currentTask?.query ?? '',
                        'candidateIds': candidateIds,
                      });
                    },
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSearchBar(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 10),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: _searchController,
              decoration: InputDecoration(
                hintText: '输入商品名称或关键词',
                prefixIcon: const Icon(Icons.search),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(8),
                ),
                contentPadding: const EdgeInsets.symmetric(vertical: 10),
                isDense: true,
              ),
              textInputAction: TextInputAction.search,
              onSubmitted: (_) => _onSearch(),
            ),
          ),
          const SizedBox(width: 8),
          FilledButton.icon(
            onPressed: _onSearch,
            icon: const Icon(Icons.search, size: 18),
            label: const Text('搜索'),
          ),
        ],
      ),
    );
  }

  Widget _buildActiveSearchHeader(SearchState state, bool isLoading) {
    final query = state.currentTask?.query;
    if (query == null || query.isEmpty) return const SizedBox.shrink();

    return Container(
      margin: const EdgeInsets.fromLTRB(16, 12, 16, 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.panel,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.line),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('当前需求', style: Theme.of(context).textTheme.labelMedium),
                const SizedBox(height: 4),
                Text(
                  query,
                  style: const TextStyle(fontWeight: FontWeight.w800),
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
          if (isLoading)
            const SizedBox(width: 12, child: LinearProgressIndicator()),
        ],
      ),
    );
  }

  Widget _buildRefineBar(BuildContext context, bool isLoading) {
    return SafeArea(
      child: Container(
        padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surface,
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.05),
              blurRadius: 4,
              offset: const Offset(0, -2),
            ),
          ],
        ),
        child: Row(
          children: [
            Expanded(
              child: TextField(
                controller: _refineController,
                focusNode: _refineFocus,
                decoration: InputDecoration(
                  hintText: '用自然语言进一步描述需求...',
                  prefixIcon: const Icon(Icons.tune, size: 20),
                  suffixIcon: IconButton(
                    icon: const Icon(Icons.send, size: 20),
                    onPressed: _onRefine,
                  ),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(8),
                  ),
                  contentPadding:
                      const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                  isDense: true,
                ),
                textInputAction: TextInputAction.send,
                onSubmitted: (_) => _onRefine(),
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _showHistorySheet(BuildContext context) {
    ref.read(searchProvider.notifier).loadHistory();

    showModalBottomSheet(
      context: context,
      builder: (_) {
        return DraggableScrollableSheet(
          expand: false,
          initialChildSize: 0.5,
          builder: (context, scrollController) {
            final state = ref.watch(searchProvider);
            if (state.history.isEmpty) {
              return const Center(child: Text('暂无搜索历史'));
            }
            return ListView.separated(
              controller: scrollController,
              padding: const EdgeInsets.all(16),
              itemCount: state.history.length,
              separatorBuilder: (_, __) => const Divider(height: 1),
              itemBuilder: (context, index) {
                final task = state.history[index];
                return ListTile(
                  leading: const Icon(Icons.history),
                  title: Text(
                    task.query ?? '图片搜索',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  subtitle: Text(
                    '${task.totalResults} 个结果  |  ${_formatDate(task.createdAt)}',
                    style: const TextStyle(fontSize: 12),
                  ),
                  trailing: Text(
                    task.status == 'completed' ? '已完成' : task.status,
                    style: TextStyle(fontSize: 11, color: Colors.grey.shade600),
                  ),
                  onTap: () {
                    Navigator.of(context).pop();
                    ref.read(searchProvider.notifier).search(
                          recognitionId: task.recognitionId,
                          query: task.query,
                        );
                  },
                );
              },
            );
          },
        );
      },
    );
  }

  String _formatDate(DateTime dt) {
    return '${dt.year}-${dt.month.toString().padLeft(2, '0')}-${dt.day.toString().padLeft(2, '0')} '
        '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
  }
}

typedef ProductActionHandler = Future<void> Function(
  BuildContext context,
  ProductEntity product,
  SearchState state,
);
