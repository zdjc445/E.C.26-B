import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/network/api_client.dart';
import '../../core/theme/app_theme.dart';
import '../auth/auth_controller.dart';
import 'price_alert_api.dart';
import 'price_alert_models.dart';

final priceAlertApiProvider = Provider<PriceAlertApi>((ref) {
  return PriceAlertApi(baseUrl: ref.watch(apiBaseUrlProvider));
});

class PriceAlertsScreen extends ConsumerStatefulWidget {
  const PriceAlertsScreen({super.key});

  @override
  ConsumerState<PriceAlertsScreen> createState() => _PriceAlertsScreenState();
}

class _PriceAlertsScreenState extends ConsumerState<PriceAlertsScreen> {
  Future<List<PriceAlertItem>>? _future;
  int _lastTriggered = 0;
  int _lastChecked = 0;

  @override
  void initState() {
    super.initState();
    _load();
  }

  void _load() {
    final api = ref.read(priceAlertApiProvider);
    final token = ref.read(authControllerProvider).session?.token;
    setState(() {
      _future = api.list(token: token);
    });
  }

  Future<void> _check() async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      final api = ref.read(priceAlertApiProvider);
      final token = ref.read(authControllerProvider).session?.token;
      final r = await api.check(token: token);
      setState(() {
        _lastChecked = r.checked;
        _lastTriggered = r.triggered;
      });
      messenger.showSnackBar(SnackBar(
          content: Text('已检测 ${r.checked} 条，触发 ${r.triggered} 条')));
      _load();
    } catch (e) {
      messenger.showSnackBar(SnackBar(content: Text('检测失败：$e')));
    }
  }

  Future<void> _delete(int id) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      final api = ref.read(priceAlertApiProvider);
      final token = ref.read(authControllerProvider).session?.token;
      await api.delete(id, token: token);
      messenger.showSnackBar(const SnackBar(content: Text('已删除提醒')));
      _load();
    } catch (e) {
      messenger.showSnackBar(SnackBar(content: Text('删除失败：$e')));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text('价格提醒'),
        actions: [
          IconButton(
            icon: const Icon(Icons.bolt),
            tooltip: '立即检测',
            onPressed: _check,
          ),
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _load,
          ),
        ],
      ),
      body: Column(
        children: [
          if (_lastChecked > 0)
            Padding(
              padding: const EdgeInsets.all(8),
              child: Text(
                  '上次检测：$_lastChecked 条，触发 $_lastTriggered 条',
                  style: const TextStyle(
                      fontSize: 12, color: AppColors.inkSoft)),
            ),
          Expanded(
            child: FutureBuilder<List<PriceAlertItem>>(
              future: _future,
              builder: (context, snapshot) {
                if (snapshot.connectionState == ConnectionState.waiting) {
                  return const Center(child: CircularProgressIndicator());
                }
                if (snapshot.hasError) {
                  return Center(
                    child: Padding(
                      padding: const EdgeInsets.all(24),
                      child: Text('加载失败：${snapshot.error}',
                          style: const TextStyle(color: AppColors.priceRed)),
                    ),
                  );
                }
                final items = snapshot.data ?? [];
                if (items.isEmpty) {
                  return const Center(
                    child: Text('暂无提醒，长按聊天推荐的商品可创建提醒',
                        style: TextStyle(color: AppColors.inkSoft)),
                  );
                }
                return ListView.separated(
                  padding: const EdgeInsets.all(12),
                  itemCount: items.length,
                  separatorBuilder: (_, __) => const SizedBox(height: 8),
                  itemBuilder: (context, i) {
                    final a = items[i];
                    return Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: AppColors.panel,
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(
                            color: a.triggered
                                ? AppColors.good
                                : AppColors.line),
                      ),
                      child: Row(children: [
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(a.title,
                                  style: const TextStyle(
                                      fontSize: 14,
                                      fontWeight: FontWeight.w600)),
                              const SizedBox(height: 4),
                              Wrap(spacing: 6, runSpacing: 4, children: [
                                _badge(a.platform),
                                _badge('目标 ¥${a.targetPrice.toStringAsFixed(0)}'),
                                if (a.lastObservedPrice != null)
                                  _badge(
                                      '当前 ¥${a.lastObservedPrice!.toStringAsFixed(0)}'),
                                if (a.triggered) _triggeredBadge(),
                              ]),
                              if (a.note != null && a.note!.isNotEmpty) ...[
                                const SizedBox(height: 4),
                                Text(a.note!,
                                    style: const TextStyle(
                                        fontSize: 11,
                                        color: AppColors.inkSoft)),
                              ],
                            ],
                          ),
                        ),
                        IconButton(
                          icon: const Icon(Icons.delete_outline,
                              color: AppColors.priceRed),
                          onPressed: () => _delete(a.id),
                        ),
                      ]),
                    );
                  },
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _badge(String label) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
      decoration: BoxDecoration(
        color: AppColors.background,
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(label,
          style: const TextStyle(fontSize: 11, color: AppColors.inkSoft)),
    );
  }

  Widget _triggeredBadge() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
      decoration: BoxDecoration(
        color: AppColors.good.withAlpha(40),
        borderRadius: BorderRadius.circular(4),
      ),
      child: const Text('已触发',
          style: TextStyle(
              fontSize: 11,
              color: AppColors.good,
              fontWeight: FontWeight.w600)),
    );
  }
}
