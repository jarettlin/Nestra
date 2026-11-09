import 'dart:io';
import 'dart:typed_data';

Future<Uint8List> readRecording(String path) async {
  final file = File(path);
  final bytes = await file.readAsBytes();
  await file.delete().catchError((_) => file); // temporary recording
  return bytes;
}
