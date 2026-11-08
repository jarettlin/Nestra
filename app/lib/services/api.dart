import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config.dart';
import '../models.dart';

class ApiException implements Exception {
  ApiException(this.message);
  final String message;
  @override
  String toString() => message;
}

/// REST calls to the Nestra backend. Live updates arrive separately over the WebSocket.
class NestraApi {
  NestraApi({http.Client? client}) : _client = client ?? http.Client();

  final http.Client _client;
  static const _headers = {'content-type': 'application/json'};

  Future<void> patchDevice(String id, Map<String, dynamic> updates) async {
    final res = await _send(
      () => _client.patch(apiUri('/api/devices/$id'), headers: _headers, body: jsonEncode(updates)),
    );
    _check(res);
  }

  Future<CommandResult> command(String text, {String? roomContext, bool confirm = false}) async {
    final res = await _send(
      () => _client.post(
        apiUri('/api/command'),
        headers: _headers,
        body: jsonEncode({
          'text': text,
          'room_context': ?roomContext,
          'confirm': confirm,
        }),
      ),
    );
    _check(res);
    return CommandResult.fromJson(jsonDecode(res.body) as Map<String, dynamic>);
  }

  Future<http.Response> _send(Future<http.Response> Function() request) async {
    try {
      return await request().timeout(const Duration(seconds: 10));
    } catch (_) {
      throw ApiException("Can't reach the Nestra backend at $apiBase. Is it running?");
    }
  }

  void _check(http.Response res) {
    if (res.statusCode >= 200 && res.statusCode < 300) return;
    var message = 'Request failed (${res.statusCode})';
    try {
      final detail = (jsonDecode(res.body) as Map<String, dynamic>)['detail'];
      if (detail != null) message = detail is String ? detail : jsonEncode(detail);
    } catch (_) {}
    throw ApiException(message);
  }
}
