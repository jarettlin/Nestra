import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';

import '../config.dart';
import '../models.dart';

class ApiException implements Exception {
  ApiException(this.message);
  final String message;
  @override
  String toString() => message;
}

/// Returns the signed-in user's Firebase ID token (null when signed out).
typedef TokenProvider = Future<String?> Function({bool forceRefresh});

/// REST calls to the Nestra backend. Live updates arrive separately over the WebSocket.
class NestraApi {
  NestraApi({http.Client? client, this.token}) : _client = _AuthClient(client ?? http.Client(), token);

  final http.Client _client;
  final TokenProvider? token;
  static const _headers = {'content-type': 'application/json'};

  Future<void> patchDevice(String id, Map<String, dynamic> updates) async {
    final res = await _send(
      () => _client.patch(apiUri('/api/devices/$id'), headers: _headers, body: jsonEncode(updates)),
    );
    _check(res);
  }

  Future<Catalog> catalog() async {
    final res = await _send(() => _client.get(apiUri('/api/catalog')));
    _check(res);
    return Catalog.fromJson(jsonDecode(res.body) as Map<String, dynamic>);
  }

  Future<void> createRoom(String name) async =>
      _check(await _send(() => _client.post(apiUri('/api/rooms'), headers: _headers, body: jsonEncode({'name': name}))));

  Future<void> renameRoom(String id, String name) async => _check(
      await _send(() => _client.patch(apiUri('/api/rooms/$id'), headers: _headers, body: jsonEncode({'name': name}))));

  Future<void> deleteRoom(String id) async => _check(await _send(() => _client.delete(apiUri('/api/rooms/$id'))));

  Future<void> createDevice({
    required String type,
    required String name,
    required String roomId,
    String? kind,
  }) async =>
      _check(await _send(() => _client.post(
            apiUri('/api/devices'),
            headers: _headers,
            body: jsonEncode({'type': type, 'name': name, 'room_id': roomId, 'kind': ?kind}),
          )));

  Future<void> deleteDevice(String id) async => _check(await _send(() => _client.delete(apiUri('/api/devices/$id'))));

  /// Upload a recording; the backend transcribes it and runs the command.
  Future<CommandResult> voice(
    List<int> audio, {
    required String filename,
    required String mimeType,
    String? roomContext,
    bool wake = false,
    bool conversation = false,
    String? previous,
  }) async {
    final request = http.MultipartRequest('POST', apiUri('/api/voice'))
      ..files.add(http.MultipartFile.fromBytes('audio', audio, filename: filename, contentType: _mediaType(mimeType)));
    if (roomContext != null) request.fields['room_context'] = roomContext;
    if (wake) request.fields['wake'] = 'true';
    if (conversation) request.fields['conversation'] = 'true';
    if (previous != null) request.fields['previous'] = previous;
    final http.Response res;
    try {
      // Generous timeout: the first request may wait for the speech model to load.
      res = await http.Response.fromStream(await _client.send(request).timeout(const Duration(seconds: 60)));
    } catch (_) {
      throw ApiException("Can't reach the Nestra backend at $apiBase. Is it running?");
    }
    _check(res);
    return CommandResult.fromJson(jsonDecode(res.body) as Map<String, dynamic>);
  }

  static MediaType _mediaType(String mime) {
    final [type, sub] = mime.split('/');
    return MediaType(type, sub);
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
    if (res.statusCode == 401) throw ApiException('Your session has expired. Please sign in again.');
    var message = 'Request failed (${res.statusCode})';
    try {
      final detail = (jsonDecode(res.body) as Map<String, dynamic>)['detail'];
      if (detail != null) message = detail is String ? detail : jsonEncode(detail);
    } catch (_) {}
    throw ApiException(message);
  }
}

/// Adds `Authorization: Bearer <Firebase ID token>` to every request.
class _AuthClient extends http.BaseClient {
  _AuthClient(this._inner, this._token);

  final http.Client _inner;
  final TokenProvider? _token;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final token = await _token?.call();
    if (token != null) request.headers['authorization'] = 'Bearer $token';
    return _inner.send(request);
  }
}
