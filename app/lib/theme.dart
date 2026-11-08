import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import 'models.dart';

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
      'appliance' => Icons.power_settings_new_rounded,
      _ => Icons.devices_other_rounded,
    };

IconData iconForAppliance(String kind) => switch (kind) {
      'tv' => Icons.tv_rounded,
      'kettle' => Icons.emoji_food_beverage_outlined,
      'washer' => Icons.local_laundry_service_outlined,
      'dryer' => Icons.dry_cleaning_outlined,
      'fridge' => Icons.kitchen_outlined,
      'microwave' => Icons.microwave_outlined,
      'coffee' => Icons.coffee_maker_outlined,
      'speaker' => Icons.speaker_outlined,
      'heater' => Icons.local_fire_department_outlined,
      'purifier' => Icons.filter_vintage_outlined,
      'vacuum' => Icons.cleaning_services_outlined,
      'charger' => Icons.battery_charging_full_rounded,
      'plug' => Icons.power_outlined,
      _ => Icons.electrical_services_rounded,
    };

/// Icon for a specific device (appliances use their kind's icon).
IconData iconFor(Device d) => d.type == 'appliance' ? iconForAppliance(d.kind) : iconForDevice(d.type);

Color colorForDevice(String type) => switch (type) {
      'light' => NestraColors.peach,
      'fan' => NestraColors.blue,
      'ac' => NestraColors.teal,
      'blinds' => NestraColors.purple,
      'lock' => NestraColors.red,
      'appliance' => NestraColors.green,
      _ => NestraColors.textSecondary,
    };

String formatTemp(double t) => '${t.toStringAsFixed(t.truncateToDouble() == t ? 0 : 1)}°C';
