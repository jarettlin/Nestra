import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:nestra/services/wake.dart';

/// 100 ms of 16 kHz audio at a fixed sample value.
Uint8List chunk(int amplitude) {
  final data = ByteData(3200);
  for (var i = 0; i < 1600; i++) {
    data.setInt16(i * 2, i.isEven ? amplitude : -amplitude, Endian.little);
  }
  return data.buffer.asUint8List();
}

void main() {
  final quiet = chunk(50); // about -56 dB
  final loud = chunk(8000); // about -12 dB

  test('silence never produces a segment', () {
    final s = SpeechSegmenter();
    for (var i = 0; i < 100; i++) {
      expect(s.add(quiet), isNull);
    }
  });

  test('speech followed by silence becomes one segment with pre-roll', () {
    final s = SpeechSegmenter();
    for (var i = 0; i < 10; i++) {
      s.add(quiet);
    }
    for (var i = 0; i < 8; i++) {
      expect(s.add(loud), isNull); // 0.8 s of talking
    }
    Uint8List? segment;
    for (var i = 0; i < 9 && segment == null; i++) {
      segment = s.add(quiet); // ends after 0.9 s of silence
    }
    expect(segment, isNotNull);
    // 0.4 s pre-roll + 0.8 s speech + 0.9 s trailing silence
    expect(segment!.length, 3200 * (4 + 8 + 9));
  });

  test('a short knock is dropped', () {
    final s = SpeechSegmenter();
    s.add(loud); // 0.1 s
    Uint8List? segment;
    for (var i = 0; i < 12; i++) {
      segment ??= s.add(quiet);
    }
    expect(segment, isNull);
    expect(s.inSpeech, isFalse);
  });

  test('long speech is cut at the maximum length', () {
    final s = SpeechSegmenter(maxLength: const Duration(seconds: 2));
    Uint8List? segment;
    var chunks = 0;
    while (segment == null && chunks < 100) {
      segment = s.add(loud);
      chunks++;
    }
    expect(chunks, 20);
  });
}
