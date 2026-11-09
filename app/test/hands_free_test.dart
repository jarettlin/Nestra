import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:nestra/models.dart';
import 'package:nestra/state/hands_free.dart';
import 'package:nestra/state/home_controller.dart';

/// Plays back scripted backend answers and records what was sent.
class ScriptedHome extends HomeController {
  ScriptedHome(this.answers);
  final List<Map<String, dynamic>> answers;
  final sent = <Map<String, Object?>>[];

  @override
  Future<CommandResult> runVoice(
    List<int> audio, {
    required String filename,
    required String mimeType,
    bool wake = false,
    bool conversation = false,
    String? previous,
  }) async {
    sent.add({'wake': wake, 'conversation': conversation, 'previous': previous});
    return CommandResult.fromJson(answers.removeAt(0));
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final speech = Uint8List(10);

  test('a conversation: wake, command, follow-up, then thanks', () async {
    final home = ScriptedHome([
      {'ok': false, 'woke': false, 'reply': ''}, // chatter: ignored
      {'ok': true, 'woke': true, 'listen': true, 'reply': 'Yes?', 'transcript': 'Hi Nestra'},
      {'ok': true, 'reply': 'Fan is on now.', 'transcript': 'turn on the fan', 'command': 'turn on the fan'},
      {'ok': true, 'reply': 'Main Light is off.', 'transcript': 'and the light off'},
      {'ok': true, 'end': true, 'reply': 'Anytime.', 'transcript': 'thank you'},
    ]);
    final hf = HandsFree(home)..status = HandsFreeStatus.listening;

    await hf.handleSpeech(speech);
    expect(hf.inConversation, isFalse);
    expect(hf.status, HandsFreeStatus.listening);

    await hf.handleSpeech(speech);
    expect(hf.inConversation, isTrue);
    expect(hf.status, HandsFreeStatus.conversing);

    await hf.handleSpeech(speech);
    await hf.handleSpeech(speech);
    expect(hf.turns.last.result.reply, 'Main Light is off.');
    expect(hf.status, HandsFreeStatus.conversing);

    await hf.handleSpeech(speech);
    expect(hf.inConversation, isFalse);
    expect(hf.status, HandsFreeStatus.listening);
    expect(home.sent.map((s) => s['conversation']), [false, false, true, true, true]);
  });

  test('answers to a question carry the question\'s command', () async {
    final home = ScriptedHome([
      {
        'ok': false, 'woke': true, 'needs_clarification': true, 'reply': 'Which fan?',
        'transcript': 'Hi Nestra turn on the fan', 'command': 'turn on the fan',
        'options': [{'room_id': 'bedroom', 'room_name': 'Bedroom'}],
      },
      {'ok': true, 'reply': 'Fan is on now.', 'transcript': 'bedroom'},
    ]);
    final hf = HandsFree(home)..status = HandsFreeStatus.listening;
    await hf.handleSpeech(speech);
    expect(hf.pendingQuestion?.options.single.roomName, 'Bedroom');
    await hf.handleSpeech(speech);
    expect(home.sent.last['previous'], 'turn on the fan');
    expect(hf.pendingQuestion, isNull);
  });

  test('two misunderstandings in a row end the conversation', () async {
    final home = ScriptedHome([
      {'ok': true, 'woke': true, 'listen': true, 'reply': 'Yes?', 'transcript': 'Hi Nestra'},
      {'ok': false, 'reply': 'Sorry?', 'transcript': 'blah'},
      {'ok': false, 'reply': 'Sorry?', 'transcript': 'blah blah'},
    ]);
    final hf = HandsFree(home)..status = HandsFreeStatus.listening;
    for (var i = 0; i < 3; i++) {
      await hf.handleSpeech(speech);
    }
    expect(hf.inConversation, isFalse);
  });
}
