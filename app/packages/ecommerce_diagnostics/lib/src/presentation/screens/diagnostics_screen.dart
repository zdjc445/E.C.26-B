import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:app_core/app_core.dart';
import '../providers/ecommerce_provider.dart';
import '../widgets/platform_status_pill.dart';
import '../widgets/diagnostics_card.dart';

/// Screen displaying e-commerce status and diagnostics results.
class DiagnosticsScreen extends ConsumerStatefulWidget {
  const DiagnosticsScreen({super.key});

  @override
  ConsumerState<DiagnosticsScreen> createState() => _DiagnosticsScreenState();
}

class _DiagnosticsScreenState extends ConsumerState<DiagnosticsScreen> {
  final _queryController = TextEditingController();
  String? _selectedPlatform;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(ecommerceProvider.notifier).loadStatus();
    });
  }

  @override
  void dispose() {
    _queryController.dispose();
    super.dispose();
  }

  Future<void> _runDiagnostics() async {
    await ref.read(ecommerceProvider.notifier).runDiagnostics(
          query: _queryController.text.trim(),
          platforms: _selectedPlatform,
        );
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(ecommerceProvider);
    final theme = Theme.of(context);

    ref.listen(ecommerceProvider, (prev, next) {
      if (next.error != null && next.error != prev?.error) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(next.error!),
            backgroundColor: AppColors.priceRed,
            action: SnackBarAction(
              label: '重试',
              textColor: Colors.white,
              onPressed: () =>
                  ref.read(ecommerceProvider.notifier).loadStatus(),
            ),
          ),
        );
        ref.read(ecommerceProvider.notifier).clearError();
      }
    });

    return Scaffold(
      appBar: AppBar(
        title: const Text('电商诊断'),
      ),
      body: RefreshIndicator(
        onRefresh: () => ref.read(ecommerceProvider.notifier).loadStatus(),
        child: ListView(
          padding: const EdgeInsets.symmetric(vertical: 16),
          children: [
            // ── Section: Status ─────────────────────────────
            const _SectionHeader(title: '平台状态'),
            const SizedBox(height: 8),
            if (state.status == EcommerceLoadStatus.loading)
              const Padding(
                padding: EdgeInsets.all(24),
                child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
              )
            else if (state.status == EcommerceLoadStatus.error)
              _buildErrorCard(theme)
            else if (state.statusData != null) ...[
              // Overall status
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Row(
                  children: [
                    _OverallStatusChip(
                      label: '电商功能',
                      enabled: state.statusData!.enabled,
                    ),
                    const SizedBox(width: 12),
                    _OverallStatusChip(
                      label: '已配置客户端',
                      enabled: state.statusData!.hasConfiguredClient,
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 12),
              // Platform pills
              if (state.statusData!.providers.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: state.statusData!.providers
                        .map((p) => PlatformStatusPill(status: p))
                        .toList(),
                  ),
                )
              else
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: Text(
                    '暂无平台数据',
                    style: theme.textTheme.bodySmall,
                  ),
                ),
            ] else
              const SizedBox.shrink(),

            const SizedBox(height: 24),
            const Divider(indent: 16, endIndent: 16),
            const SizedBox(height: 8),

            // ── Section: Diagnostics ────────────────────────
            const _SectionHeader(title: '运行诊断'),
            const SizedBox(height: 12),

            // Query input
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: TextField(
                controller: _queryController,
                decoration: const InputDecoration(
                  hintText: '搜索关键词 (可选)',
                  prefixIcon: Icon(Icons.search, size: 18),
                ),
              ),
            ),
            const SizedBox(height: 12),

            // Platform selector
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: DropdownButtonFormField<String?>(
                value: _selectedPlatform,
                decoration: const InputDecoration(
                  hintText: '选择平台 (全部)',
                  contentPadding:
                      EdgeInsets.symmetric(horizontal: 10, vertical: 9),
                ),
                items: const [
                  DropdownMenuItem(value: null, child: Text('全部平台')),
                  DropdownMenuItem(value: 'jd', child: Text('京东')),
                  DropdownMenuItem(value: 'taobao', child: Text('淘宝')),
                  DropdownMenuItem(value: 'pdd', child: Text('拼多多')),
                  DropdownMenuItem(value: 'tmall', child: Text('天猫')),
                ],
                onChanged: (v) => setState(() => _selectedPlatform = v),
              ),
            ),
            const SizedBox(height: 12),

            // Run button
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  onPressed: state.diagnosticsRunning ? null : _runDiagnostics,
                  icon: state.diagnosticsRunning
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(
                              strokeWidth: 2, color: Colors.white),
                        )
                      : const Icon(Icons.play_arrow, size: 18),
                  label: Text(state.diagnosticsRunning ? '诊断中...' : '运行诊断'),
                ),
              ),
            ),
            const SizedBox(height: 16),

            // Diagnostics results
            if (state.diagnosticsError != null) ...[
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: AppColors.priceRed.withAlpha(15),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: AppColors.priceRed.withAlpha(50)),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.error_outline,
                          color: AppColors.priceRed),
                      const SizedBox(width: 8),
                      Expanded(
                          child: Text(state.diagnosticsError!,
                              style:
                                  const TextStyle(color: AppColors.priceRed))),
                    ],
                  ),
                ),
              ),
            ] else if (state.diagnosticsData != null) ...[
              // Checked at
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Text(
                  '查询: "${state.diagnosticsData!.query}" | '
                  '检查时间: ${_formatDateTime(state.diagnosticsData!.checkedAt)}',
                  style: theme.textTheme.bodySmall,
                ),
              ),
              const SizedBox(height: 12),
              // Provider cards
              ...state.diagnosticsData!.providers.map(
                (diag) => DiagnosticsCard(diagnostic: diag),
              ),
              if (state.diagnosticsData!.providers.isEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: Text('暂无诊断结果', style: theme.textTheme.bodySmall),
                ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildErrorCard(ThemeData theme) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Center(
            child: Column(
              children: [
                const Icon(Icons.cloud_off, size: 48, color: AppColors.inkSoft),
                const SizedBox(height: 8),
                Text('无法获取状态', style: theme.textTheme.bodySmall),
                const SizedBox(height: 12),
                OutlinedButton(
                  onPressed: () =>
                      ref.read(ecommerceProvider.notifier).loadStatus(),
                  child: const Text('重试'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  String _formatDateTime(DateTime dt) {
    return '${dt.year}-${dt.month.toString().padLeft(2, '0')}-${dt.day.toString().padLeft(2, '0')} '
        '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
  }
}

class _SectionHeader extends StatelessWidget {
  final String title;
  const _SectionHeader({required this.title});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Text(
        title,
        style: Theme.of(context).textTheme.titleMedium,
      ),
    );
  }
}

class _OverallStatusChip extends StatelessWidget {
  final String label;
  final bool enabled;

  const _OverallStatusChip({required this.label, required this.enabled});

  @override
  Widget build(BuildContext context) {
    final color = enabled ? AppColors.good : AppColors.inkSoft;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: color.withAlpha(30),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withAlpha(80)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(label,
              style: const TextStyle(fontSize: 12, color: AppColors.inkMain)),
          const SizedBox(width: 6),
          Icon(
            enabled ? Icons.check_circle : Icons.cancel,
            size: 14,
            color: color,
          ),
        ],
      ),
    );
  }
}
