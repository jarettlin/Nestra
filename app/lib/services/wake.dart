import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:record/record.dart';

import 'voice.dart';

/// Cuts a continuous 16-bit mono PCM stream into bursts of speech.
///
/// Silence is never kept, so only moments when someone is talking get sent to
/// the backend. Each burst includes a little audio from just before the speech
/// started, so the first syllable ("Hi...") isn't clipped.
class SpeechSegmenter {
  SpeechSegmenter({
    this.sampleRate = 16000,
    this.speechDb = -42,
    this.preRoll = const Duration(milliseconds: 400),
    this.endSilence = const Duration(milliseconds: 900),
    this.minSpeech = const Duration(milliseconds: 250),
    this.maxLength = const Duration(seconds: 7),
  });

  final int sampleRate;
  final double speechDb;
  final Duration preRoll;
  final Duration endSilence;
  final Duration minSpeech;
  final Duration maxLength;

  final _preRoll = <Uint8List>[];
  int _preRollSamples = 0;
  BytesBuilder? _segment;
  int _segmentSamples = 0;
  int _speechSamples = 0;
  int _quietSamples = 0;

  int _samples(Duration d) => sampleRate * d.inMilliseconds ~/ 1000;

  /// Loudness of the last chunk, 0 (silent) to 1 (loud).
  double level = 0;

  bool get inSpeech => _segment != null;

  /// Feeds one chunk; returns a finished burst of speech (raw PCM), if any.
  Uint8List? add(Uint8List chunk) {
    final n = chunk.length ~/ 2;
    final db = peakDb(chunk);
    level = ((db + 60) / 60).clamp(0.0, 1.0);
    final loud = db > speechDb;
    final segment = _segment;
    if (segment == null) {
      if (!loud) {
        _preRoll.add(chunk);
        _preRollSamples += n;
        while (_preRoll.isNotEmpty && _preRollSamples - _preRoll.first.length ~/ 2 >= _samples(preRoll)) {
          _preRollSamples -= _preRoll.removeAt(0).length ~/ 2;
        }
        return null;
      }
      final started = _segment = BytesBuilder(copy: false);
      for (final c in _preRoll) {
        started.add(c);
      }
      _segmentSamples = _preRollSamples;
      _preRoll.clear();
      _preRollSamples = 0;
      _speechSamples = 0;
      _quietSamples = 0;
      return _append(chunk, n, loud);
    }
    return _append(chunk, n, loud);
  }

  Uint8List? _append(Uint8List chunk, int n, bool loud) {
    _segment!.add(chunk);
    _segmentSamples += n;
    if (loud) {
      _speechSamples += n;
      _quietSamples = 0;
    } else {
      _quietSamples += n;
    }
    final ended = _quietSamples >= _samples(endSilence) || _segmentSamples >= _samples(maxLength);
    if (!ended) return null;
    final pcm = _segment!.takeBytes();
    final enoughSpeech = _speechSamples >= _samples(minSpeech);
    reset();
    return enoughSpeech ? pcm : null; // a door slam or a cough isn't worth sending
  }

  void reset() {
    _segment = null;
    _segmentSamples = 0;
    _speechSamples = 0;
    _quietSamples = 0;
    _preRoll.clear();
    _preRollSamples = 0;
  }
}

/// Listens to the microphone continuously and hands each burst of speech
/// (as a WAV file) to [onSpeech]. While [onSpeech] runs, new speech is ignored.
class WakeListener {
  WakeListener({required this.onSpeech});

  final Future<void> Function(Uint8List wav) onSpeech;

  late final _recorder = AudioRecorder(); // created on first use (keeps tests off the plugin)
  final _segmenter = SpeechSegmenter();
  StreamSubscription<Uint8List>? _audio;
  bool _handling = false;

  /// Microphone loudness, 0 to 1, for the indicator.
  final level = ValueNotifier<double>(0);

  bool get running => _audio != null;

  /// Someone is talking right now (a burst of speech is being collected).
  bool get hearingSpeech => _segmenter.inSpeech;

  Future<bool> hasPermission() => _recorder.hasPermission();

  Future<void> start() async {
    if (running) return;
    _segmenter.reset();
    final stream = await _recorder.startStream(const RecordConfig(
      encoder: AudioEncoder.pcm16bits,
      numChannels: 1,
      sampleRate: VoiceRecorder.sampleRate,
      autoGain: true,
      echoCancel: true,
      noiseSuppress: true,
    ));
    _audio = stream.listen(_onChunk);
  }

  void _onChunk(Uint8List chunk) {
    if (_handling) return;
    final speech = _segmenter.add(Uint8List.fromList(chunk));
    level.value = _segmenter.level;
    if (speech == null) return;
    _handling = true;
    level.value = 0;
    onSpeech(wav(speech, sampleRate: VoiceRecorder.sampleRate)).whenComplete(() {
      _segmenter.reset();
      _handling = false;
    });
  }

  /// Releases the microphone (e.g. while the command box records).
  Future<void> stop() async {
    await _audio?.cancel();
    _audio = null;
    level.value = 0;
    if (await _recorder.isRecording()) await _recorder.stop();
  }

  Future<void> dispose() async {
    await stop();
    await _recorder.dispose();
    level.dispose();
  }
}
