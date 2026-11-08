import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';

import 'config.dart';
import 'firebase_options.dart';
import 'state/home_controller.dart';
import 'theme.dart';
import 'ui/dashboard.dart';
import 'ui/login_screen.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
  if (authEmulator.isNotEmpty) {
    final [host, port] = authEmulator.split(':');
    await FirebaseAuth.instance.useAuthEmulator(host, int.parse(port));
  }
  runApp(const NestraApp());
}

class NestraApp extends StatelessWidget {
  const NestraApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Nestra',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(),
      home: const AuthGate(),
    );
  }
}

/// Shows the login screen when signed out, and the user's home when signed in.
class AuthGate extends StatelessWidget {
  const AuthGate({super.key});

  @override
  Widget build(BuildContext context) {
    return StreamBuilder<User?>(
      // userChanges also fires when the profile (display name) is updated after sign-up.
      stream: FirebaseAuth.instance.userChanges(),
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Scaffold(body: Center(child: CircularProgressIndicator(color: NestraColors.purple)));
        }
        final user = snapshot.data;
        if (user == null) return const LoginScreen();
        // A new key per user rebuilds the home (and its connection) on account switch.
        return SignedInHome(key: ValueKey(user.uid), user: user);
      },
    );
  }
}

class SignedInHome extends StatefulWidget {
  const SignedInHome({super.key, required this.user});

  final User user;

  @override
  State<SignedInHome> createState() => _SignedInHomeState();
}

class _SignedInHomeState extends State<SignedInHome> {
  late final HomeController controller = HomeController(
    token: ({bool forceRefresh = false}) => widget.user.getIdToken(forceRefresh),
  )..start();

  @override
  void dispose() {
    controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Dashboard(controller: controller, user: widget.user);
}
