import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../models.dart';
import '../services/voice.dart';
import '../state/home_controller.dart';
import '../theme.dart';

const _examples = [
  'Lower the fan to a comfortable speed',
  'Make the bedroom cozy',
  'Dim the lights a bit',
  'Make it a bit warmer',
  'Close the shades',
  'Unlock the front door',
];

/// Opens the command box. With [listen], it starts recording straight away (the mic button).
/// [result] opens it on a spoken follow-up instead ("Which room?"), from hands-free mode.
Future<void> showCommandDialog(
  BuildContext context,
  HomeController controller, {
  bool listen = true,
  CommandResult? result,
}) =>
    showDialog(
      context: context,
      builder: (_) => CommandDialog(controller: controller, listenOnOpen: listen && result == null, initialResult: result),
    );

/// Speak or type a command. Voice is recorded here, transcribed by the backend
/// (Whisper), and the reply is spoken back. Handles the backend's follow-ups:
/// "which room?" and "are you sure?".
class CommandDialog extends StatefulWidget {
  const CommandDialog({super.key, required this.controller, this.listenOnOpen = false, this.initialResult});

  final HomeController controller;
  final bool listenOnOpen;
  final CommandResult? initialResult;

  @override
  State<CommandDialog> createState() => _CommandDialogState();
}

class _CommandDialogState extends State<CommandDialog> {
  final _text = TextEditingController();
  final _recorder = VoiceRecorder();
  String _lastCommand = '';
  CommandResult? _result;
  bool _busy = false;
  bool _listening = false;
  bool _spoken = false; // this conversation started by voice, so answer out loud
  String? _voiceError;

  @override
  void initState() {
    super.initState();
    final first = widget.initialResult;
    if (first != null) {
      _result = first;
      _spoken = true;
      _lastCommand = first.command ?? first.transcript ?? '';
      _text.text = first.transcript ?? '';
    }
    if (widget.listenOnOpen) WidgetsBinding.instance.addPostFrameCallback((_) => _listen());
  }

  @override
  void dispose() {
    _text.dispose();
    _recorder.dispose();
    super.dispose();
  }

  Future<void> _run(String text, {String? roomContext, bool confirm = false}) async {
    text = text.trim();
    if (text.isEmpty || _busy) return;
    setState(() {
      _busy = true;
      _lastCommand = text;
    });
    final result = await widget.controller.runCommand(text, roomContext: roomContext, confirm: confirm);
    if (!mounted) return;
    setState(() {
      _busy = false;
      _result = result;
    });
    if (_spoken) Speaker.instance.say(result.reply);
  }

  Future<void> _listen() async {
    if (_listening || _busy) return;
    await Speaker.instance.stop();
    setState(() {
      _voiceError = null;
      _result = null;
    });
    final allowed = await _recorder.hasPermission().timeout(const Duration(seconds: 8), onTimeout: () => false);
    if (!mounted) return;
    if (!allowed) {
      setState(() => _voiceError =
          'Nestra needs microphone access. Allow it in your browser (Safari, Chrome...), then tap the mic again.');
      return;
    }
    try {
      setState(() => _listening = true);
      final stoppedByItself = _recorder.start();
      await stoppedByItself; // returns when you stop talking, or after 10 s
      if (_listening) await _finishListening();
    } catch (e) {
      if (mounted) {
        setState(() {
          _listening = false;
          _voiceError = 'Couldn\'t use the microphone: $e';
        });
      }
    }
  }

  Future<void> _finishListening() async {
    if (!_listening) return;
    setState(() {
      _listening = false;
      _busy = true;
    });
    final recording = await _recorder.stop();
    if (!mounted) return;
    if (recording == null) {
      setState(() {
        _busy = false;
        _voiceError = 'Nothing was recorded. Please try again.';
      });
      return;
    }
    final result = await widget.controller.runVoice(
      recording.bytes,
      filename: recording.filename,
      mimeType: recording.mimeType,
    );
    if (!mounted) return;
    final heard = result.transcript?.trim() ?? '';
    setState(() {
      _busy = false;
      _spoken = true;
      _result = result;
      if (heard.isNotEmpty) {
        _text.text = heard;
        _lastCommand = result.command ?? heard; // without "Hi Nestra", for follow-ups
      }
    });
    Speaker.instance.say(result.reply);
  }

  Future<void> _cancelListening() async {
    await _recorder.cancel();
    if (mounted) setState(() => _listening = false);
  }

  @override
  Widget build(BuildContext context) {
    final result = _result;
    return Dialog(
      backgroundColor: NestraColors.panel,
      insetPadding: const EdgeInsets.all(16),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(24),
        side: const BorderSide(color: NestraColors.border),
      ),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 580, maxHeight: 640),
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(22),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Expanded(
                    child: Text('What would you like to do?', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
                  ),
                  ValueListenableBuilder<bool>(
                    valueListenable: Speaker.instance.muted,
                    builder: (context, muted, _) => IconButton(
                      tooltip: muted ? 'Speak replies' : 'Mute spoken replies',
                      onPressed: () {
                        Speaker.instance.muted.value = !muted;
                        if (!muted) Speaker.instance.stop();
                      },
                      icon: Icon(
                        muted ? Icons.volume_off_rounded : Icons.volume_up_rounded,
                        color: NestraColors.textSecondary,
                      ),
                    ),
                  ),
                  IconButton(
                    tooltip: 'Close',
                    onPressed: () => Navigator.pop(context),
                    icon: const Icon(Icons.close_rounded, color: NestraColors.textSecondary),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              Text(
                'Commands apply to ${widget.controller.selectedRoom?.name ?? 'this room'} unless you name a room.',
                style: const TextStyle(fontSize: 12, color: NestraColors.textSecondary),
              ),
              const SizedBox(height: 16),
              _VoiceButton(
                listening: _listening,
                busy: _busy,
                level: _recorder.level,
                onStart: _listen,
                onStop: _finishListening,
                onCancel: _cancelListening,
              ),
              if (_voiceError != null) ...[
                const SizedBox(height: 10),
                Text(_voiceError!, style: const TextStyle(color: NestraColors.red, fontSize: 12.5)),
              ],
              const SizedBox(height: 16),
              TextField(
                controller: _text,
                autofocus: !widget.listenOnOpen,
                textInputAction: TextInputAction.send,
                          onSubmitted: (t) {
                  _spoken = false;
                  _run(t);
                },
                decoration: InputDecoration(
                  hintText: 'Or type, e.g. lower the fan to a comfortable speed',
                  hintStyle: const TextStyle(color: NestraColors.textMuted),
                  filled: true,
                  fillColor: NestraColors.card,
                  prefixIcon: const Icon(Icons.chat_bubble_outline_rounded, color: NestraColors.textSecondary),
                  suffixIcon: Padding(
                    padding: const EdgeInsets.only(right: 6),
                    child: IconButton.filled(
                      tooltip: 'Send',
                      style: IconButton.styleFrom(backgroundColor: NestraColors.purple),
                      onPressed: _busy ? null : () => _run(_text.text),
                      icon: _busy
                          ? const SizedBox.square(
                              dimension: 16,
                              child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                            )
                          : const Icon(Icons.arrow_upward_rounded, color: Colors.white),
                    ),
                  ),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(16),
                    borderSide: const BorderSide(color: NestraColors.border),
                  ),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(16),
                    borderSide: const BorderSide(color: NestraColors.border),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(16),
                    borderSide: const BorderSide(color: NestraColors.purple),
                  ),
                ),
              ),
              const SizedBox(height: 14),
              if (result == null)
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    for (final e in _examples)
                      ActionChip(
                        label: Text(e, style: const TextStyle(fontSize: 12)),
                        backgroundColor: NestraColors.card,
                        side: const BorderSide(color: NestraColors.border),
                        onPressed: () {
                          _text.text = e;
                          _spoken = false;
                          _run(e);
                        },
                      ),
                  ],
                )
              else
                _ResultView(
                  result: result,
                  onPickRoom: (room) => _run(_lastCommand, roomContext: room),
                  onConfirm: () => _run(_lastCommand, confirm: true),
                  onCancel: () => setState(() => _result = null),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ResultView extends StatelessWidget {
  const _ResultView({
    required this.result,
    required this.onPickRoom,
    required this.onConfirm,
    required this.onCancel,
  });

  final CommandResult result;
  final ValueChanged<String> onPickRoom;
  final VoidCallback onConfirm;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) {
    final color = result.ok
        ? NestraColors.green
        : (result.needsClarification || result.needsConfirmation)
            ? NestraColors.orange
            : NestraColors.red;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: color.withValues(alpha: 0.08),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: color.withValues(alpha: 0.35)),
          ),
          child: Text(result.reply, style: const TextStyle(height: 1.45)),
        ),
        if (result.options.isNotEmpty) ...[
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            children: [
              for (final o in result.options)
                ActionChip(
                  avatar: const Icon(Icons.meeting_room_outlined, size: 16),
                  label: Text(o.roomName),
                  backgroundColor: NestraColors.card,
                  side: const BorderSide(color: NestraColors.border),
                  onPressed: () => onPickRoom(o.roomId),
                ),
            ],
          ),
        ],
        if (result.needsConfirmation) ...[
          const SizedBox(height: 12),
          Row(
            children: [
              FilledButton(onPressed: onConfirm, child: const Text('Yes, go ahead')),
              const SizedBox(width: 8),
              TextButton(onPressed: onCancel, child: const Text('Cancel')),
            ],
          ),
        ],
        for (final e in result.explanations) _Why(explanation: e),
      ],
    );
  }
}

/// The fuzzy engine's reasoning: inputs, the rules that fired and how strongly.
class _Why extends StatelessWidget {
  const _Why({required this.explanation});
  final Explanation explanation;

  String _input(String name, double v) => switch (name) {
        'temperature' => formatTemp(v),
        'humidity' => '${v.round()}% humidity',
        'time_of_day' => '${v.floor().toString().padLeft(2, '0')}:${((v % 1) * 60).floor().toString().padLeft(2, '0')}',
        'ambient_light' => 'daylight ${v.round()}/100',
        'intensity' => 'intensity ${v.toStringAsFixed(2)}',
        'headroom' => 'headroom ${v.round()}%',
        _ => '$name ${v.toStringAsFixed(1)}',
      };

  @override
  Widget build(BuildContext context) {
    final e = explanation;
    return Theme(
      data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
      child: ExpansionTile(
        tilePadding: EdgeInsets.zero,
        childrenPadding: const EdgeInsets.only(bottom: 8),
        iconColor: NestraColors.textSecondary,
        collapsedIconColor: NestraColors.textSecondary,
        leading: const Icon(Icons.psychology_alt_outlined, color: NestraColors.purple),
        title: Text('Why ${e.deviceName}?', style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
        subtitle: Text(
          '${e.output.replaceAll('_', ' ')} ${e.value.toStringAsFixed(1)} (${e.term}) from '
          '${e.inputs.entries.map((i) => _input(i.key, i.value)).join(', ')}',
          style: const TextStyle(fontSize: 12, color: NestraColors.textSecondary),
        ),
        children: [
          for (final r in e.rules)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Row(
                children: [
                  SizedBox(
                    width: 64,
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(4),
                      child: LinearProgressIndicator(
                        value: r.strength,
                        minHeight: 6,
                        backgroundColor: NestraColors.track,
                        color: NestraColors.purple,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  SizedBox(
                    width: 34,
                    child: Text(
                      r.strength.toStringAsFixed(2),
                      style: const TextStyle(fontSize: 11, color: NestraColors.textSecondary),
                    ),
                  ),
                  Expanded(child: Text(r.rule, style: const TextStyle(fontSize: 12, height: 1.35))),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

/// Big round mic: tap to talk, pulses with your voice while listening.
class _VoiceButton extends StatelessWidget {
  const _VoiceButton({
    required this.listening,
    required this.busy,
    required this.level,
    required this.onStart,
    required this.onStop,
    required this.onCancel,
  });

  final bool listening;
  final bool busy;
  final ValueListenable<double> level;
  final VoidCallback onStart;
  final VoidCallback onStop;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) {
    final label = listening
        ? 'Listening… stop talking to send'
        : busy
            ? 'Thinking…'
            : 'Tap to speak';
    return Center(
      child: Column(
        children: [
          ValueListenableBuilder<double>(
            valueListenable: level,
            builder: (context, v, _) {
              final glow = listening ? 10 + 30 * v : 0.0;
              return AnimatedContainer(
                duration: const Duration(milliseconds: 120),
                width: 84,
                height: 84,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: listening ? NestraColors.red : NestraColors.purple,
                  boxShadow: [
                    BoxShadow(
                      color: (listening ? NestraColors.red : NestraColors.purple).withValues(alpha: 0.35),
                      blurRadius: glow,
                      spreadRadius: glow / 3,
                    ),
                  ],
                ),
                child: Material(
                  type: MaterialType.transparency,
                  child: InkWell(
                    customBorder: const CircleBorder(),
                    onTap: busy ? null : (listening ? onStop : onStart),
                    child: Center(
                      child: busy
                          ? const SizedBox.square(
                              dimension: 28,
                              child: CircularProgressIndicator(strokeWidth: 2.5, color: Colors.white),
                            )
                          : Icon(listening ? Icons.stop_rounded : Icons.mic_rounded, color: Colors.white, size: 36),
                    ),
                  ),
                ),
              );
            },
          ),
          const SizedBox(height: 10),
          Text(label, style: const TextStyle(fontSize: 13, color: NestraColors.textSecondary)),
          if (listening)
            TextButton(onPressed: onCancel, child: const Text('Cancel')),
        ],
      ),
    );
  }
}
