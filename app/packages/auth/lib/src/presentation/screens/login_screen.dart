import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:app_core/app_core.dart';
import '../providers/auth_provider.dart';
import '../widgets/auth_form.dart';

/// Combined login / register screen.
class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  bool _isLogin = true;

  @override
  void initState() {
    super.initState();
    Future.microtask(() => ref.read(authProvider.notifier).restoreSession());
  }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authProvider);
    final apiBaseUrl = ref.watch(apiBaseUrlProvider);

    ref.listen<AuthState>(authProvider, (prev, next) {
      if (next.status == AuthStatus.authenticated) {
        context.go('/home');
      }
      if (next.error != null) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(next.error!), backgroundColor: AppColors.warn),
        );
        ref.read(authProvider.notifier).clearError();
      }
    });

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 400),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Container(
                        width: 46,
                        height: 46,
                        decoration: BoxDecoration(
                          color: AppColors.accent,
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: const Center(
                          child: Text('EC',
                              style: TextStyle(
                                  color: Colors.white,
                                  fontWeight: FontWeight.w900)),
                        ),
                      ),
                      const SizedBox(width: 12),
                      const Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('E.C.26-B',
                              style: TextStyle(
                                  fontSize: 20, fontWeight: FontWeight.w800)),
                          Text('购物决策工作台',
                              style: TextStyle(
                                  fontSize: 13, color: AppColors.inkSoft)),
                        ],
                      ),
                    ],
                  ),
                  const SizedBox(height: 32),
                  Row(
                    children: [
                      Expanded(
                        child: _TabButton(
                          label: '登录',
                          active: _isLogin,
                          onTap: () => setState(() => _isLogin = true),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: _TabButton(
                          label: '注册',
                          active: !_isLogin,
                          onTap: () => setState(() => _isLogin = false),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 20),
                  _isLogin
                      ? AuthForm(
                          mode: AuthFormMode.login,
                          onSubmit: (username, password, nickname) {
                            ref
                                .read(authProvider.notifier)
                                .login(username, password);
                          },
                          isLoading: authState.status == AuthStatus.initial,
                        )
                      : AuthForm(
                          mode: AuthFormMode.register,
                          onSubmit: (username, password, nickname) {
                            ref
                                .read(authProvider.notifier)
                                .register(username, password, nickname);
                          },
                          isLoading: authState.status == AuthStatus.initial,
                        ),
                  const SizedBox(height: 16),
                  Text(
                    '连接后端：$apiBaseUrl',
                    textAlign: TextAlign.center,
                    style:
                        const TextStyle(fontSize: 12, color: AppColors.inkSoft),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _TabButton extends StatelessWidget {
  final String label;
  final bool active;
  final VoidCallback onTap;

  const _TabButton(
      {required this.label, required this.active, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return OutlinedButton(
      onPressed: onTap,
      style: OutlinedButton.styleFrom(
        backgroundColor: active ? AppColors.accent : Colors.white,
        foregroundColor: active ? Colors.white : AppColors.inkMain,
        side: BorderSide(color: active ? AppColors.accent : AppColors.line),
      ),
      child: Text(label),
    );
  }
}
