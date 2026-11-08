import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../config.dart';

/// WebSocket to the backend that reconnects automatically with backoff.
class LiveConnection {
  LiveConnection({Uri? uri}) : _uri = uri ?? wsUri();

  final Uri _uri;
  final _messages = StreamController<Map<String, dynamic>>.broadcast();
  final connected = ValueNotifier<bool>(false);
  WebSocketChannel? _channel;
  bool _closed = false;

  Stream<Map<String, dynamic>> get messages => _messages.stream;

  void start() => unawaited(_run());

  Future<void> _run() async {
    var backoff = const Duration(seconds: 1);
    while (!_closed) {
      try {
        final channel = WebSocketChannel.connect(_uri);
        _channel = channel;
        await channel.ready;
        connected.value = true;
        backoff = const Duration(seconds: 1);
        await for (final raw in channel.stream) {
          final decoded = jsonDecode(raw as String);
          if (decoded is Map<String, dynamic>) _messages.add(decoded);
        }
      } catch (e) {
        debugPrint('Nestra live connection error: $e');
      }
      connected.value = false;
      if (_closed) break;
      await Future<void>.delayed(backoff);
      backoff = Duration(seconds: min(backoff.inSeconds * 2, 10));
    }
  }

  void dispose() {
    _closed = true;
    _channel?.sink.close();
    _messages.close();
    connected.dispose();
  }
}
