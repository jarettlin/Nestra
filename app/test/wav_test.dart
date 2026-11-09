import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:nestra/services/voice.dart';

void main() {
  test('wraps 16-bit mono PCM in a valid WAV header', () {
    final pcm = Uint8List.fromList(List.generate(3200, (i) => i % 256)); // 0.1 s
    final file = wav(pcm, sampleRate: 16000);
    final h = ByteData.sublistView(file);
    expect(String.fromCharCodes(file.sublist(0, 4)), 'RIFF');
    expect(String.fromCharCodes(file.sublist(8, 12)), 'WAVE');
    expect(h.getUint32(4, Endian.little), 36 + pcm.length);
    expect(h.getUint16(22, Endian.little), 1); // mono
    expect(h.getUint32(24, Endian.little), 16000);
    expect(h.getUint16(34, Endian.little), 16);
    expect(h.getUint32(40, Endian.little), pcm.length);
    expect(file.sublist(44), pcm);
  });
}
