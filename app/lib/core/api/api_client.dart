import 'dart:convert';

import 'package:http/http.dart' as http;

import '../contracts/contracts.g.dart';

class ApiFailure implements Exception {
  const ApiFailure(this.message, {this.code, this.requestId});
  final String message;
  final ErrorCode? code;
  final String? requestId;

  @override
  String toString() => message;
}

class ApiClient {
  ApiClient({required this.baseUrl, required http.Client client})
    : _client = client;
  final Uri baseUrl;
  final http.Client _client;

  Future<Account> currentAccount(String token) async {
    try {
      final response = await _client
          .get(
            baseUrl.resolve('/api/v1/me'),
            headers: {
              'Accept': 'application/json',
              'Authorization': 'Bearer $token',
            },
          )
          .timeout(const Duration(seconds: 20));
      if (response.statusCode != 200) {
        throw const ApiFailure('Account access is unavailable. Sign in again.');
      }
      return Account.fromJson(
        jsonDecode(response.body) as Map<String, dynamic>,
      );
    } on ApiFailure {
      rethrow;
    } catch (_) {
      throw const ApiFailure(
        'Account services are unavailable. Try again shortly.',
      );
    }
  }

  Future<HealthResponse> liveness() async {
    try {
      final response = await _client
          .get(
            baseUrl.resolve('/health/live'),
            headers: {'Accept': 'application/json'},
          )
          .timeout(const Duration(seconds: 15));
      final payload = jsonDecode(response.body);
      if (payload is! Map<String, dynamic>) {
        throw const FormatException('Expected an object');
      }
      if (response.statusCode != 200) {
        final error = ErrorResponse.fromJson(payload).error;
        throw ApiFailure(
          'The service is temporarily unavailable.',
          code: error.code,
          requestId: error.requestId,
        );
      }
      final result = HealthResponse.fromJson(payload);
      if (result.service != 'mediflow-api' ||
          result.status != 'ok' ||
          !result.syntheticDataOnly) {
        throw const FormatException('Unexpected service identity');
      }
      return result;
    } on ApiFailure {
      rethrow;
    } on FormatException {
      throw const ApiFailure('The service returned an unreadable status.');
    } on TypeError {
      throw const ApiFailure('The service returned an unreadable status.');
    } catch (_) {
      throw const ApiFailure(
        'The service could not be reached. Try again shortly.',
      );
    }
  }
}
