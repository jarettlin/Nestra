import 'package:flutter/material.dart';

import 'state/home_controller.dart';
import 'theme.dart';
import 'ui/dashboard.dart';

void main() {
  final controller = HomeController()..start();
  runApp(NestraApp(controller: controller));
}

class NestraApp extends StatelessWidget {
  const NestraApp({super.key, required this.controller});

  final HomeController controller;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Nestra',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(),
      home: Dashboard(controller: controller),
    );
  }
}
