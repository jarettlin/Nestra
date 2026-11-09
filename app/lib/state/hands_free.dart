import 'dart:async';

import 'package:flutter/foundation.dart';

import '../models.dart';
import '../services/voice.dart';
import '../services/wake.dart';
import 'home_controller.dart';

enum HandsFreeStatus { off, starting, listening, conversing, thinking }

/// One exchange in a hands-free conversation.
class Turn {
  const Turn(this.heard, this.result);
  final String heard;
  final CommandResult result;
}

/// "Hi Nestra" hands-free mode.
///
/// While on, the microphone stays open and every burst of speech goes to the
/// backend. Waiting for the wake phrase, only speech starting with "Hi Nestra"
/// is acted on. After Nestra answers, it keeps listening for a follow-up
/// without the wake phrase (a conversation) until you say "thank you" /
/// "that's all", or stay quiet for [followUpWindow].
class HandsFree extends ChangeNotifier {
  HandsFree(this.controller, {this.followUpWindow = const Duration(seconds: 8)}) {
    _listener = WakeListener(onSpeech: _onSpeech);
  }

  final HomeController controller;
  final Duration followUpWindow;
  late final WakeListener _listener;

  HandsFreeStatus status = HandsFreeStatus.off;
  String? error;

  /// The current conversation, newest last (shown in the conversation bar).
  final List<Turn> turns = [];

  /// True from "Hi Nestra" until the conversation ends.
  bool inConversation = false;

  /// The command Nestra just asked about ("Which room?", "Should I go ahead?").
  String? _pending;
  CommandResult? get pendingQuestion => _pending == null || turns.isEmpty ? null : turns.last.result;

  Timer? _quiet;
  int _misses = 0;

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
    _endConversation();
    await _listener.stop();
    _set(HandsFreeStatus.off);
  }

  /// Gives the microphone to something else (the command box) while [action] runs.
  Future<T> pauseWhile<T>(Future<T> Function() action) async {
    final wasOn = enabled;
    if (wasOn) {
      _endConversation();
      await _listener.stop();
      notifyListeners();
    }
    try {
      return await action();
    } finally {
      if (wasOn && enabled) {
        await _listener.start();
        _set(HandsFreeStatus.listening);
      }
    }
  }

  /// Answer Nestra's "which room?" by tapping a room.
  Future<void> answerRoom(String roomId) async {
    final command = _pending;
    if (command == null) return;
    _quiet?.cancel();
    _set(HandsFreeStatus.thinking);
    final result = await controller.runCommand(command, roomContext: roomId);
    await _respond(command, result);
  }

  /// Stop the conversation now (the bar's close button).
  void endConversation() {
    _endConversation();
    if (enabled) _set(HandsFreeStatus.listening);
  }

  @visibleForTesting
  Future<void> handleSpeech(Uint8List wav) => _onSpeech(wav);

  Future<void> _onSpeech(Uint8List wav) async {
    final following = inConversation;
    _quiet?.cancel();
    _set(HandsFreeStatus.thinking);
    final result = await controller.runVoice(
      wav,
      filename: 'speech.wav',
      mimeType: 'audio/wav',
      wake: true,
      conversation: following,
      previous: _pending,
    );
    if (!enabled) return;
    if (!following && !result.woke) {
      _set(HandsFreeStatus.listening); // not for Nestra
      return;
    }
    final heard = (result.transcript ?? '').trim();
    if (heard.isEmpty) {
      _listenForFollowUp(); // noise; keep the conversation open
      return;
    }
    await _respond(heard, result);
  }

  Future<void> _respond(String heard, CommandResult result) async {
    inConversation = true;
    turns.add(Turn(heard, result));
    if (turns.length > 4) turns.removeAt(0);
    final asked = result.needsClarification || result.needsConfirmation;
    _pending = asked ? (result.command ?? heard) : null;
    _misses = result.ok || asked ? 0 : _misses + 1;
    _set(HandsFreeStatus.thinking);
    await Speaker.instance.say(result.reply); // the mic ignores speech while Nestra talks
    if (!enabled) return;
    if (result.end || _misses >= 2) {
      endConversation(); // "thank you", or two things in a row it didn't understand
    } else {
      _listenForFollowUp();
    }
  }

  void _listenForFollowUp() {
    _set(HandsFreeStatus.conversing);
    _quiet?.cancel();
    _quiet = Timer(followUpWindow, _quietCheck);
  }

  void _quietCheck() {
    if (status != HandsFreeStatus.conversing) return;
    if (_listener.hearingSpeech) {
      _quiet = Timer(const Duration(seconds: 2), _quietCheck); // still talking
      return;
    }
    endConversation(); // nobody answered: back to waiting for "Hi Nestra"
  }

  void _endConversation() {
    _quiet?.cancel();
    inConversation = false;
    _pending = null;
    _misses = 0;
    turns.clear();
  }

  void _set(HandsFreeStatus s) {
    status = s;
    notifyListeners();
  }

  @override
  void dispose() {
    _quiet?.cancel();
    _listener.dispose();
    super.dispose();
  }
}
