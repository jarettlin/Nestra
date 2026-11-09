import 'dart:typed_data';

import 'package:http/http.dart' as http;

Future<Uint8List> readRecording(String blobUrl) async => (await http.get(Uri.parse(blobUrl))).bodyBytes;
