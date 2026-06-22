import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme/app_theme.dart';
import 'auth_controller.dart';

/// Login + register screen.
class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabController;
  final _loginUser = TextEditingController();
  final _loginPwd = TextEditingController();
  final _regUser = TextEditingController();
  final _regPwd = TextEditingController();
  final _regDisplay = TextEditingController();

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    _loginUser.dispose();
    _loginPwd.dispose();
    _regUser.dispose();
    _regPwd.dispose();
    _regDisplay.dispose();
    super.dispose();
  }

  Future<void> _doLogin() async {
    final ok = await ref.read(authControllerProvider.notifier)
        .login(_loginUser.text.trim(), _loginPwd.text);
    _afterAuth(ok);
  }

  Future<void> _doRegister() async {
    final ok = await ref.read(authControllerProvider.notifier).register(
          _regUser.text.trim(),
          _regPwd.text,
          displayName: _regDisplay.text.trim(),
        );
    _afterAuth(ok);
  }

  void _afterAuth(bool ok) {
    if (!mounted) return;
    final ctrl = ref.read(authControllerProvider);
    if (ok) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('欢迎回来，${ctrl.currentUser.displayName}')),
      );
      context.go('/home');
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(ctrl.lastError ?? '操作失败')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authControllerProvider);
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text('登录 / 注册'),
        bottom: TabBar(
          controller: _tabController,
          tabs: const [Tab(text: '登录'), Tab(text: '注册')],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: [
          _buildLoginForm(auth.loading),
          _buildRegisterForm(auth.loading),
        ],
      ),
    );
  }

  Widget _buildLoginForm(bool loading) {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        children: [
          TextField(
            controller: _loginUser,
            decoration: const InputDecoration(labelText: '用户名'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _loginPwd,
            obscureText: true,
            decoration: const InputDecoration(labelText: '密码'),
          ),
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              onPressed: loading ? null : _doLogin,
              child: Text(loading ? '登录中…' : '登录'),
            ),
          ),
          const SizedBox(height: 12),
          TextButton(
            onPressed: () => context.go('/home'),
            child: const Text('暂不登录，继续以演示用户体验'),
          ),
        ],
      ),
    );
  }

  Widget _buildRegisterForm(bool loading) {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        children: [
          TextField(
            controller: _regUser,
            decoration: const InputDecoration(labelText: '用户名（3-32 位）'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _regPwd,
            obscureText: true,
            decoration: const InputDecoration(labelText: '密码（6-64 位）'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _regDisplay,
            decoration: const InputDecoration(labelText: '展示名（可选）'),
          ),
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              onPressed: loading ? null : _doRegister,
              child: Text(loading ? '注册中…' : '注册并登录'),
            ),
          ),
          const SizedBox(height: 12),
          const Text(
            '认证仅作演示用途，密码采用 BCrypt 哈希存储，默认 24 小时 JWT。',
            style: TextStyle(fontSize: 12, color: AppColors.inkSoft),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }
}
