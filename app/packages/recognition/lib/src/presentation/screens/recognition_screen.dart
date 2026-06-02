import 'package:app_core/app_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../domain/entities/recognition_entity.dart';
import '../providers/recognition_provider.dart';
import '../widgets/attribute_editor.dart';
import '../widgets/suggestion_card_list.dart';

class RecognitionScreen extends ConsumerStatefulWidget {
  const RecognitionScreen({super.key});

  @override
  ConsumerState<RecognitionScreen> createState() => _RecognitionScreenState();
}

class _RecognitionScreenState extends ConsumerState<RecognitionScreen> {
  bool _didResetOnDeactivate = false;

  @override
  void deactivate() {
    if (!_didResetOnDeactivate) {
      ref.read(recognitionProvider.notifier).reset();
      _didResetOnDeactivate = true;
    }
    super.deactivate();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(recognitionProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('识别结果')),
      body: _buildBody(state),
    );
  }

  Widget _buildBody(RecognitionState state) {
    if (state.status == RecognitionStatus.idle) {
      return const _EmptyState();
    }

    if (state.status == RecognitionStatus.loading) {
      return const _LoadingState();
    }

    if (state.status == RecognitionStatus.error && state.recognition == null) {
      return _ErrorState(message: state.error ?? '识别失败，请重试');
    }

    final recognition = state.recognition;
    if (recognition == null) return const SizedBox.shrink();

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(20, 18, 20, 28),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _RecognitionHero(recognition: recognition),
          if (state.error != null) ...[
            const SizedBox(height: 16),
            _InlineError(message: state.error!),
          ],
          const SizedBox(height: 24),
          SuggestionCardList(cards: recognition.suggestionCards),
          if (_hasInsight(recognition)) ...[
            const SizedBox(height: 24),
            _InsightSection(recognition: recognition),
          ],
          if (recognition.attributes.isNotEmpty) ...[
            const SizedBox(height: 24),
            _AttributeDigest(recognition: recognition),
          ],
          const SizedBox(height: 24),
          const AttributeEditor(),
        ],
      ),
    );
  }

  bool _hasInsight(RecognitionEntity recognition) {
    return (recognition.explanation != null &&
            recognition.explanation!.isNotEmpty) ||
        recognition.notices.isNotEmpty;
  }
}

class _RecognitionHero extends StatelessWidget {
  final RecognitionEntity recognition;

  const _RecognitionHero({required this.recognition});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final facts = _coreFacts(recognition);

    return Container(
      decoration: BoxDecoration(
        color: AppColors.panel,
        borderRadius: BorderRadius.circular(8),
        border: const Border(
          left: BorderSide(color: AppColors.accent, width: 4),
          top: BorderSide(color: AppColors.line),
          right: BorderSide(color: AppColors.line),
          bottom: BorderSide(color: AppColors.line),
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withAlpha(18),
            blurRadius: 14,
            offset: const Offset(0, 5),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const _ScanVisual(animated: false),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          const _StatusDot(),
                          const SizedBox(width: 6),
                          Text(
                            '识别完成',
                            style: theme.textTheme.labelMedium?.copyWith(
                              color: AppColors.accent,
                              fontSize: 14,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      Text(
                        recognition.displayName,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.headlineSmall?.copyWith(
                          height: 1.24,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Wrap(
                        spacing: 6,
                        runSpacing: 6,
                        children: [
                          _ConfidenceBadge(confidence: recognition.confidence),
                          _MetaPill(
                            icon: Icons.memory_outlined,
                            label: '识别源 ${recognition.aiProvider}',
                          ),
                          if (recognition.fallbackUsed)
                            const _MetaPill(
                              icon: Icons.alt_route,
                              label: '已回退',
                              tone: _PillTone.warn,
                            ),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          if (facts.isNotEmpty) ...[
            const Divider(height: 1),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 14),
              child: Wrap(
                spacing: 8,
                runSpacing: 8,
                children: facts
                    .map((fact) =>
                        _FactChip(label: fact.label, value: fact.value))
                    .toList(),
              ),
            ),
          ],
          if (recognition.keywords.isNotEmpty) ...[
            const Divider(height: 1),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 14),
              child: _KeywordStrip(keywords: recognition.keywords),
            ),
          ],
        ],
      ),
    );
  }

  List<_Fact> _coreFacts(RecognitionEntity recognition) {
    final facts = <_Fact>[];
    void add(String label, Object? value) {
      final text = _displayValue(value);
      if (text.isNotEmpty && text != '-') {
        facts.add(_Fact(label, text));
      }
    }

    add('类目', recognition.category);
    add('品牌', recognition.brand);
    add('型号', recognition.model);
    for (final entry in recognition.attributes.entries.take(3)) {
      add(entry.key, entry.value);
    }
    return facts.take(6).toList();
  }
}

class _ScanVisual extends StatelessWidget {
  final bool animated;

  const _ScanVisual({this.animated = true});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 78,
      height: 78,
      decoration: BoxDecoration(
        color: AppColors.panelSoft,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.line),
      ),
      child: Stack(
        children: [
          _ScanSweep(animated: animated),
          const Center(
            child: Icon(
              Icons.center_focus_strong,
              size: 34,
              color: AppColors.accent,
            ),
          ),
          Positioned(
              left: 10,
              top: 10,
              child: _ScanCorner(
                  alignment: Alignment.topLeft, animated: animated)),
          Positioned(
              right: 10,
              top: 10,
              child: _ScanCorner(
                  alignment: Alignment.topRight, animated: animated)),
          Positioned(
              left: 10,
              bottom: 10,
              child: _ScanCorner(
                  alignment: Alignment.bottomLeft, animated: animated)),
          Positioned(
              right: 10,
              bottom: 10,
              child: _ScanCorner(
                  alignment: Alignment.bottomRight, animated: animated)),
        ],
      ),
    );
  }
}

class _ScanSweep extends StatefulWidget {
  final bool animated;

  const _ScanSweep({required this.animated});

  @override
  State<_ScanSweep> createState() => _ScanSweepState();
}

class _ScanSweepState extends State<_ScanSweep>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1250),
    );
    if (widget.animated) {
      _controller.repeat();
    } else {
      _controller.value = 0.48;
    }
  }

  @override
  void didUpdateWidget(covariant _ScanSweep oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.animated == widget.animated) return;
    if (widget.animated) {
      _controller.repeat();
    } else {
      _controller.stop();
      _controller.value = 0.48;
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        final progress = widget.animated ? _controller.value : 0.48;
        return Positioned(
          left: 9,
          right: 9,
          top: 13 + progress * 48,
          child: Opacity(
            opacity: widget.animated ? 0.82 : 0.24,
            child: Container(
              height: 2,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(999),
                gradient: LinearGradient(
                  colors: [
                    AppColors.accent.withAlpha(0),
                    AppColors.accent.withAlpha(210),
                    AppColors.signal.withAlpha(150),
                    AppColors.accent.withAlpha(0),
                  ],
                ),
                boxShadow: [
                  BoxShadow(
                    color: AppColors.accent.withAlpha(80),
                    blurRadius: 10,
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

class _ScanCorner extends StatefulWidget {
  final Alignment alignment;
  final bool animated;

  const _ScanCorner({
    required this.alignment,
    this.animated = true,
  });

  @override
  State<_ScanCorner> createState() => _ScanCornerState();
}

class _ScanCornerState extends State<_ScanCorner>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _opacity;
  late final Animation<double> _scale;
  late final Animation<double> _turns;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    );
    _opacity = Tween<double>(begin: 0.46, end: 1).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeInOut),
    );
    _scale = Tween<double>(begin: 0.92, end: 1.1).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeInOut),
    );
    _turns = Tween<double>(begin: -0.015, end: 0.015).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeInOut),
    );
    if (widget.animated) {
      _controller.repeat(reverse: true);
    } else {
      _controller.value = 1;
    }
  }

  @override
  void didUpdateWidget(covariant _ScanCorner oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.animated == widget.animated) return;
    if (widget.animated) {
      _controller.repeat(reverse: true);
    } else {
      _controller.stop();
      _controller.value = 1;
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isLeft = widget.alignment.x < 0;
    final isTop = widget.alignment.y < 0;
    return FadeTransition(
      opacity: _opacity,
      child: RotationTransition(
        turns: _turns,
        child: ScaleTransition(
          scale: _scale,
          child: SizedBox(
            width: 16,
            height: 16,
            child: Stack(
              children: [
                Positioned(
                  left: isLeft ? 0 : null,
                  right: isLeft ? null : 0,
                  top: isTop ? 0 : null,
                  bottom: isTop ? null : 0,
                  child:
                      Container(width: 16, height: 2, color: AppColors.accent),
                ),
                Positioned(
                  left: isLeft ? 0 : null,
                  right: isLeft ? null : 0,
                  top: isTop ? 0 : null,
                  bottom: isTop ? null : 0,
                  child:
                      Container(width: 2, height: 16, color: AppColors.accent),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _StatusDot extends StatelessWidget {
  const _StatusDot();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 8,
      height: 8,
      decoration: BoxDecoration(
        color: AppColors.good,
        borderRadius: BorderRadius.circular(8),
      ),
    );
  }
}

class _ConfidenceBadge extends StatelessWidget {
  final double confidence;

  const _ConfidenceBadge({required this.confidence});

  @override
  Widget build(BuildContext context) {
    final score = (confidence * 100).round().clamp(0, 100).toInt();
    final color = _confidenceColor(confidence);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: color.withAlpha(20),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: color.withAlpha(72)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.verified_outlined, size: 15, color: color),
          const SizedBox(width: 4),
          Text(
            '置信度 $score%',
            style: TextStyle(
              color: color,
              fontSize: 12,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }

  Color _confidenceColor(double value) {
    if (value >= 0.8) return AppColors.good;
    if (value >= 0.5) return AppColors.warn;
    return AppColors.priceRed;
  }
}

enum _PillTone { normal, warn }

class _MetaPill extends StatelessWidget {
  final IconData icon;
  final String label;
  final _PillTone tone;

  const _MetaPill({
    required this.icon,
    required this.label,
    this.tone = _PillTone.normal,
  });

  @override
  Widget build(BuildContext context) {
    final color = tone == _PillTone.warn ? AppColors.warn : AppColors.inkSoft;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: AppColors.panelSoft,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: AppColors.line),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: color),
          const SizedBox(width: 4),
          Text(
            label,
            style: TextStyle(
              color: color,
              fontSize: 12,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }
}

class _FactChip extends StatelessWidget {
  final String label;
  final String value;

  const _FactChip({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(minWidth: 96, maxWidth: 164),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: AppColors.panelSoft,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(label, style: Theme.of(context).textTheme.labelMedium),
          const SizedBox(height: 3),
          Text(
            value,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              color: AppColors.inkMain,
              fontSize: 14,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}

class _KeywordStrip extends StatelessWidget {
  final List<String> keywords;

  const _KeywordStrip({required this.keywords});

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 6,
      runSpacing: 6,
      children: keywords
          .take(8)
          .map(
            (keyword) => Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: AppColors.panelSoft,
                borderRadius: BorderRadius.circular(6),
                border: Border.all(color: AppColors.line),
              ),
              child: Text(
                keyword,
                style: const TextStyle(
                  color: AppColors.inkSoft,
                  fontSize: 12,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
          )
          .toList(),
    );
  }
}

class _InsightSection extends StatelessWidget {
  final RecognitionEntity recognition;

  const _InsightSection({required this.recognition});

  @override
  Widget build(BuildContext context) {
    return _SectionBlock(
      title: '识别判断',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (recognition.explanation != null &&
              recognition.explanation!.isNotEmpty)
            _InsightRow(
              icon: Icons.lightbulb_outline,
              title: '判断依据',
              body: recognition.explanation!,
            ),
          if (recognition.explanation != null &&
              recognition.explanation!.isNotEmpty &&
              recognition.notices.isNotEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 12),
              child: Divider(height: 1),
            ),
          if (recognition.notices.isNotEmpty)
            _NoticeList(notices: recognition.notices),
        ],
      ),
    );
  }
}

class _InsightRow extends StatelessWidget {
  final IconData icon;
  final String title;
  final String body;

  const _InsightRow({
    required this.icon,
    required this.title,
    required this.body,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 18, color: AppColors.signal),
        const SizedBox(width: 9),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: Theme.of(context).textTheme.titleSmall),
              const SizedBox(height: 4),
              Text(body, style: Theme.of(context).textTheme.bodySmall),
            ],
          ),
        ),
      ],
    );
  }
}

class _NoticeList extends StatelessWidget {
  final List<String> notices;

  const _NoticeList({required this.notices});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Icon(Icons.info_outline, size: 17, color: AppColors.warn),
            const SizedBox(width: 8),
            Text('需要确认', style: Theme.of(context).textTheme.titleSmall),
          ],
        ),
        const SizedBox(height: 8),
        ...notices.take(4).map(
              (notice) => Padding(
                padding: const EdgeInsets.only(left: 25, bottom: 5),
                child: Text(
                  notice,
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ),
            ),
      ],
    );
  }
}

class _AttributeDigest extends StatelessWidget {
  final RecognitionEntity recognition;

  const _AttributeDigest({required this.recognition});

  @override
  Widget build(BuildContext context) {
    final entries = recognition.attributes.entries.take(8).toList();
    return _SectionBlock(
      title: '识别细节',
      trailing: Text(
        '${entries.length} 项',
        style: Theme.of(context).textTheme.labelMedium,
      ),
      child: Column(
        children: [
          for (var index = 0; index < entries.length; index++) ...[
            _DetailLine(
              label: entries[index].key,
              value: _displayValue(entries[index].value),
            ),
            if (index != entries.length - 1) const Divider(height: 18),
          ],
        ],
      ),
    );
  }
}

class _DetailLine extends StatelessWidget {
  final String label;
  final String value;

  const _DetailLine({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 92,
          child: Text(label, style: Theme.of(context).textTheme.bodySmall),
        ),
        Expanded(
          child: Text(
            value,
            style: const TextStyle(
              color: AppColors.inkMain,
              fontSize: 14,
              fontWeight: FontWeight.w500,
            ),
          ),
        ),
      ],
    );
  }
}

class _SectionBlock extends StatelessWidget {
  final String title;
  final Widget child;
  final Widget? trailing;

  const _SectionBlock({
    required this.title,
    required this.child,
    this.trailing,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text(title, style: Theme.of(context).textTheme.titleMedium),
            const Spacer(),
            if (trailing != null) trailing!,
          ],
        ),
        const SizedBox(height: 10),
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: AppColors.panelSoft,
            borderRadius: BorderRadius.circular(8),
          ),
          child: child,
        ),
      ],
    );
  }
}

class _InlineError extends StatelessWidget {
  final String message;

  const _InlineError({required this.message});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.priceRed.withAlpha(16),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.priceRed.withAlpha(52)),
      ),
      child: Row(
        children: [
          const Icon(Icons.error_outline, size: 18, color: AppColors.priceRed),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              message,
              style: const TextStyle(color: AppColors.priceRed, fontSize: 13),
            ),
          ),
        ],
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.image_search_outlined,
                size: 42, color: AppColors.inkSoft),
            const SizedBox(height: 12),
            Text('还没有识别结果', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 6),
            Text('请先上传或拍摄商品图', style: Theme.of(context).textTheme.bodySmall),
          ],
        ),
      ),
    );
  }
}

class _LoadingState extends StatelessWidget {
  const _LoadingState();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Container(
        width: 220,
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          color: AppColors.panel,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: AppColors.line),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const _ScanVisual(),
            const SizedBox(height: 14),
            Text('正在识别商品', style: Theme.of(context).textTheme.titleSmall),
            const SizedBox(height: 5),
            Text('解析类目、品牌和关键属性', style: Theme.of(context).textTheme.bodySmall),
          ],
        ),
      ),
    );
  }
}

class _ErrorState extends StatelessWidget {
  final String message;

  const _ErrorState({required this.message});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline,
                size: 42, color: AppColors.priceRed),
            const SizedBox(height: 12),
            Text('识别失败', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 6),
            Text(
              message,
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }
}

class _Fact {
  final String label;
  final String value;

  const _Fact(this.label, this.value);
}

String _displayValue(Object? value) {
  if (value == null) return '';
  if (value is Iterable) {
    return value
        .map((item) => item.toString())
        .where((item) => item.isNotEmpty)
        .join('、');
  }
  final text = value.toString().trim();
  return text;
}
