import 'package:flutter/material.dart';

import '../state/hands_free.dart';
import '../state/home_controller.dart';
import '../theme.dart';

/// Floating card at the bottom of the dashboard during a hands-free
/// conversation: what Nestra heard, what it said, and whether it's listening.
class ConversationBar extends StatelessWidget {
  const ConversationBar({super.key, required this.handsFree, required this.controller});

  final HandsFree handsFree;
  final HomeController controller;

  @override
  Widget build(BuildContext context) => ListenableBuilder(
        listenable: handsFree,
        builder: (context, _) {
          final visible = handsFree.inConversation ||
              (handsFree.status == HandsFreeStatus.thinking && handsFree.turns.isNotEmpty);
          return AnimatedSwitcher(
            duration: const Duration(milliseconds: 220),
            transitionBuilder: (child, anim) => FadeTransition(
              opacity: anim,
              child: SlideTransition(
                position: Tween(begin: const Offset(0, 0.3), end: Offset.zero).animate(anim),
                child: child,
              ),
            ),
            child: visible ? _card(context) : const SizedBox.shrink(key: ValueKey('hidden')),
          );
        },
      );

  Widget _card(BuildContext context) {
    final status = handsFree.status;
    final last = handsFree.turns.isEmpty ? null : handsFree.turns.last;
    final question = handsFree.pendingQuestion;
    final hint = switch (status) {
      HandsFreeStatus.conversing => question?.needsConfirmation == true
          ? 'Listening… say “yes” or “no”'
          : question != null
              ? 'Listening… say a room'
              : 'Listening… or say “that’s all”',
      HandsFreeStatus.thinking => 'Thinking…',
      _ => '',
    };
    return ConstrainedBox(
      key: const ValueKey('card'),
      constraints: const BoxConstraints(maxWidth: 560),
      child: Material(
        color: NestraColors.cardRaised,
        elevation: 12,
        shadowColor: Colors.black54,
        borderRadius: BorderRadius.circular(22),
        child: Container(
          padding: const EdgeInsets.fromLTRB(16, 14, 8, 14),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(22),
            border: Border.all(color: NestraColors.green.withValues(alpha: 0.45)),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _Pulse(handsFree: handsFree),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (last != null) ...[
                      Text(
                        '“${last.heard}”',
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontSize: 13, color: NestraColors.textSecondary),
                      ),
                      const SizedBox(height: 4),
                      Text(last.result.reply, style: const TextStyle(fontSize: 14.5, height: 1.35)),
                    ],
                    if (question != null && question.options.isNotEmpty) ...[
                      const SizedBox(height: 8),
                      Wrap(
                        spacing: 6,
                        runSpacing: 6,
                        children: [
                          for (final o in question.options)
                            ActionChip(
                              label: Text(o.roomName, style: const TextStyle(fontSize: 12)),
                              backgroundColor: NestraColors.card,
                              side: const BorderSide(color: NestraColors.border),
                              onPressed: () => handsFree.answerRoom(o.roomId),
                            ),
                        ],
                      ),
                    ],
                    if (hint.isNotEmpty) ...[
                      const SizedBox(height: 6),
                      Text(hint, style: const TextStyle(fontSize: 12, color: NestraColors.green)),
                    ],
                  ],
                ),
              ),
              IconButton(
                tooltip: 'End conversation',
                iconSize: 18,
                color: NestraColors.textMuted,
                onPressed: handsFree.endConversation,
                icon: const Icon(Icons.close_rounded),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Green ear that glows with your voice while Nestra is listening.
class _Pulse extends StatelessWidget {
  const _Pulse({required this.handsFree});
  final HandsFree handsFree;

  @override
  Widget build(BuildContext context) => ValueListenableBuilder<double>(
        valueListenable: handsFree.level,
        builder: (context, level, _) {
          final thinking = handsFree.status == HandsFreeStatus.thinking;
          return AnimatedContainer(
            duration: const Duration(milliseconds: 120),
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: NestraColors.green.withValues(alpha: 0.16),
              boxShadow: [
                BoxShadow(
                  color: NestraColors.green.withValues(alpha: 0.3),
                  blurRadius: thinking ? 4 : 4 + 18 * level,
                  spreadRadius: thinking ? 0 : 4 * level,
                ),
              ],
            ),
            child: Center(
              child: thinking
                  ? const SizedBox.square(
                      dimension: 18,
                      child: CircularProgressIndicator(strokeWidth: 2, color: NestraColors.green),
                    )
                  : const Icon(Icons.hearing_rounded, size: 20, color: NestraColors.green),
            ),
          );
        },
      );
}
