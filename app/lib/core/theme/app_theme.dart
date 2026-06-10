import 'package:flutter/material.dart';

/// Product design system — refined with Klarna/Rufus/modern e-commerce patterns.
///
/// Generous spacing, soft gradients, elevated cards, and a warm-but-professional
/// indigo accent anchor the visual identity.

// ── Core palette ─────────────────────────────────────────────────────────

const _primary = Color(0xFF5B4CF0); // warm indigo (Rufus-like)
const _primarySoft = Color(0xFFA78BFA); // lighter accent for gradients
const _primaryMuted = Color(0xFFEDE9FE); // very light tint
const _inkMain = Color(0xFF0F172A); // near-black, softer than pure black
const _inkBody = Color(0xFF334155); // body text
const _inkSoft = Color(0xFF64748B); // secondary / caption
const _line = Color(0xFFE2E8F0); // subtle border
const _lineStrong = Color(0xFFCBD5E1); // card border
const _panel = Color(0xFFFFFFFF);
const _panelSoft = Color(0xFFF8FAFC); // card background tint
const _background = Color(0xFFF1F5F9); // page background (slightly blue-gray)
const _chatBg = Color(0xFFEDF0F5); // chat screen bg (like messaging apps)
const _userBubble = Color(0xFF5B4CF0); // user message bubble
const _userBubbleEnd = Color(0xFF7C6FF4); // gradient end
const _aiBubble = Color(0xFFFFFFFF); // AI message card
const _warn = Color(0xFFD97706);
const _good = Color(0xFF059669);
const _priceRed = Color(0xFFDC2626);

// Platform badge colors
const _jdRed = Color(0xFFC41A22);
const _pddRed = Color(0xFFE53A30);
const _taobaoOrange = Color(0xFFFF5000);
const _tmallRed = Color(0xFFFF0033);

// ── Chat bubble colors (exported for use in chat_screen) ────────────────

const chatUserBubbleStart = _userBubble;
const chatUserBubbleEnd = _userBubbleEnd;
const chatAiCardColor = _aiBubble;
const chatBackground = _chatBg;
const chatInputFill = _panel;

// ── Theme builder ───────────────────────────────────────────────────────

ThemeData buildAppTheme() {
  const colorScheme = ColorScheme.light(
    primary: _primary,
    onPrimary: Colors.white,
    secondary: _primarySoft,
    surface: _panel,
    surfaceContainerHighest: _panelSoft,
    error: _priceRed,
    onSurface: _inkMain,
    outline: _line,
  );

  return ThemeData(
    useMaterial3: true,
    fontFamily: 'AppSans',
    fontFamilyFallback: const ['Roboto', 'Arial', 'sans-serif'],
    colorScheme: colorScheme,
    scaffoldBackgroundColor: _background,

    // ── AppBar ─────────────────────────────────────────────────
    appBarTheme: const AppBarTheme(
      backgroundColor: _panel,
      foregroundColor: _inkMain,
      elevation: 0,
      scrolledUnderElevation: 0.5,
      centerTitle: false,
      titleTextStyle: TextStyle(
        fontSize: 18,
        fontWeight: FontWeight.w700,
        color: _inkMain,
        letterSpacing: -0.3,
      ),
    ),

    // ── Cards ──────────────────────────────────────────────────
    cardTheme: CardThemeData(
      color: _panel,
      elevation: 0,
      margin: EdgeInsets.zero,
      shadowColor: Colors.transparent,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: const BorderSide(color: _line, width: 0.5),
      ),
    ),

    // ── Input ──────────────────────────────────────────────────
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: _panel,
      contentPadding:
          const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: _line),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: _line),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: _primary, width: 1.5),
      ),
    ),

    // ── Buttons ────────────────────────────────────────────────
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: _primary,
        foregroundColor: Colors.white,
        elevation: 0,
        minimumSize: const Size.fromHeight(42),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
        ),
        textStyle: const TextStyle(
          fontSize: 14,
          fontWeight: FontWeight.w600,
        ),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: _inkBody,
        side: const BorderSide(color: _lineStrong),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(10),
        ),
        textStyle: const TextStyle(fontSize: 13),
      ),
    ),

    // ── Bottom nav ─────────────────────────────────────────────
    bottomNavigationBarTheme: const BottomNavigationBarThemeData(
      backgroundColor: _panel,
      selectedItemColor: _primary,
      unselectedItemColor: _inkSoft,
      type: BottomNavigationBarType.fixed,
      elevation: 0,
      selectedLabelStyle:
          TextStyle(fontSize: 11, fontWeight: FontWeight.w600),
      unselectedLabelStyle:
          TextStyle(fontSize: 11, fontWeight: FontWeight.w400),
    ),

    // ── Dividers ───────────────────────────────────────────────
    dividerTheme:
        const DividerThemeData(color: _line, thickness: 0.5, space: 0),

    // ── Chips ──────────────────────────────────────────────────
    chipTheme: ChipThemeData(
      backgroundColor: _panelSoft,
      selectedColor: _primaryMuted,
      labelStyle: const TextStyle(fontSize: 12, color: _inkBody),
      secondaryLabelStyle:
          const TextStyle(fontSize: 12, color: _primary),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
        side: const BorderSide(color: _line),
      ),
      side: const BorderSide(color: _line),
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 0),
    ),

    // ── Text theme ─────────────────────────────────────────────
    textTheme: const TextTheme(
      headlineLarge: TextStyle(
        fontSize: 28, fontWeight: FontWeight.w700, color: _inkMain,
        letterSpacing: -0.5,
      ),
      headlineSmall: TextStyle(
        fontSize: 21, fontWeight: FontWeight.w700, color: _inkMain,
        letterSpacing: -0.3,
      ),
      titleLarge: TextStyle(
        fontSize: 18, fontWeight: FontWeight.w700, color: _inkMain,
      ),
      titleMedium: TextStyle(
        fontSize: 16, fontWeight: FontWeight.w600, color: _inkMain,
      ),
      titleSmall: TextStyle(
        fontSize: 14, fontWeight: FontWeight.w600, color: _inkMain,
      ),
      bodyLarge: TextStyle(
        fontSize: 16, fontWeight: FontWeight.w400, color: _inkMain,
      ),
      bodyMedium: TextStyle(
        fontSize: 15, fontWeight: FontWeight.w400, color: _inkBody,
      ),
      bodySmall: TextStyle(
        fontSize: 14, fontWeight: FontWeight.w400, color: _inkSoft,
      ),
      labelLarge: TextStyle(
        fontSize: 13, fontWeight: FontWeight.w600, color: _inkBody,
      ),
      labelMedium: TextStyle(
        fontSize: 12, fontWeight: FontWeight.w500, color: _inkSoft,
      ),
      labelSmall: TextStyle(
        fontSize: 11, fontWeight: FontWeight.w500, color: _inkSoft,
      ),
    ),
  );
}

// ── Convenience accessors ────────────────────────────────────────────────

class AppColors {
  AppColors._();

  // Primary scale
  static const primary = _primary;
  static const primarySoft = _primarySoft;
  static const primaryMuted = _primaryMuted;

  // Ink / text
  static const inkMain = _inkMain;
  static const inkBody = _inkBody;
  static const inkSoft = _inkSoft;

  // Surfaces
  static const line = _line;
  static const lineStrong = _lineStrong;
  static const panel = _panel;
  static const panelSoft = _panelSoft;
  static const background = _background;

  // Semantic
  static const warn = _warn;
  static const good = _good;
  static const priceRed = _priceRed;

  // Chat
  static const chatBackground = _chatBg;
  static const userBubble = _userBubble;
  static const userBubbleEnd = _userBubbleEnd;

  // Platforms
  static const jdRed = _jdRed;
  static const pddRed = _pddRed;
  static const taobaoOrange = _taobaoOrange;
  static const tmallRed = _tmallRed;

  // Legacy aliases (keep old code compiling)
  static const accent = _primary;
  static const accentStrong = Color(0xFF4338CA);
  static const signal = Color(0xFF2453A6);
}

/// Platform badge color resolved by name.
Color platformColor(String platform) => switch (platform) {
      '京东-mock' => _jdRed,
      '拼多多-mock' => _pddRed,
      '淘宝-mock' => _taobaoOrange,
      '天猫-mock' => _tmallRed,
      _ => _inkSoft,
    };
