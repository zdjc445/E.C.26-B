import 'package:flutter/material.dart';

enum AuthFormMode { login, register }

typedef OnSubmit = void Function(String username, String password, String? nickname);

class AuthForm extends StatefulWidget {
  final AuthFormMode mode;
  final OnSubmit onSubmit;
  final bool isLoading;

  const AuthForm({
    super.key,
    required this.mode,
    required this.onSubmit,
    this.isLoading = false,
  });

  @override
  State<AuthForm> createState() => _AuthFormState();
}

class _AuthFormState extends State<AuthForm> {
  final _usernameController = TextEditingController(text: 'alice');
  final _passwordController = TextEditingController(text: 'password123');
  final _nicknameController = TextEditingController(text: 'Alice');
  final _formKey = GlobalKey<FormState>();

  @override
  void dispose() {
    _usernameController.dispose();
    _passwordController.dispose();
    _nicknameController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Form(
      key: _formKey,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          TextFormField(
            controller: _usernameController,
            decoration: const InputDecoration(labelText: '用户名'),
            validator: (v) => (v == null || v.trim().length < 3) ? '用户名至少 3 个字符' : null,
            textInputAction: TextInputAction.next,
          ),
          const SizedBox(height: 12),
          TextFormField(
            controller: _passwordController,
            decoration: const InputDecoration(labelText: '密码'),
            obscureText: true,
            validator: (v) => (v == null || v.length < 8) ? '密码至少 8 个字符' : null,
            textInputAction: widget.mode == AuthFormMode.register ? TextInputAction.next : TextInputAction.done,
            onFieldSubmitted: widget.mode == AuthFormMode.login ? (_) => _submit() : null,
          ),
          if (widget.mode == AuthFormMode.register) ...[
            const SizedBox(height: 12),
            TextFormField(
              controller: _nicknameController,
              decoration: const InputDecoration(labelText: '昵称（选填）'),
              textInputAction: TextInputAction.done,
              onFieldSubmitted: (_) => _submit(),
            ),
          ],
          const SizedBox(height: 20),
          ElevatedButton(
            onPressed: widget.isLoading ? null : _submit,
            child: Text(widget.mode == AuthFormMode.login ? '登录' : '注册'),
          ),
        ],
      ),
    );
  }

  void _submit() {
    if (_formKey.currentState!.validate()) {
      widget.onSubmit(
        _usernameController.text.trim(),
        _passwordController.text,
        widget.mode == AuthFormMode.register ? _nicknameController.text.trim() : null,
      );
    }
  }
}
