/// Build-time settings. Override with --dart-define, e.g.
///   flutter run -d web-server --dart-define=NESTRA_API=http://192.168.1.20:8000
const String apiBase = String.fromEnvironment(
  'NESTRA_API',
  defaultValue: 'http://localhost:8000',
);

/// Name shown in the greeting ("Good evening, Alex."). Empty = no name.
const String residentName = String.fromEnvironment('NESTRA_USER');

Uri apiUri(String path) => Uri.parse(apiBase).replace(path: path);

Uri wsUri() {
  final base = Uri.parse(apiBase);
  return base.replace(scheme: base.scheme == 'https' ? 'wss' : 'ws', path: '/ws');
}

/// Use the local Firebase Auth emulator, e.g. --dart-define=NESTRA_AUTH_EMULATOR=localhost:9099
const String authEmulator = String.fromEnvironment('NESTRA_AUTH_EMULATOR');
