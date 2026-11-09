import 'dart:async';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:record/record.dart';

/// A finished recording, ready to upload to /api/voice.
class Recording {
  const Recording(this.bytes, this.mimeType, this.filename);
  final Uint8List bytes;
  final String mimeType;
  final String filename;
}

/// Records one spoken command from the microphone.
///
/// The raw 16 kHz samples are streamed straight into memory and wrapped as a
/// WAV file, the format Whisper wants anyway. This avoids the browser's
/// MediaRecorder and blob URLs (Safari kept handing back the first recording).
///
/// Stops by itself shortly after you stop talking (or after [maxLength]),
/// so you can just speak and wait.
class VoiceRecorder {
  VoiceRecorder({this.maxLength = const Duration(seconds: 10)});

  final Duration maxLength;
  final _recorder = AudioRecorder();

  /// Microphone loudness while recording, 0 (silent) to 1 (loud), for the animation.
  final level = ValueNotifier<double>(0);

  static const sampleRate = 16000;
  static const _speechDb = -45.0; // louder than this counts as talking (low enough for across the room)
  static const _silenceAfterSpeech = Duration(milliseconds: 1400);

  StreamSubscription<Uint8List>? _audio;
  BytesBuilder? _pcm;
  Timer? _limit;
  Completer<void>? _autoStop;

  Future<bool> hasPermission() => _recorder.hasPermission();

  /// Starts recording. The returned future completes when it stops by itself.
  Future<void> start() async {
    await cancel();
    final pcm = _pcm = BytesBuilder(copy: false);
    final done = _autoStop = Completer<void>();
    final stream = await _recorder.startStream(const RecordConfig(
      encoder: AudioEncoder.pcm16bits,
      numChannels: 1,
      sampleRate: sampleRate,
      autoGain: true, // the browser/OS raises the level when you're further away
      echoCancel: true,
      noiseSuppress: true,
    ));
    var heardSpeech = false;
    DateTime? quietSince;
    _audio = stream.listen((chunk) {
      pcm.add(Uint8List.fromList(chunk)); // copy: the plugin may reuse its buffer
      final db = peakDb(chunk);
      level.value = ((db + 60) / 60).clamp(0.0, 1.0);
      if (db > _speechDb) {
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

  /// Stops recording and returns the audio as WAV (null if nothing was recorded).
  Future<Recording?> stop() async {
    _finish();
    await _recorder.stop();
    await _audio?.cancel();
    _audio = null;
    final pcm = _pcm?.takeBytes();
    _pcm = null;
    if (pcm == null || pcm.isEmpty) return null;
    return Recording(wav(pcm, sampleRate: sampleRate), 'audio/wav', 'command.wav');
  }

  Future<void> cancel() async {
    _finish();
    await _audio?.cancel();
    _audio = null;
    _pcm = null;
    if (await _recorder.isRecording()) await _recorder.cancel();
  }

  void _finish() {
    _limit?.cancel();
    level.value = 0;
    if (_autoStop != null && !_autoStop!.isCompleted) _autoStop!.complete();
  }

  Future<void> dispose() async {
    await cancel();
    await _recorder.dispose();
    level.dispose();
  }
}

/// Loudest sample in a chunk of 16-bit little-endian PCM, in dBFS (-60 = silence).
double peakDb(Uint8List chunk) {
  final data = ByteData.sublistView(chunk);
  var peak = 0;
  for (var i = 0; i + 1 < chunk.length; i += 2) {
    final v = data.getInt16(i, Endian.little).abs();
    if (v > peak) peak = v;
  }
  if (peak == 0) return -60;
  return math.max(-60, 20 * math.log(peak / 32768) / math.ln10);
}

/// Wraps mono 16-bit PCM samples in a WAV header.
Uint8List wav(Uint8List pcm, {required int sampleRate}) {
  final header = ByteData(44);
  void text(int at, String s) {
    for (var i = 0; i < s.length; i++) {
      header.setUint8(at + i, s.codeUnitAt(i));
    }
  }

  text(0, 'RIFF');
  header.setUint32(4, 36 + pcm.length, Endian.little);
  text(8, 'WAVE');
  text(12, 'fmt ');
  header.setUint32(16, 16, Endian.little); // fmt chunk size
  header.setUint16(20, 1, Endian.little); // PCM
  header.setUint16(22, 1, Endian.little); // mono
  header.setUint32(24, sampleRate, Endian.little);
  header.setUint32(28, sampleRate * 2, Endian.little); // bytes per second
  header.setUint16(32, 2, Endian.little); // bytes per sample frame
  header.setUint16(34, 16, Endian.little); // bits per sample
  text(36, 'data');
  header.setUint32(40, pcm.length, Endian.little);
  return (BytesBuilder(copy: false)
        ..add(header.buffer.asUint8List())
        ..add(pcm))
      .takeBytes();
}

/// Speaks replies out loud with the device's built-in voices.
class Speaker {
  Speaker._();
  static final instance = Speaker._();

  final _tts = FlutterTts();
  bool _ready = false;
  bool _speaking = false;
  Completer<void>? _finished;

  /// Mutes spoken replies (remembered while the app is open).
  final muted = ValueNotifier<bool>(false);

  /// Speaks [text] and completes once it has been said.
  ///
  /// Finishing is tracked here (the plugin's own "await completion" is
  /// unreliable in browsers), with a time limit based on the text's length
  /// so a lost "finished" event can never leave the caller waiting forever.
  Future<void> say(String text) async {
    if (muted.value || text.trim().isEmpty) return;
    try {
      if (!_ready) {
        await _tts.setLanguage('en-US');
        await _tts.setSpeechRate(kIsWeb ? 1.0 : 0.5);
        void done() => _finish();
        _tts.setCompletionHandler(done);
        _tts.setCancelHandler(done);
        _tts.setErrorHandler((_) => done());
        _ready = true;
      }
      if (_speaking) await stop();
      final finished = _finished = Completer<void>();
      _speaking = true;
      await _tts.speak(text);
      final limit = Duration(milliseconds: 1500 + 80 * text.length); // ~12 characters a second
      await finished.future.timeout(limit, onTimeout: () {});
    } catch (e) {
      debugPrint('Text-to-speech failed: $e');
    } finally {
      _speaking = false;
    }
  }

  void _finish() {
    _speaking = false;
    final f = _finished;
    _finished = null;
    if (f != null && !f.isCompleted) f.complete();
  }

  Future<void> stop() async {
    try {
      await _tts.stop();
    } catch (_) {}
    _finish();
  }
}
