import 'dart:math' as math;

import 'package:app_core/app_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../domain/entities/recommendation_entity.dart';
import '../providers/recommendation_provider.dart';
import '../widgets/evidence_card.dart';
import '../widgets/risk_chip.dart';

/// Full-screen recommendation view showing the suggestion, product card,
/// signals, trace, candidates, risks, and evidence.
class RecommendationScreen extends ConsumerStatefulWidget {
  final String searchTaskId;
  final String userQuery;
  final List<String> candidateIds;

  const RecommendationScreen({
    super.key,
    required this.searchTaskId,
    required this.userQuery,
    this.candidateIds = const [],
  });

  @override
  ConsumerState<RecommendationScreen> createState() =>
      _RecommendationScreenState();
}

class _RecommendationScreenState extends ConsumerState<RecommendationScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(recommendationProvider.notifier).createRecommendation(
            searchTaskId: widget.searchTaskId,
            userQuery: widget.userQuery,
            candidateIds: widget.candidateIds,
          );
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(recommendationProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('购买建议')),
      body: state.isLoading
          ? const Center(child: CircularProgressIndicator())
          : state.error != null
              ? _ErrorView(
                  message: state.error!,
                  onRetry: () {
                    ref
                        .read(recommendationProvider.notifier)
                        .createRecommendation(
                          searchTaskId: widget.searchTaskId,
                          userQuery: widget.userQuery,
                          candidateIds: widget.candidateIds,
                        );
                  },
                )
              : state.recommendation != null
                  ? _RecommendationContent(
                      recommendation: state.recommendation!)
                  : const SizedBox.shrink(),
    );
  }
}

class _RecommendationContent extends StatelessWidget {
  final RecommendationEntity recommendation;

  const _RecommendationContent({required this.recommendation});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _SuggestionBadge(
            suggestion: recommendation.suggestion,
            score: recommendation.decisionScore,
          ),
          const SizedBox(height: 18),
          _RecommendedProductCard(
            product: recommendation.recommendedPlatformProduct,
          ),
          if (recommendation.decisionSignals.isNotEmpty) ...[
            const SizedBox(height: 18),
            _SignalPanel(signals: recommendation.decisionSignals),
          ],
          if (recommendation.decisionTrace.isNotEmpty) ...[
            const SizedBox(height: 18),
            _TracePanel(steps: recommendation.decisionTrace),
          ],
          if (recommendation.candidateAnalyses.isNotEmpty) ...[
            const SizedBox(height: 18),
            _CandidateMatrix(candidates: recommendation.candidateAnalyses),
          ],
          const SizedBox(height: 16),
          if (recommendation.reasons.isNotEmpty) ...[
            Text('推荐理由', style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            _ReasonList(reasons: recommendation.reasons),
            const SizedBox(height: 16),
          ],
          if (recommendation.risks.isNotEmpty) ...[
            Text('潜在风险', style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 4,
              children:
                  recommendation.risks.map((r) => RiskChip(risk: r)).toList(),
            ),
            const SizedBox(height: 16),
          ],
          if (recommendation.evidence.isNotEmpty) ...[
            Text('决策依据', style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            ...recommendation.evidence.map(
              (e) => Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: EvidenceCard(evidence: e),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _SuggestionBadge extends StatelessWidget {
  final SuggestionAction suggestion;
  final int score;

  const _SuggestionBadge({required this.suggestion, required this.score});

  @override
  Widget build(BuildContext context) {
    final (Color color, IconData icon, String label) = switch (suggestion) {
      SuggestionAction.buy => (
          AppColors.good,
          Icons.shopping_cart_checkout,
          '建议购买',
        ),
      SuggestionAction.wait => (
          AppColors.warn,
          Icons.hourglass_bottom,
          '建议观望',
        ),
      SuggestionAction.avoid => (
          AppColors.priceRed,
          Icons.block,
          '建议避开',
        ),
      SuggestionAction.compare => (
          AppColors.accent,
          Icons.compare_arrows,
          '建议对比',
        ),
    };
    final theme = Theme.of(context);

    return Container(
      padding: const EdgeInsets.all(20),
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
            blurRadius: 16,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  width: 44,
                  height: 44,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: color.withAlpha(22),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: color.withAlpha(72)),
                  ),
                  child: Icon(icon, color: color, size: 24),
                ),
                const SizedBox(height: 14),
                Text(
                  label,
                  style: theme.textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.w700,
                    color: AppColors.inkMain,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  '由匹配、价格、口碑、渠道和风险信号综合计算',
                  style: theme.textTheme.bodySmall,
                ),
              ],
            ),
          ),
          const SizedBox(width: 16),
          _AnimatedScoreRing(score: score, color: color),
        ],
      ),
    );
  }
}

class _AnimatedScoreRing extends StatefulWidget {
  final int score;
  final Color color;

  const _AnimatedScoreRing({
    required this.score,
    required this.color,
  });

  @override
  State<_AnimatedScoreRing> createState() => _AnimatedScoreRingState();
}

class _AnimatedScoreRingState extends State<_AnimatedScoreRing>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late Animation<double> _score;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 650),
    );
    _score = Tween<double>(
      begin: 0,
      end: widget.score.clamp(0, 100).toDouble(),
    ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeOutCubic));
    _controller.forward();
  }

  @override
  void didUpdateWidget(covariant _AnimatedScoreRing oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.score == widget.score) return;
    _score = Tween<double>(
      begin: _score.value,
      end: widget.score.clamp(0, 100).toDouble(),
    ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeOutCubic));
    _controller
      ..reset()
      ..forward();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _score,
      builder: (context, _) {
        final value = _score.value;
        return SizedBox(
          width: 112,
          height: 112,
          child: CustomPaint(
            painter: _ScoreRingPainter(value: value, color: widget.color),
            child: Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    value.round().toString(),
                    style: const TextStyle(
                      color: AppColors.inkMain,
                      fontSize: 28,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  Text('决策分', style: Theme.of(context).textTheme.labelMedium),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

class _ScoreRingPainter extends CustomPainter {
  final double value;
  final Color color;

  const _ScoreRingPainter({
    required this.value,
    required this.color,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    final center = rect.center;
    final radius = math.min(size.width, size.height) / 2 - 8;
    final background = Paint()
      ..color = AppColors.line
      ..style = PaintingStyle.stroke
      ..strokeWidth = 10
      ..strokeCap = StrokeCap.round;
    final foreground = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 10
      ..strokeCap = StrokeCap.round;
    canvas.drawCircle(center, radius, background);
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      -math.pi / 2,
      math.pi * 2 * (value.clamp(0, 100) / 100),
      false,
      foreground,
    );
  }

  @override
  bool shouldRepaint(covariant _ScoreRingPainter oldDelegate) {
    return oldDelegate.value != value || oldDelegate.color != color;
  }
}

class _SignalPanel extends StatelessWidget {
  final List<RecommendationSignal> signals;

  const _SignalPanel({required this.signals});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          children: signals
              .map(
                (signal) => Padding(
                  padding: const EdgeInsets.symmetric(vertical: 5),
                  child: Row(
                    children: [
                      SizedBox(
                        width: 72,
                        child: Text(signal.label,
                            style: Theme.of(context).textTheme.bodySmall),
                      ),
                      Expanded(
                        child: ClipRRect(
                          borderRadius: BorderRadius.circular(99),
                          child: LinearProgressIndicator(
                            minHeight: 7,
                            value: signal.score.clamp(0, 100) / 100,
                            backgroundColor: const Color(0xFFE4E7EC),
                            color: AppColors.signal,
                          ),
                        ),
                      ),
                      const SizedBox(width: 10),
                      SizedBox(
                        width: 32,
                        child: Text(
                          '${signal.score}',
                          textAlign: TextAlign.right,
                          style: const TextStyle(fontWeight: FontWeight.w800),
                        ),
                      ),
                    ],
                  ),
                ),
              )
              .toList(),
        ),
      ),
    );
  }
}

class _TracePanel extends StatelessWidget {
  final List<RecommendationTraceStep> steps;

  const _TracePanel({required this.steps});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Column(
        children: steps
            .map(
              (step) => Container(
                padding: const EdgeInsets.all(12),
                decoration: const BoxDecoration(
                  border: Border(bottom: BorderSide(color: AppColors.line)),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      width: 9,
                      height: 9,
                      margin: const EdgeInsets.only(top: 5),
                      decoration: BoxDecoration(
                        color: step.status == 'watch'
                            ? AppColors.warn
                            : AppColors.signal,
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(step.label,
                              style:
                                  const TextStyle(fontWeight: FontWeight.w800)),
                          const SizedBox(height: 3),
                          Text(step.observation,
                              style: Theme.of(context).textTheme.bodySmall),
                        ],
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text('${step.confidence}',
                        style: Theme.of(context).textTheme.labelMedium),
                  ],
                ),
              ),
            )
            .toList(),
      ),
    );
  }
}

class _CandidateMatrix extends StatelessWidget {
  final List<RecommendationCandidateAnalysis> candidates;

  const _CandidateMatrix({required this.candidates});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('候选矩阵', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        ...candidates.take(3).map((candidate) => Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Card(
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Text('#${candidate.rank}',
                              style: Theme.of(context).textTheme.labelMedium),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              candidate.title,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style:
                                  const TextStyle(fontWeight: FontWeight.w800),
                            ),
                          ),
                          Text('${candidate.decisionScore}',
                              style:
                                  const TextStyle(fontWeight: FontWeight.w900)),
                        ],
                      ),
                      const SizedBox(height: 8),
                      Wrap(
                        spacing: 6,
                        runSpacing: 6,
                        children: [
                          ...candidate.strengths.take(2).map((text) =>
                              _SmallPill(text: text, color: AppColors.good)),
                          ...candidate.weaknesses.take(1).map((text) =>
                              _SmallPill(text: text, color: AppColors.warn)),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            )),
      ],
    );
  }
}

class _ReasonList extends StatelessWidget {
  final List<String> reasons;

  const _ReasonList({required this.reasons});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          children: reasons
              .take(5)
              .map(
                (reason) => Padding(
                  padding: const EdgeInsets.symmetric(vertical: 5),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Icon(Icons.check, size: 17, color: AppColors.good),
                      const SizedBox(width: 8),
                      Expanded(
                          child: Text(reason,
                              style: Theme.of(context).textTheme.bodyMedium)),
                    ],
                  ),
                ),
              )
              .toList(),
        ),
      ),
    );
  }
}

class _SmallPill extends StatelessWidget {
  final String text;
  final Color color;

  const _SmallPill({required this.text, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 4),
      decoration: BoxDecoration(
        color: color.withAlpha(18),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: color.withAlpha(60)),
      ),
      child: Text(
        text,
        style:
            TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w700),
      ),
    );
  }
}

class _RecommendedProductCard extends StatelessWidget {
  final RecommendedPlatformProduct product;

  const _RecommendedProductCard({required this.product});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text('推荐商品',
                    style: theme.textTheme.titleSmall
                        ?.copyWith(fontWeight: FontWeight.bold)),
                const Spacer(),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: AppColors.panelSoft,
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: AppColors.line),
                  ),
                  child: Text(
                    '${(product.matchScore * 100).toStringAsFixed(0)}% 匹配',
                    style: theme.textTheme.labelMedium,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(product.title, style: theme.textTheme.bodyLarge),
            const SizedBox(height: 8),
            Row(
              children: [
                Text(product.platform,
                    style: theme.textTheme.bodySmall
                        ?.copyWith(color: theme.colorScheme.primary)),
                const Spacer(),
                Text(
                  '${product.price.currency} ${product.price.amount}',
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: AppColors.priceRed,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _ErrorView extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;

  const _ErrorView({required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.error_outline,
                size: 48, color: Theme.of(context).colorScheme.error),
            const SizedBox(height: 16),
            Text(message, textAlign: TextAlign.center),
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: const Text('重试'),
            ),
          ],
        ),
      ),
    );
  }
}
