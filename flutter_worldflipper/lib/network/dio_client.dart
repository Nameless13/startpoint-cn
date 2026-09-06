import 'package:dio/dio.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

class DioClient {
  DioClient._();

  // 本地开发使用 127.0.0.1:8001
  static const String baseUrl = 'http://127.0.0.1:8001';
  static String? sessionToken;
  static final Dio instance = Dio(
    BaseOptions(
      baseUrl: baseUrl,
      connectTimeout: const Duration(seconds: 30),
      receiveTimeout: const Duration(seconds: 30),
      sendTimeout: const Duration(seconds: 30),
      headers: {'Content-Type': 'application/json'},
    ),
  )..interceptors.addAll([
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          String? token = sessionToken;
          try {
            final preferences = await SharedPreferences.getInstance();
            token = preferences.getString('auth_token') ?? token;
          } on MissingPluginException {
            // Requires a full restart after adding a platform plugin.
          }
          if (token != null && token.isNotEmpty) {
            options.headers['Authorization'] = 'Bearer $token';
          }
          handler.next(options);
        },
      ),
      LogInterceptor(requestBody: true, responseBody: false),
    ]);
}
