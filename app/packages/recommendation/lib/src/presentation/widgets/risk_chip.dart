import 'package:flutter/material.dart';

/// A small chip displaying a risk item with a warning color.
class RiskChip extends StatelessWidget {
  final String risk;

  const RiskChip({super.key, required this.risk});

  @override
  Widget build(BuildContext context) {
    return Chip(
      avatar: const Icon(Icons.warning_amber_rounded, size: 18),
      label: Text(risk),
      backgroundColor: Colors.orange.shade50,
      side: BorderSide(color: Colors.orange.shade200),
      labelStyle: TextStyle(fontSize: 12, color: Colors.orange.shade900),
      visualDensity: VisualDensity.compact,
    );
  }
}
