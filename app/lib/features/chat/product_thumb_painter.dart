import 'dart:math' as math;

import 'package:flutter/material.dart';

class ProductThumbPainter extends CustomPainter {
  final IconData icon;
  final Color accent;
  final Color lineColor;
  final String text;

  const ProductThumbPainter({
    required this.icon,
    required this.accent,
    required this.lineColor,
    required this.text,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final softPaint = Paint()
      ..color = accent.withAlpha(18)
      ..style = PaintingStyle.fill;
    canvas.drawCircle(Offset(size.width * 0.68, size.height * 0.28),
        size.width * 0.28, softPaint);
    canvas.drawCircle(Offset(size.width * 0.28, size.height * 0.78),
        size.width * 0.18, softPaint);

    if (text.contains('耳机')) {
      _paintHeadphones(canvas, size);
    } else if (text.contains('鞋')) {
      _paintShoe(canvas, size);
    } else if (text.contains('吹风机')) {
      _paintHairDryer(canvas, size);
    } else if (text.contains('背包') || text.contains('双肩')) {
      _paintBag(canvas, size);
    } else if (text.contains('手表')) {
      _paintWatch(canvas, size);
    } else {
      _paintIcon(canvas, size);
    }
  }

  void _paintHeadphones(Canvas canvas, Size size) {
    final stroke = Paint()
      ..color = accent
      ..style = PaintingStyle.stroke
      ..strokeWidth = 4
      ..strokeCap = StrokeCap.round;
    final fill = Paint()
      ..color = accent.withAlpha(170)
      ..style = PaintingStyle.fill;
    canvas.drawArc(
      Rect.fromLTWH(size.width * 0.24, size.height * 0.20, size.width * 0.52,
          size.height * 0.54),
      math.pi,
      math.pi,
      false,
      stroke,
    );
    canvas.drawRRect(
        RRect.fromRectAndRadius(
            Rect.fromLTWH(size.width * 0.23, size.height * 0.48,
                size.width * 0.17, size.height * 0.27),
            const Radius.circular(8)),
        fill);
    canvas.drawRRect(
        RRect.fromRectAndRadius(
            Rect.fromLTWH(size.width * 0.60, size.height * 0.48,
                size.width * 0.17, size.height * 0.27),
            const Radius.circular(8)),
        fill);
    canvas.drawLine(Offset(size.width * 0.40, size.height * 0.72),
        Offset(size.width * 0.60, size.height * 0.72), stroke);
  }

  void _paintShoe(Canvas canvas, Size size) {
    final fill = Paint()
      ..color = accent.withAlpha(190)
      ..style = PaintingStyle.fill;
    final sole = Paint()
      ..color = lineColor
      ..strokeWidth = 3
      ..strokeCap = StrokeCap.round;
    final path = Path()
      ..moveTo(size.width * 0.20, size.height * 0.58)
      ..quadraticBezierTo(size.width * 0.43, size.height * 0.34,
          size.width * 0.62, size.height * 0.48)
      ..quadraticBezierTo(size.width * 0.76, size.height * 0.58,
          size.width * 0.84, size.height * 0.64)
      ..quadraticBezierTo(size.width * 0.67, size.height * 0.72,
          size.width * 0.23, size.height * 0.70)
      ..close();
    canvas.drawPath(path, fill);
    canvas.drawLine(Offset(size.width * 0.18, size.height * 0.73),
        Offset(size.width * 0.82, size.height * 0.74), sole);
  }

  void _paintHairDryer(Canvas canvas, Size size) {
    final fill = Paint()
      ..color = accent.withAlpha(185)
      ..style = PaintingStyle.fill;
    canvas.drawRRect(
        RRect.fromRectAndRadius(
            Rect.fromLTWH(size.width * 0.22, size.height * 0.35,
                size.width * 0.36, size.height * 0.24),
            const Radius.circular(10)),
        fill);
    final nozzle = Path()
      ..moveTo(size.width * 0.56, size.height * 0.39)
      ..lineTo(size.width * 0.82, size.height * 0.35)
      ..lineTo(size.width * 0.82, size.height * 0.56)
      ..lineTo(size.width * 0.56, size.height * 0.53)
      ..close();
    canvas.drawPath(nozzle, fill);
    canvas.drawRRect(
        RRect.fromRectAndRadius(
            Rect.fromLTWH(size.width * 0.34, size.height * 0.55,
                size.width * 0.14, size.height * 0.28),
            const Radius.circular(6)),
        fill);
  }

  void _paintBag(Canvas canvas, Size size) {
    final fill = Paint()
      ..color = accent.withAlpha(180)
      ..style = PaintingStyle.fill;
    final stroke = Paint()
      ..color = lineColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3
      ..strokeCap = StrokeCap.round;
    canvas.drawRRect(
        RRect.fromRectAndRadius(
            Rect.fromLTWH(size.width * 0.28, size.height * 0.32,
                size.width * 0.44, size.height * 0.46),
            const Radius.circular(10)),
        fill);
    canvas.drawArc(
        Rect.fromLTWH(size.width * 0.36, size.height * 0.22, size.width * 0.28,
            size.height * 0.25),
        math.pi,
        math.pi,
        false,
        stroke);
    canvas.drawLine(Offset(size.width * 0.35, size.height * 0.52),
        Offset(size.width * 0.65, size.height * 0.52), stroke);
  }

  void _paintWatch(Canvas canvas, Size size) {
    final fill = Paint()
      ..color = accent.withAlpha(180)
      ..style = PaintingStyle.fill;
    final band = Paint()
      ..color = lineColor
      ..style = PaintingStyle.fill;
    canvas.drawRRect(
        RRect.fromRectAndRadius(
            Rect.fromLTWH(size.width * 0.43, size.height * 0.18,
                size.width * 0.14, size.height * 0.62),
            const Radius.circular(7)),
        band);
    canvas.drawCircle(
        Offset(size.width * 0.50, size.height * 0.50), size.width * 0.22, fill);
  }

  void _paintIcon(Canvas canvas, Size size) {
    final painter = TextPainter(
      text: TextSpan(
        text: String.fromCharCode(icon.codePoint),
        style: TextStyle(
          fontSize: 34,
          color: accent.withAlpha(185),
          fontFamily: icon.fontFamily,
          package: icon.fontPackage,
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    painter.paint(
      canvas,
      Offset(
          (size.width - painter.width) / 2, (size.height - painter.height) / 2),
    );
  }

  @override
  bool shouldRepaint(covariant ProductThumbPainter oldDelegate) {
    return oldDelegate.icon != icon ||
        oldDelegate.accent != accent ||
        oldDelegate.lineColor != lineColor ||
        oldDelegate.text != text;
  }
}

class ThumbColors {
  final Color bg;
  final Color bg2;
  final IconData icon;

  const ThumbColors(this.bg, this.bg2, this.icon);
}
