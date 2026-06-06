import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/theme/app_theme.dart';
import 'chat_controller.dart';
import 'chat_models.dart';

/// Left-side drawer showing chat history.
class ChatHistoryDrawer extends ConsumerWidget {
  final VoidCallback onClose;

  const ChatHistoryDrawer({super.key, required this.onClose});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final controller = ref.watch(chatControllerProvider);
    final sessions = controller.sessions;
    final currentId = controller.currentSessionId;
    final loading = controller.loadingSessions;

    ref.listen(chatControllerProvider, (_, __) {
      // re-render on state changes
    });

    return Drawer(
      child: SafeArea(
        child: Column(
          children: [
            // Header
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 8, 8),
              child: Row(
                children: [
                  const Text('历史对话',
                      style: TextStyle(
                          fontSize: 18, fontWeight: FontWeight.w700)),
                  const Spacer(),
                  IconButton(
                    icon: const Icon(Icons.add_comment_outlined, size: 22),
                    tooltip: '新建对话',
                    onPressed: () {
                      ref.read(chatControllerProvider.notifier).newConversation();
                      onClose();
                    },
                  ),
                ],
              ),
            ),
            const Divider(),
            // New conversation button
            ListTile(
              leading: const Icon(Icons.chat_bubble_outline,
                  color: AppColors.accent),
              title: const Text('新建对话'),
              onTap: () {
                ref.read(chatControllerProvider.notifier).newConversation();
                onClose();
              },
            ),
            const Divider(height: 1),
            // Session list
            Expanded(
              child: loading
                  ? const Center(
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : sessions.isEmpty
                      ? const Center(
                          child: Text('暂无历史对话',
                              style: TextStyle(color: AppColors.inkSoft)))
                      : ListView.builder(
                          itemCount: sessions.length,
                          itemBuilder: (context, index) {
                            final s = sessions[index];
                            final isActive = s.sessionId == currentId;
                            return _SessionTile(
                              session: s,
                              isActive: isActive,
                              onTap: () {
                                ref
                                    .read(chatControllerProvider.notifier)
                                    .switchToSession(s.sessionId);
                                onClose();
                              },
                              onRename: () =>
                                  _showRenameDialog(context, ref, s),
                              onDelete: () =>
                                  _showDeleteDialog(context, ref, s),
                            );
                          },
                        ),
            ),
          ],
        ),
      ),
    );
  }

  void _showRenameDialog(
      BuildContext context, WidgetRef ref, ChatSessionSummary session) {
    final controller = TextEditingController(text: session.title);
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('重命名会话'),
        content: TextField(
          controller: controller,
          maxLength: 40,
          decoration: const InputDecoration(hintText: '输入新标题'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('取消'),
          ),
          TextButton(
            onPressed: () {
              final newTitle = controller.text.trim();
              if (newTitle.isNotEmpty) {
                ref
                    .read(chatControllerProvider.notifier)
                    .renameSession(session.sessionId, newTitle);
              }
              Navigator.pop(ctx);
            },
            child: const Text('确定'),
          ),
        ],
      ),
    );
  }

  void _showDeleteDialog(
      BuildContext context, WidgetRef ref, ChatSessionSummary session) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('删除会话'),
        content: Text('确定要删除「${session.title}」吗？'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('取消'),
          ),
          TextButton(
            onPressed: () {
              ref
                  .read(chatControllerProvider.notifier)
                  .deleteSession(session.sessionId);
              Navigator.pop(ctx);
            },
            child: const Text('删除',
                style: TextStyle(color: AppColors.priceRed)),
          ),
        ],
      ),
    );
  }
}

class _SessionTile extends StatelessWidget {
  final ChatSessionSummary session;
  final bool isActive;
  final VoidCallback onTap;
  final VoidCallback onRename;
  final VoidCallback onDelete;

  const _SessionTile({
    required this.session,
    required this.isActive,
    required this.onTap,
    required this.onRename,
    required this.onDelete,
  });

  @override
  Widget build(BuildContext context) {
    return ListTile(
      selected: isActive,
      selectedTileColor: AppColors.accent.withAlpha(15),
      title: Text(session.title,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(fontSize: 14)),
      subtitle: Text('${session.messageCount} 条消息',
          style: const TextStyle(fontSize: 12, color: AppColors.inkSoft)),
      trailing: PopupMenuButton<String>(
        icon: const Icon(Icons.more_vert, size: 18, color: AppColors.inkSoft),
        onSelected: (action) {
          if (action == 'rename') {
            onRename();
          } else if (action == 'delete') {
            onDelete();
          }
        },
        itemBuilder: (_) => const [
          PopupMenuItem(value: 'rename', child: Text('重命名')),
          PopupMenuItem(value: 'delete', child: Text('删除')),
        ],
      ),
      onTap: onTap,
    );
  }
}
