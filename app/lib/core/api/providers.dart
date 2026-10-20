import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import '../contracts/contracts.g.dart';
import 'api_client.dart';

final apiClientProvider = Provider<ApiClient?>((ref) {
  final url = ref.watch(appConfigProvider).apiBaseUrl;
  if (url == null) return null;
  final client = http.Client();
  ref.onDispose(client.close);
  return ApiClient(baseUrl: url, client: client);
});

final backendStatusProvider = FutureProvider<HealthResponse?>((ref) async {
  return ref.watch(apiClientProvider)?.liveness();
});
