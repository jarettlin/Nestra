import 'package:flutter/material.dart';

import '../models.dart';
import '../theme.dart';

/// "Recent Activity" timeline with the connection status footer.
class ActivityPanel extends StatefulWidget {
  const ActivityPanel({super.key, required this.entries, required this.online, this.scrollable = true});

  final List<ActivityEntry> entries;
  final bool online;

  /// False when the panel sits inside an outer scroll view (narrow layouts).
  final bool scrollable;

  @override
  State<ActivityPanel> createState() => _ActivityPanelState();
}

class _ActivityPanelState extends State<ActivityPanel> {
  bool _showAll = false;

  @override
  Widget build(BuildContext context) {
    final entries = _showAll ? widget.entries : widget.entries.take(8).toList();
    final list = entries.isEmpty
        ? const Padding(
            padding: EdgeInsets.symmetric(vertical: 24),
            child: Text('Nothing yet', style: TextStyle(color: NestraColors.textSecondary)),
          )
        : ListView.builder(
            shrinkWrap: !widget.scrollable,
            physics: widget.scrollable ? null : const NeverScrollableScrollPhysics(),
            itemCount: entries.length,
            itemBuilder: (context, i) => _TimelineItem(entry: entries[i], last: i == entries.length - 1),
          );

    return Container(
      padding: const EdgeInsets.fromLTRB(18, 18, 18, 12),
      decoration: BoxDecoration(
        color: NestraColors.panel,
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: NestraColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Expanded(
                child: Text('Recent Activity', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
              ),
              if (widget.entries.length > 8)
                TextButton(
                  onPressed: () => setState(() => _showAll = !_showAll),
                  style: TextButton.styleFrom(
                    foregroundColor: NestraColors.purple,
                    visualDensity: VisualDensity.compact,
                  ),
                  child: Text(_showAll ? 'Show less' : 'View All'),
                ),
            ],
          ),
          const SizedBox(height: 10),
          if (widget.scrollable) Expanded(child: list) else list,
          const Divider(color: NestraColors.border, height: 20),
          Row(
            children: [
              Container(
                width: 7,
                height: 7,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: widget.online ? NestraColors.green : NestraColors.red,
                ),
              ),
              const SizedBox(width: 8),
              Text(
                widget.online ? 'SYSTEM ONLINE' : 'RECONNECTING…',
                style: const TextStyle(
                  fontSize: 11,
                  letterSpacing: 1.1,
                  fontWeight: FontWeight.w600,
                  color: NestraColors.textSecondary,
                ),
              ),
              const Spacer(),
              Icon(
                widget.online ? Icons.wifi_rounded : Icons.wifi_off_rounded,
                size: 16,
                color: NestraColors.textSecondary,
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _TimelineItem extends StatelessWidget {
  const _TimelineItem({required this.entry, required this.last});

  final ActivityEntry entry;
  final bool last;

  @override
  Widget build(BuildContext context) {
    final t = entry.time;
    final clock = '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';
    final source = switch (entry.source) {
      'voice' => 'Voice',
      'manual' => 'Manual',
      'cli' => 'Console',
      _ => 'System',
    };
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SizedBox(
            width: 16,
            child: Column(
              children: [
                const SizedBox(height: 3),
                Container(
                  width: 11,
                  height: 11,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: NestraColors.panel,
                    border: Border.all(color: NestraColors.textSecondary, width: 2),
                  ),
                ),
                if (!last)
                  Expanded(child: Container(width: 1.5, color: NestraColors.border)),
              ],
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.only(bottom: 14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text.rich(
                    TextSpan(
                      children: [
                        TextSpan(text: entry.title, style: const TextStyle(fontWeight: FontWeight.w600)),
                        if (entry.roomName != null && entry.changes.isNotEmpty)
                          TextSpan(
                            text: '  ${entry.roomName}',
                            style: const TextStyle(color: NestraColors.textMuted, fontSize: 11.5),
                          ),
                      ],
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 12.5, height: 1.35),
                  ),
                  for (final change in entry.changes) _ChangeLine(change: change),
                  const SizedBox(height: 3),
                  Row(
                    children: [
                      Icon(_sourceIcon(entry.source), size: 11, color: NestraColors.textMuted),
                      const SizedBox(width: 4),
                      Text('$clock · $source', style: const TextStyle(fontSize: 11, color: NestraColors.textMuted)),
                    ],
                  ),
                  if (entry.command != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 2),
                      child: Text(
                        '"${entry.command}"',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 11,
                          fontStyle: FontStyle.italic,
                          color: NestraColors.textSecondary,
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

IconData _sourceIcon(String source) => switch (source) {
      'voice' => Icons.mic_none_rounded,
      'manual' => Icons.touch_app_outlined,
      'cli' => Icons.terminal_rounded,
      _ => Icons.settings_outlined,
    };

/// "Fan speed  High (85%) → Medium (55%)"
class _ChangeLine extends StatelessWidget {
  const _ChangeLine({required this.change});
  final ActivityChange change;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(top: 3),
        child: Text.rich(
          TextSpan(
            style: const TextStyle(fontSize: 11.5, height: 1.3),
            children: [
              TextSpan(text: '${change.label}  ', style: const TextStyle(color: NestraColors.textSecondary)),
              TextSpan(text: change.oldText, style: const TextStyle(color: NestraColors.textMuted)),
              const TextSpan(text: '  →  ', style: TextStyle(color: NestraColors.textMuted)),
              TextSpan(
                text: change.newText,
                style: const TextStyle(color: NestraColors.peach, fontWeight: FontWeight.w600),
              ),
            ],
          ),
        ),
      );
}
