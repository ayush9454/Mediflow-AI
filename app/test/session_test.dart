import 'dart:typed_data';
import 'package:flutter_test/flutter_test.dart';
import 'package:mediflow_ai/core/contracts/contracts.g.dart';
import 'package:mediflow_ai/features/auth/session.dart';
import 'package:mediflow_ai/core/api/api_client.dart';

class Accounts implements SessionGateway {
  Role role = Role.patient;
  bool revoked = false;
  @override
  Future<IdentityToken> signIn(String email, String password) async =>
      IdentityToken(
        'server-token',
        DateTime.now().add(const Duration(hours: 1)),
      );
  @override
  Future<Account> account(String token) async {
    if (revoked) throw Exception('denied');
    return Account(
      uid: role.value,
      hospitalId: 'hospital_demo',
      displayName: 'Synthetic',
      role: role,
      active: true,
      schemaVersion: '1.0',
    );
  }
}

class ExpiringAccount extends Accounts {
  @override
  Future<IdentityToken> signIn(String email, String password) async =>
      IdentityToken(
        'short-session',
        DateTime.now().add(const Duration(seconds: 1)),
      );
}

class OfflineAccount extends Accounts {
  bool offline = false;
  @override
  Future<Account> account(String token) async {
    if (offline) {
      throw const ApiFailure('Cannot reach the service.', retryable: true);
    }
    return super.account(token);
  }
}

void main() {
  test(
    'temporary offline resume preserves the verified session until actual expiry',
    () async {
      final gateway = OfflineAccount();
      final controller = SessionController(gateway, SensitiveCache());
      addTearDown(controller.dispose);
      await controller.signIn('synthetic@example.test', 'password');
      gateway.offline = true;
      await controller.revalidate();
      expect(controller.state.account?.role, Role.patient);
      expect(controller.state.token, isNotNull);
      gateway.offline = false;
      await controller.revalidate();
      expect(controller.state.account?.role, Role.patient);
    },
  );
  test(
    'trusted role controls session and logout wipes temporary bytes',
    () async {
      final gateway = Accounts()..role = Role.doctor;
      final cache = SensitiveCache();
      final controller = SessionController(gateway, cache);
      addTearDown(controller.dispose);
      await controller.signIn('synthetic@example.test', 'password');
      expect(controller.state.account?.role, Role.doctor);
      final bytes = Uint8List.fromList([3, 4, 5]);
      cache.put('report', bytes);
      controller.signOut();
      expect(controller.state.account, isNull);
      expect(cache.read('report'), isNull);
      expect(bytes, [0, 0, 0]);
    },
  );
  test(
    'revoked account clears session and cached clinical content on resume',
    () async {
      final gateway = Accounts();
      final cache = SensitiveCache();
      final controller = SessionController(gateway, cache);
      addTearDown(controller.dispose);
      await controller.signIn('patient@example.test', 'password');
      cache.put('report', Uint8List.fromList([9]));
      gateway.revoked = true;
      await controller.revalidate();
      expect(controller.state.account, isNull);
      expect(controller.state.message, contains('Sign in again'));
      expect(cache.read('report'), isNull);
    },
  );
  test(
    'switching accounts clears cached bytes before replacing trusted role',
    () async {
      final gateway = Accounts();
      final cache = SensitiveCache();
      final controller = SessionController(gateway, cache);
      addTearDown(controller.dispose);
      await controller.signIn('patient@example.test', 'password');
      final bytes = Uint8List.fromList([9]);
      cache.put('report', bytes);
      gateway.role = Role.administrator;
      await controller.signIn('admin@example.test', 'password');
      expect(controller.state.account?.role, Role.administrator);
      expect(bytes, [0]);
      expect(cache.read('report'), isNull);
    },
  );
  testWidgets('token expiry clears account and cache while screen stays open', (
    tester,
  ) async {
    final cache = SensitiveCache();
    final controller = SessionController(ExpiringAccount(), cache);
    addTearDown(controller.dispose);
    await controller.signIn('patient@example.test', 'password');
    cache.put('report', Uint8List.fromList([7]));
    expect(controller.state.account, isNotNull);
    await tester.pump(const Duration(seconds: 2));
    expect(controller.state.account, isNull);
    expect(controller.state.message, contains('Sign in again'));
    expect(cache.read('report'), isNull);
  });
}
