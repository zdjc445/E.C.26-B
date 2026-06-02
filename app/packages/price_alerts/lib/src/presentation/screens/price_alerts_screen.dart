import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:app_core/app_core.dart';
import '../providers/price_alert_provider.dart';
import '../widgets/price_alert_card.dart';

/// Screen displaying the user's price alerts with create/edit dialog support.
class PriceAlertsScreen extends ConsumerStatefulWidget {
  const PriceAlertsScreen({super.key});

  @override
  ConsumerState<PriceAlertsScreen> createState() => _PriceAlertsScreenState();
}

class _PriceAlertsScreenState extends ConsumerState<PriceAlertsScreen> {
  final _scrollController = ScrollController();

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScroll);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(priceAlertProvider.notifier).loadAlerts();
    });
  }

  void _onScroll() {
    if (_scrollController.position.pixels >=
        _scrollController.position.maxScrollExtent - 200) {
      ref.read(priceAlertProvider.notifier).loadMore();
    }
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  // ── Dialog helpers ────────────────────────────────────────

  Future<void> _showCreateDialog() async {
    final result = await showDialog<_AlertFormResult>(
      context: context,
      builder: (_) => const _AlertFormDialog(),
    );
    if (result != null && mounted) {
      await ref.read(priceAlertProvider.notifier).createAlert(
            platformProductId: result.platformProductId,
            targetPrice: result.targetPrice,
            enabled: result.enabled,
          );
      _showActionResult();
    }
  }

  Future<void> _showEditDialog(String alertId) async {
    final state = ref.read(priceAlertProvider);
    final alert = state.alerts.firstWhere((a) => a.priceAlertId == alertId);
    final result = await showDialog<_AlertFormResult>(
      context: context,
      builder: (_) => _AlertFormDialog(
        initialPrice: alert.targetPrice,
        initialEnabled: alert.enabled,
        isEdit: true,
      ),
    );
    if (result != null && mounted) {
      await ref.read(priceAlertProvider.notifier).updateAlert(
            priceAlertId: alertId,
            targetPrice: result.targetPrice,
            enabled: result.enabled,
          );
      _showActionResult();
    }
  }

  void _showActionResult() {
    final state = ref.read(priceAlertProvider);
    if (state.actionError != null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(state.actionError!),
          backgroundColor: AppColors.priceRed,
        ),
      );
      ref.read(priceAlertProvider.notifier).clearActionError();
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(priceAlertProvider);
    final theme = Theme.of(context);

    ref.listen(priceAlertProvider, (prev, next) {
      if (next.error != null && next.error != prev?.error) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(next.error!),
            backgroundColor: AppColors.priceRed,
            action: SnackBarAction(
              label: '重试',
              textColor: Colors.white,
              onPressed: () =>
                  ref.read(priceAlertProvider.notifier).loadAlerts(),
            ),
          ),
        );
        ref.read(priceAlertProvider.notifier).clearError();
      }
    });

    return Scaffold(
      appBar: AppBar(
        title: const Text('价格提醒'),
        actions: [
          if (state.alerts.isNotEmpty)
            Text('共 ${state.total} 条', style: theme.textTheme.bodySmall),
          const SizedBox(width: 16),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _showCreateDialog,
        icon: const Icon(Icons.add, size: 20),
        label: const Text('新建提醒'),
      ),
      body: _buildBody(state, theme),
    );
  }

  Widget _buildBody(PriceAlertsState state, ThemeData theme) {
    switch (state.status) {
      case AlertsLoadStatus.initial:
      case AlertsLoadStatus.loading:
        if (state.alerts.isEmpty) {
          return const Center(child: CircularProgressIndicator());
        }
        return _buildList(state, theme);

      case AlertsLoadStatus.error:
        if (state.alerts.isEmpty) {
          return _buildError(theme);
        }
        return _buildList(state, theme);

      case AlertsLoadStatus.empty:
        return _buildEmpty(theme);

      case AlertsLoadStatus.loaded:
        return _buildList(state, theme);
    }
  }

  Widget _buildList(PriceAlertsState state, ThemeData theme) {
    return RefreshIndicator(
      onRefresh: () => ref.read(priceAlertProvider.notifier).loadAlerts(),
      child: ListView.builder(
        controller: _scrollController,
        padding: const EdgeInsets.only(top: 8, bottom: 80),
        itemCount: state.alerts.length + (state.hasMore ? 1 : 0),
        itemBuilder: (context, index) {
          if (index >= state.alerts.length) {
            return const Padding(
              padding: EdgeInsets.all(16),
              child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
            );
          }
          final alert = state.alerts[index];
          return PriceAlertCard(
            alert: alert,
            onToggleEnabled: () {
              ref.read(priceAlertProvider.notifier).updateAlert(
                    priceAlertId: alert.priceAlertId,
                    enabled: !alert.enabled,
                  );
            },
            onEdit: () => _showEditDialog(alert.priceAlertId),
            onDelete: () {
              ref
                  .read(priceAlertProvider.notifier)
                  .deleteAlert(alert.priceAlertId);
            },
            onTap: () {
              // Navigate to product detail.
            },
          );
        },
      ),
    );
  }

  Widget _buildEmpty(ThemeData theme) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.notifications_none,
              size: 64, color: AppColors.inkSoft),
          const SizedBox(height: 16),
          Text(
            '还没有设置价格提醒',
            style: theme.textTheme.titleMedium?.copyWith(
              color: AppColors.inkSoft,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            '设置目标价格，降价时自动通知您',
            style: theme.textTheme.bodySmall,
          ),
          const SizedBox(height: 24),
          ElevatedButton.icon(
            onPressed: _showCreateDialog,
            icon: const Icon(Icons.add, size: 18),
            label: const Text('新建提醒'),
          ),
        ],
      ),
    );
  }

  Widget _buildError(ThemeData theme) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.error_outline, size: 64, color: AppColors.inkSoft),
          const SizedBox(height: 16),
          Text(
            '加载失败，请重试',
            style: theme.textTheme.titleMedium?.copyWith(
              color: AppColors.inkSoft,
            ),
          ),
          const SizedBox(height: 16),
          ElevatedButton.icon(
            onPressed: () => ref.read(priceAlertProvider.notifier).loadAlerts(),
            icon: const Icon(Icons.refresh, size: 18),
            label: const Text('重试'),
          ),
        ],
      ),
    );
  }
}

// ── Form dialog for create / edit ──────────────────────────

class _AlertFormResult {
  final String platformProductId;
  final Money targetPrice;
  final bool enabled;
  const _AlertFormResult({
    required this.platformProductId,
    required this.targetPrice,
    required this.enabled,
  });
}

class _AlertFormDialog extends StatefulWidget {
  final Money? initialPrice;
  final bool initialEnabled;
  final bool isEdit;

  const _AlertFormDialog({
    this.initialPrice,
    this.initialEnabled = true,
    this.isEdit = false,
  });

  @override
  State<_AlertFormDialog> createState() => _AlertFormDialogState();
}

class _AlertFormDialogState extends State<_AlertFormDialog> {
  late final TextEditingController _productIdCtrl;
  late final TextEditingController _priceCtrl;
  late bool _enabled;

  final _formKey = GlobalKey<FormState>();

  @override
  void initState() {
    super.initState();
    _productIdCtrl = TextEditingController();
    _priceCtrl = TextEditingController(
      text: widget.initialPrice?.amount ?? '',
    );
    _enabled = widget.initialEnabled;
  }

  @override
  void dispose() {
    _productIdCtrl.dispose();
    _priceCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return AlertDialog(
      title: Text(widget.isEdit ? '编辑价格提醒' : '新建价格提醒'),
      content: Form(
        key: _formKey,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (!widget.isEdit) ...[
              Text('商品 ID', style: theme.textTheme.bodySmall),
              const SizedBox(height: 4),
              TextFormField(
                controller: _productIdCtrl,
                decoration: const InputDecoration(
                  hintText: '请输入平台商品 ID',
                ),
                validator: (v) =>
                    (v == null || v.trim().isEmpty) ? '商品 ID 不能为空' : null,
              ),
              const SizedBox(height: 16),
            ],
            Text('目标价格', style: theme.textTheme.bodySmall),
            const SizedBox(height: 4),
            TextFormField(
              controller: _priceCtrl,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(
                hintText: '0.00',
                suffixText: 'CNY',
              ),
              validator: (v) {
                if (v == null || v.trim().isEmpty) return '请输入目标价格';
                final amount = double.tryParse(v.trim());
                if (amount == null || amount <= 0) return '价格必须大于 0';
                return null;
              },
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Text('启用提醒', style: theme.textTheme.bodySmall),
                const Spacer(),
                Switch(
                  value: _enabled,
                  onChanged: (v) => setState(() => _enabled = v),
                ),
              ],
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('取消'),
        ),
        ElevatedButton(
          onPressed: _submit,
          child: Text(widget.isEdit ? '保存' : '创建'),
        ),
      ],
    );
  }

  void _submit() {
    if (!_formKey.currentState!.validate()) return;

    final price = Money(
      amount: _priceCtrl.text.trim(),
      currency: 'CNY',
    );

    Navigator.pop(
      context,
      _AlertFormResult(
        platformProductId: _productIdCtrl.text.trim(),
        targetPrice: price,
        enabled: _enabled,
      ),
    );
  }
}
