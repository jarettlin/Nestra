import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../theme.dart';

/// Sign in or create an account with email/password or Google (Firebase Auth).
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _name = TextEditingController();
  bool _creating = false;
  bool _busy = false;
  bool _hidePassword = true;
  String? _error;
  String? _info;

  FirebaseAuth get _auth => FirebaseAuth.instance;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    _name.dispose();
    super.dispose();
  }

  Future<void> _run(Future<void> Function() action) async {
    setState(() {
      _busy = true;
      _error = null;
      _info = null;
    });
    try {
      await action();
    } on FirebaseAuthException catch (e) {
      if (mounted) setState(() => _error = _message(e));
    } catch (e) {
      if (mounted) setState(() => _error = 'Something went wrong: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _submit() => _run(() async {
        final email = _email.text.trim();
        final password = _password.text;
        if (email.isEmpty || password.isEmpty) {
          throw FirebaseAuthException(code: 'missing-fields');
        }
        if (_creating) {
          final cred = await _auth.createUserWithEmailAndPassword(email: email, password: password);
          final name = _name.text.trim();
          if (name.isNotEmpty) await cred.user?.updateDisplayName(name);
        } else {
          await _auth.signInWithEmailAndPassword(email: email, password: password);
        }
      });

  Future<void> _google() => _run(() async {
        final provider = GoogleAuthProvider()..setCustomParameters({'prompt': 'select_account'});
        if (kIsWeb) {
          await _auth.signInWithPopup(provider);
        } else {
          await _auth.signInWithProvider(provider);
        }
      });

  Future<void> _resetPassword() => _run(() async {
        final email = _email.text.trim();
        if (email.isEmpty) throw FirebaseAuthException(code: 'reset-needs-email');
        await _auth.sendPasswordResetEmail(email: email);
        if (mounted) setState(() => _info = 'Password reset email sent to $email.');
      });

  String _message(FirebaseAuthException e) => switch (e.code) {
        'missing-fields' => 'Enter your email and password.',
        'reset-needs-email' => 'Enter your email first, then tap "Forgot password?".',
        'invalid-email' => 'That email address doesn\'t look right.',
        'invalid-credential' || 'wrong-password' || 'user-not-found' => 'Email or password is incorrect.',
        'email-already-in-use' => 'An account with this email already exists. Sign in instead.',
        'weak-password' => 'Use a password with at least 6 characters.',
        'too-many-requests' => 'Too many attempts. Please wait a moment and try again.',
        'popup-closed-by-user' || 'cancelled-popup-request' => 'Google sign-in was cancelled.',
        'operation-not-allowed' => 'This sign-in method isn\'t enabled in Firebase yet.',
        'network-request-failed' => 'No connection to Firebase. Check your internet.',
        _ => e.message ?? 'Sign-in failed (${e.code}).',
      };

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: Container(
              padding: const EdgeInsets.all(28),
              decoration: BoxDecoration(
                color: NestraColors.panel,
                borderRadius: BorderRadius.circular(24),
                border: Border.all(color: NestraColors.border),
              ),
              child: AutofillGroup(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Row(
                      children: [
                        Container(
                          padding: const EdgeInsets.all(10),
                          decoration: BoxDecoration(
                            color: NestraColors.purple.withValues(alpha: 0.2),
                            borderRadius: BorderRadius.circular(14),
                          ),
                          child: const Icon(Icons.home_rounded, color: NestraColors.purple),
                        ),
                        const SizedBox(width: 12),
                        const Text('Nestra', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w700)),
                      ],
                    ),
                    const SizedBox(height: 24),
                    Text(
                      _creating ? 'Create your account' : 'Welcome home',
                      style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w500),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      _creating
                          ? 'Set up your home and control it by voice.'
                          : 'Sign in to control your home.',
                      style: const TextStyle(color: NestraColors.textSecondary),
                    ),
                    const SizedBox(height: 24),
                    if (_creating) ...[
                      _field(_name, 'Your name (optional)', Icons.person_outline_rounded,
                          autofill: AutofillHints.name),
                      const SizedBox(height: 12),
                    ],
                    _field(_email, 'Email', Icons.mail_outline_rounded,
                        keyboard: TextInputType.emailAddress, autofill: AutofillHints.email),
                    const SizedBox(height: 12),
                    _field(
                      _password,
                      'Password',
                      Icons.lock_outline_rounded,
                      obscure: _hidePassword,
                      autofill: _creating ? AutofillHints.newPassword : AutofillHints.password,
                      onSubmitted: _submit,
                      suffix: IconButton(
                        tooltip: _hidePassword ? 'Show password' : 'Hide password',
                        onPressed: () => setState(() => _hidePassword = !_hidePassword),
                        icon: Icon(
                          _hidePassword ? Icons.visibility_outlined : Icons.visibility_off_outlined,
                          color: NestraColors.textSecondary,
                        ),
                      ),
                    ),
                    if (!_creating)
                      Align(
                        alignment: Alignment.centerRight,
                        child: TextButton(
                          onPressed: _busy ? null : _resetPassword,
                          child: const Text('Forgot password?'),
                        ),
                      ),
                    if (_error != null) _notice(_error!, NestraColors.red),
                    if (_info != null) _notice(_info!, NestraColors.green),
                    const SizedBox(height: 12),
                    FilledButton(
                      style: FilledButton.styleFrom(
                        minimumSize: const Size.fromHeight(48),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                      ),
                      onPressed: _busy ? null : _submit,
                      child: _busy
                          ? const SizedBox.square(dimension: 18, child: CircularProgressIndicator(strokeWidth: 2))
                          : Text(_creating ? 'Create account' : 'Sign in'),
                    ),
                    const SizedBox(height: 16),
                    const Row(
                      children: [
                        Expanded(child: Divider(color: NestraColors.border)),
                        Padding(
                          padding: EdgeInsets.symmetric(horizontal: 12),
                          child: Text('or', style: TextStyle(color: NestraColors.textMuted)),
                        ),
                        Expanded(child: Divider(color: NestraColors.border)),
                      ],
                    ),
                    const SizedBox(height: 16),
                    OutlinedButton.icon(
                      style: OutlinedButton.styleFrom(
                        minimumSize: const Size.fromHeight(48),
                        foregroundColor: NestraColors.textPrimary,
                        side: const BorderSide(color: NestraColors.border),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                      ),
                      onPressed: _busy ? null : _google,
                      icon: const Text('G', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
                      label: const Text('Continue with Google'),
                    ),
                    const SizedBox(height: 18),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text(
                          _creating ? 'Already have an account?' : 'New to Nestra?',
                          style: const TextStyle(color: NestraColors.textSecondary),
                        ),
                        TextButton(
                          onPressed: _busy
                              ? null
                              : () => setState(() {
                                    _creating = !_creating;
                                    _error = null;
                                    _info = null;
                                  }),
                          child: Text(_creating ? 'Sign in' : 'Create an account'),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _notice(String text, Color color) => Container(
        margin: const EdgeInsets.only(top: 8),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.1),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: color.withValues(alpha: 0.4)),
        ),
        child: Text(text, style: const TextStyle(fontSize: 13)),
      );

  Widget _field(
    TextEditingController controller,
    String label,
    IconData icon, {
    bool obscure = false,
    TextInputType? keyboard,
    String? autofill,
    Widget? suffix,
    VoidCallback? onSubmitted,
  }) =>
      TextField(
        controller: controller,
        obscureText: obscure,
        keyboardType: keyboard,
        autofillHints: autofill == null ? null : [autofill],
        onSubmitted: onSubmitted == null ? null : (_) => onSubmitted(),
        decoration: InputDecoration(
          labelText: label,
          labelStyle: const TextStyle(color: NestraColors.textSecondary),
          prefixIcon: Icon(icon, color: NestraColors.textSecondary),
          suffixIcon: suffix,
          filled: true,
          fillColor: NestraColors.card,
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(14),
            borderSide: const BorderSide(color: NestraColors.border),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(14),
            borderSide: const BorderSide(color: NestraColors.purple),
          ),
        ),
      );
}
