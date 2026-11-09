import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:record/record.dart';

import 'read_bytes.dart';

/// A finished recording, ready to upload to /api/voice.
class Recording {
  const Recording(this.bytes, this.mimeType, this.filename);
  final Uint8List bytes;
  final String mimeType;
  final String filename;
}

/// Records one spoken command from the microphone.
///
/// Stops by itself shortly after you stop talking (or after [maxLength]),
/// so you can just speak and wait.
class VoiceRecorder {
  VoiceRecorder({this.maxLength = const Duration(seconds: 10)});

  final Duration maxLength;
  final _recorder = AudioRecorder();

  /// Microphone loudness while recording, 0 (silent) to 1 (loud), for the animation.
  final level = ValueNotifier<double>(0);

  StreamSubscription<Amplitude>? _amplitude;
  Timer? _limit;
  Completer<void>? _autoStop;
  AudioEncoder _encoder = AudioEncoder.opus;

  static const _speechDb = -38.0; // louder than this counts as talking
  static const _silenceAfterSpeech = Duration(milliseconds: 1400);

  Future<bool> hasPermission() => _recorder.hasPermission();

  /// Starts recording. The returned future completes when it stops by itself.
  Future<void> start() async {
    _encoder = await _pickEncoder();
    await _recorder.start(
      RecordConfig(encoder: _encoder, numChannels: 1, sampleRate: 16000, echoCancel: true, noiseSuppress: true),
      path: kIsWeb ? '' : '${DateTime.now().millisecondsSinceEpoch}.${_extension(_encoder)}',
    );
    final done = _autoStop = Completer<void>();
    var heardSpeech = false;
    DateTime? quietSince;
    _amplitude = _recorder.onAmplitudeChanged(const Duration(milliseconds: 120)).listen((a) {
      level.value = ((a.current + 60) / 60).clamp(0.0, 1.0);
      if (a.current > _speechDb) {
        heardSpeech = true;
        quietSince = null;
      } else if (heardSpeech) {
        quietSince ??= DateTime.now();
        if (DateTime.now().difference(quietSince!) > _silenceAfterSpeech && !done.isCompleted) {
          done.complete();
        }
      }
    });
    _limit = Timer(maxLength, () {
      if (!done.isCompleted) done.complete();
    });
    return done.future;
  }

  /// Stops recording and returns the audio (null if nothing was recorded).
  Future<Recording?> stop() async {
    _limit?.cancel();
    await _amplitude?.cancel();
    _amplitude = null;
    level.value = 0;
    if (_autoStop != null && !_autoStop!.isCompleted) _autoStop!.complete();
    final path = await _recorder.stop();
    if (path == null || path.isEmpty) return null;
    final bytes = await readRecording(path);
    if (bytes.isEmpty) return null;
    return Recording(bytes, _mime(_encoder), 'command.${_extension(_encoder)}');
  }

  Future<void> cancel() async {
    _limit?.cancel();
    await _amplitude?.cancel();
    _amplitude = null;
    level.value = 0;
    if (await _recorder.isRecording()) await _recorder.cancel();
  }

  Future<AudioEncoder> _pickEncoder() async {
    // Opus/WebM in Chrome-based browsers, AAC in Safari, WAV as a last resort.
    for (final e in [AudioEncoder.opus, AudioEncoder.aacLc, AudioEncoder.wav]) {
      if (await _recorder.isEncoderSupported(e)) return e;
    }
    return AudioEncoder.wav;
  }

  static String _extension(AudioEncoder e) => switch (e) {
        AudioEncoder.opus => kIsWeb ? 'webm' : 'ogg',
        AudioEncoder.aacLc => 'm4a',
        _ => 'wav',
      };

  static String _mime(AudioEncoder e) => switch (e) {
        AudioEncoder.opus => kIsWeb ? 'audio/webm' : 'audio/ogg',
        AudioEncoder.aacLc => 'audio/mp4',
        _ => 'audio/wav',
      };

  Future<void> dispose() async {
    await cancel();
    await _recorder.dispose();
    level.dispose();
  }
}

/// Speaks replies out loud with the device's built-in voices.
class Speaker {
  Speaker._();
  static final instance = Speaker._();

  final _tts = FlutterTts();
  bool _ready = false;

  /// Mutes spoken replies (remembered while the app is open).
  final muted = ValueNotifier<bool>(false);

  Future<void> say(String text) async {
    if (muted.value || text.trim().isEmpty) return;
    try {
      if (!_ready) {
        await _tts.setLanguage('en-US');
        await _tts.setSpeechRate(kIsWeb ? 1.0 : 0.5);
        _ready = true;
      }
      await _tts.stop();
      await _tts.speak(text);
    } catch (e) {
      debugPrint('Text-to-speech failed: $e');
    }
  }

  Future<void> stop() async {
    try {
      await _tts.stop();
    } catch (_) {}
  }
}
