import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/material.dart';

import 'package:flutter_worldflipper/pages/login_page.dart';

void main() {
  testWidgets('renders the research client shell', (tester) async {
    await tester.pumpWidget(
      MaterialApp(home: LoginPage(onLoggedIn: (_) {})),
    );
    await tester.pump();

    expect(find.text('世界弹射物语'), findsOneWidget);
    expect(find.text('登录'), findsOneWidget);
  });
}
