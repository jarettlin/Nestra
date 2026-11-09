import 'package:flutter/foundation.dart';

import '../models.dart';
import '../services/voice.dart';
import '../services/wake.dart';
import 'home_controller.dart';

enum HandsFreeStatus { off, starting, listening, thinking }

/// "Hi Nestra" hands-free mode.
///
/// While on, the microphone stays open and every burst of speech goes to the
/// backend with wake=true; only speech that starts with "Hi Nestra" is acted
/// on. The UI supplies [openCommand] (show the command box, listening or
/// with a follow-up question) and [showResult] (a short notice).
class HandsFree extends ChangeNotifier {
  HandsFree(this.controller) {
    _listener = WakeListener(onSpeech: _onSpeech);
  }

  final HomeController controller;
  late final WakeListener _listener;

  HandsFreeStatus status = HandsFreeStatus.off;
  String? error;

  /// Opens the command box; completes when it closes. [result] is a follow-up
  /// ("Which room?") to show, or null to start listening for a command.
  Future<void> Function(CommandResult? result)? openCommand;

  /// Shows what was heard and done, e.g. a snack bar.
  void Function(CommandResult result)? showResult;

  bool get enabled => status != HandsFreeStatus.off;

  ValueListenable<double> get level => _listener.level;

  Future<void> toggle() => enabled ? disable() : enable();

  Future<void> enable() async {
    if (enabled) return;
    error = null;
    _set(HandsFreeStatus.starting);
    final allowed = await _listener.hasPermission().timeout(const Duration(seconds: 8), onTimeout: () => false);
    if (!allowed) {
      error = 'Hands-free needs microphone access. Allow it in your browser, then try again.';
      _set(HandsFreeStatus.off);
      return;
    }
    try {
      await _listener.start();
      _set(HandsFreeStatus.listening);
    } catch (e) {
      error = "Couldn't start listening: $e";
      _set(HandsFreeStatus.off);
    }
  }

  Future<void> disable() async {
    await _listener.stop();
    _set(HandsFreeStatus.off);
  }

  /// Gives the microphone to something else (the command box) while [action] runs.
  Future<T> pauseWhile<T>(Future<T> Function() action) async {
    final wasOn = enabled;
    if (wasOn) await _listener.stop();
    try {
      return await action();
    } finally {
      if (wasOn && enabled) {
        await _listener.start();
        _set(HandsFreeStatus.listening);
      }
    }
  }

  Future<void> _onSpeech(Uint8List wav) async {
    _set(HandsFreeStatus.thinking);
    try {
      final result = await controller.runVoice(wav, filename: 'speech.wav', mimeType: 'audio/wav', wake: true);
      if (!result.woke) return; // not for Nestra
      if (result.listen) {
        await Speaker.instance.say(result.reply); // "Yes?"
        await pauseWhile(() async => openCommand?.call(null));
      } else if (result.needsClarification || result.needsConfirmation) {
        await Speaker.instance.say(result.reply);
        await pauseWhile(() async => openCommand?.call(result));
      } else {
        showResult?.call(result);
        await Speaker.instance.say(result.reply); // the mic ignores speech until it's done
      }
    } finally {
      if (enabled) _set(HandsFreeStatus.listening);
    }
  }

  void _set(HandsFreeStatus s) {
    status = s;
    notifyListeners();
  }

  @override
  void dispose() {
    _listener.dispose();
    super.dispose();
  }
}
