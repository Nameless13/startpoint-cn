import 'package:flutter/material.dart';

import '../models/player.dart';
import '../services/auth_service.dart';

class LoginPage extends StatefulWidget {
  const LoginPage({required this.onLoggedIn, super.key});

  final ValueChanged<Player> onLoggedIn;

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final _username = TextEditingController(text: 'testplayer');
  final _password = TextEditingController(text: '123456');
  final _service = AuthService();
  bool _loading = false;
  String? _error;

  @override
  void dispose() {
    _username.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _login() async {
    if (_username.text.trim().isEmpty || _password.text.isEmpty) {
      setState(() => _error = '请输入账号和密码');
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final player = await _service.login(_username.text.trim(), _password.text);
      if (mounted) widget.onLoggedIn(player);
    } on AuthException catch (error) {
      setState(() => _error = _message(error.code));
    } catch (_) {
      setState(() => _error = '网络连接失败，请检查服务器地址和网络');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  String _message(String code) => switch (code) {
        'missing_credentials' => '请输入账号和密码',
        'invalid_credentials' => '账号或密码错误',
        'account_disabled' => '账号已被停用',
        'too_many_attempts' => '尝试次数过多，请稍后再试',
        _ => code,
      };

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 380),
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Card(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text('世界弹射物语', style: Theme.of(context).textTheme.headlineSmall),
                    const SizedBox(height: 24),
                    TextField(controller: _username, decoration: const InputDecoration(labelText: '账号', prefixIcon: Icon(Icons.person_outline))),
                    const SizedBox(height: 12),
                    TextField(controller: _password, obscureText: true, onSubmitted: (_) => _login(), decoration: const InputDecoration(labelText: '密码', prefixIcon: Icon(Icons.lock_outline))),
                    if (_error != null) ...[
                      const SizedBox(height: 12),
                      Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
                    ],
                    const SizedBox(height: 20),
                    SizedBox(
                      width: double.infinity,
                      child: FilledButton(
                        onPressed: _loading ? null : _login,
                        child: _loading ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)) : const Text('登录'),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}