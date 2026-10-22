import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;

import '../../core/api/api_client.dart';
import '../../core/config/app_config.dart';
import '../../core/contracts/contracts.g.dart';

class IdentityToken {
  const IdentityToken(this.value, this.expiresAt);
  final String value;
  final DateTime expiresAt;
}

abstract interface class SessionGateway {
  Future<IdentityToken> signIn(String email, String password);
  Future<Account> account(String token);
}

/// Firebase REST email/password sign-in. Credentials and tokens stay in memory.
class FirebaseSessionGateway implements SessionGateway {
  FirebaseSessionGateway(this.config, this.client);
  final AppConfig config;
  final http.Client client;

  @override
  Future<IdentityToken> signIn(String email, String password) async {
    if (config.firebaseApiKey.isEmpty || config.apiBaseUrl == null) {
      throw const ApiFailure('Account access is not configured.');
    }
    final response = await client
        .post(
          Uri.https(
            'identitytoolkit.googleapis.com',
            '/v1/accounts:signInWithPassword',
            {'key': config.firebaseApiKey},
          ),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({
            'email': email.trim(),
            'password': password,
            'returnSecureToken': true,
          }),
        )
        .timeout(const Duration(seconds: 20));
    if (response.statusCode != 200) {
      throw const ApiFailure(
        'Sign-in failed. Check your account details and try again.',
      );
    }
    final data = jsonDecode(response.body) as Map<String, dynamic>;
    final seconds = int.parse(data['expiresIn'] as String);
    final token = data['idToken'] as String;
    if (seconds <= 0 || token.isEmpty) {
      throw const FormatException('Invalid session');
    }
    return IdentityToken(token, DateTime.now().add(Duration(seconds: seconds)));
  }

  @override
  Future<Account> account(String token) => ApiClient(
    baseUrl: config.apiBaseUrl!,
    client: client,
  ).currentAccount(token);
}

/// The single temporary clinical cache. Consumers must never persist bearer data.
class SensitiveCache {
  final Map<String, Uint8List> _bytes = {};
  void put(String key, Uint8List bytes) {
    final previous = _bytes.remove(key);
    previous?.fillRange(0, previous.length, 0);
    _bytes[key] = bytes;
  }

  Uint8List? read(String key) => _bytes[key];
  void clear() {
    for (final value in _bytes.values) {
      value.fillRange(0, value.length, 0);
    }
    _bytes.clear();
  }
}

class SessionState {
  const SessionState({
    this.account,
    this.token,
    this.busy = false,
    this.message,
  });
  final Account? account;
  final IdentityToken? token;
  final bool busy;
  final String? message;
}

class SessionController extends StateNotifier<SessionState> {
  SessionController(this.gateway, this.cache) : super(const SessionState());
  final SessionGateway gateway;
  final SensitiveCache cache;
  Timer? _expiry;
  int _generation = 0;

  Future<void> signIn(String email, String password) async {
    signOut();
    final generation = _generation;
    state = const SessionState(busy: true);
    try {
      final token = await gateway.signIn(email, password);
      final account = await gateway.account(token.value);
      if (!mounted || generation != _generation) return;
      if (!account.active || !token.expiresAt.isAfter(DateTime.now())) {
        throw const ApiFailure('Account access is unavailable.');
      }
      state = SessionState(account: account, token: token);
      _expiry = Timer(token.expiresAt.difference(DateTime.now()), expire);
    } catch (error) {
      if (!mounted || generation != _generation) return;
      state = SessionState(
        message: error is ApiFailure
            ? error.message
            : 'Sign-in could not be completed. Try again shortly.',
      );
    }
  }

  Future<void> revalidate() async {
    final token = state.token;
    if (token == null) return;
    if (!token.expiresAt.isAfter(DateTime.now())) {
      expire();
      return;
    }
    final generation = _generation;
    try {
      final account = await gateway.account(token.value);
      if (!mounted || generation != _generation) return;
      if (!account.active) {
        expire();
        return;
      }
      final prior = state.account;
      if (prior?.uid != account.uid ||
          prior?.role != account.role ||
          prior?.hospitalId != account.hospitalId) {
        cache.clear();
      }
      state = SessionState(account: account, token: token);
    } catch (_) {
      if (mounted && generation == _generation) expire();
    }
  }

  void signOut({String? message}) {
    _generation++;
    _expiry?.cancel();
    _expiry = null;
    cache.clear();
    state = SessionState(message: message);
  }

  void expire() => signOut(message: 'Your session ended. Sign in again.');
  @override
  void dispose() {
    _generation++;
    _expiry?.cancel();
    cache.clear();
    super.dispose();
  }
}

final sensitiveCacheProvider = Provider<SensitiveCache>((ref) {
  final cache = SensitiveCache();
  ref.onDispose(cache.clear);
  return cache;
});
final sessionGatewayProvider = Provider<SessionGateway>((ref) {
  final client = http.Client();
  ref.onDispose(client.close);
  return FirebaseSessionGateway(ref.watch(appConfigProvider), client);
});
final sessionProvider = StateNotifierProvider<SessionController, SessionState>(
  (ref) => SessionController(
    ref.watch(sessionGatewayProvider),
    ref.watch(sensitiveCacheProvider),
  ),
);
