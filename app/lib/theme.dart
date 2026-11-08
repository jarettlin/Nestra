import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Colours taken from the Luma in-wall tablet design.
abstract final class NestraColors {
  static const background = Color(0xFF14151B);
  static const panel = Color(0xFF1C1D24);
  static const card = Color(0xFF24252D);
  static const cardRaised = Color(0xFF2C2D36);
  static const border = Color(0xFF32333D);
  static const track = Color(0xFF3A3B45);

  static const textPrimary = Color(0xFFF2F2F5);
  static const textSecondary = Color(0xFF8D8E9B);
  static const textMuted = Color(0xFF5F606C);

  static const purple = Color(0xFF7B61FF);
  static const peach = Color(0xFFF4A672);
  static const blue = Color(0xFF5B8DEF);
  static const green = Color(0xFF4ADE80);
  static const orange = Color(0xFFF59E0B);
  static const red = Color(0xFFEF5350);
  static const teal = Color(0xFF2DD4BF);
}

ThemeData buildTheme() {
  final base = ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    scaffoldBackgroundColor: NestraColors.background,
    colorScheme: const ColorScheme.dark(
      primary: NestraColors.purple,
      secondary: NestraColors.peach,
      surface: NestraColors.card,
      onSurface: NestraColors.textPrimary,
    ),
  );
  return base.copyWith(
    textTheme: GoogleFonts.manropeTextTheme(base.textTheme).apply(
      bodyColor: NestraColors.textPrimary,
      displayColor: NestraColors.textPrimary,
    ),
    switchTheme: SwitchThemeData(
      thumbColor: const WidgetStatePropertyAll(Colors.white),
      trackColor: WidgetStateProperty.resolveWith(
        (s) => s.contains(WidgetState.selected) ? NestraColors.purple : NestraColors.track,
      ),
      trackOutlineColor: const WidgetStatePropertyAll(Colors.transparent),
    ),
    snackBarTheme: const SnackBarThemeData(
      backgroundColor: NestraColors.cardRaised,
      contentTextStyle: TextStyle(color: NestraColors.textPrimary),
      behavior: SnackBarBehavior.floating,
    ),
  );
}

IconData iconForDevice(String type) => switch (type) {
      'light' => Icons.lightbulb_outline_rounded,
      'fan' => Icons.air_rounded,
      'ac' => Icons.ac_unit_rounded,
      'blinds' => Icons.blinds_outlined,
      'lock' => Icons.lock_outline_rounded,
      _ => Icons.devices_other_rounded,
    };

Color colorForDevice(String type) => switch (type) {
      'light' => NestraColors.peach,
      'fan' => NestraColors.blue,
      'ac' => NestraColors.teal,
      'blinds' => NestraColors.purple,
      'lock' => NestraColors.red,
      _ => NestraColors.textSecondary,
    };

String formatTemp(double t) => '${t.toStringAsFixed(t.truncateToDouble() == t ? 0 : 1)}°C';
