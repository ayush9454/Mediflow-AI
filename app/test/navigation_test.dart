import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mediflow_ai/app.dart';
import 'package:mediflow_ai/core/config/app_config.dart';
import 'package:mediflow_ai/core/contracts/contracts.g.dart';
import 'package:mediflow_ai/core/routing/app_router.dart';
import 'package:mediflow_ai/features/auth/preview_controller.dart';
import 'package:mediflow_ai/features/auth/session.dart';

class SeededGateway implements SessionGateway {
  SeededGateway(this.role);
  final Role role;
  @override
  Future<IdentityToken> signIn(String email, String password) async =>
      IdentityToken('verified', DateTime.now().add(const Duration(hours: 1)));
  @override
  Future<Account> account(String token) async => Account(
    uid: role.value,
    hospitalId: 'hospital_demo',
    displayName: 'Synthetic account',
    role: role,
    active: true,
    schemaVersion: '1.0',
  );
}

ProviderContainer container({bool preview = true}) => ProviderContainer(
  overrides: [
    appConfigProvider.overrideWithValue(
      AppConfig(apiBaseUrl: null, enableRolePreview: preview),
    ),
  ],
);

void main() {
  for (final role in Role.values) {
    testWidgets('signed in ${role.value} reaches only its trusted role shell', (
      tester,
    ) async {
      final scope = ProviderContainer(
        overrides: [
          appConfigProvider.overrideWithValue(
            const AppConfig(apiBaseUrl: null, enableRolePreview: false),
          ),
          sessionGatewayProvider.overrideWithValue(SeededGateway(role)),
        ],
      );
      addTearDown(scope.dispose);
      await tester.pumpWidget(
        UncontrolledProviderScope(container: scope, child: const MediFlowApp()),
      );
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byType(TextField).at(0),
        'seeded@example.test',
      );
      await tester.enterText(
        find.byType(TextField).at(1),
        'synthetic-password',
      );
      await tester.testTextInput.receiveAction(TextInputAction.done);
      await tester.pumpAndSettle();
      expect(find.text('${role.label} workspace'), findsOneWidget);
      scope
          .read(appRouterProvider)
          .go('/${role == Role.patient ? 'administrator' : 'patient'}');
      await tester.pumpAndSettle();
      expect(
        scope.read(appRouterProvider).routeInformationProvider.value.uri.path,
        '/${role.value}',
      );
      await tester.tap(find.text('Sign out'));
      await tester.pumpAndSettle();
      expect(find.text('Sign in'), findsOneWidget);
      expect(find.text('${role.label} workspace'), findsNothing);
    });
  }

  testWidgets(
    'preview navigation is explicitly labeled and does not authenticate',
    (tester) async {
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final scope = container();
      addTearDown(scope.dispose);
      await tester.pumpWidget(
        UncontrolledProviderScope(container: scope, child: const MediFlowApp()),
      );
      await tester.pumpAndSettle();
      expect(find.text('Sign in'), findsOneWidget);
      for (final field in tester.widgetList<TextField>(
        find.byType(TextField),
      )) {
        expect(field.enabled, isTrue);
      }
      await tester.scrollUntilVisible(
        find.text('Patient'),
        200,
        scrollable: find
            .descendant(
              of: find.byType(ListView),
              matching: find.byType(Scrollable),
            )
            .first,
      );
      await tester.tap(find.text('Patient'));
      await tester.pumpAndSettle();
      expect(find.text('Patient workspace'), findsOneWidget);
      expect(
        find.text('Interface preview · no sign-in or patient data'),
        findsOneWidget,
      );
      scope.read(appRouterProvider).go('/doctor');
      await tester.pumpAndSettle();
      expect(find.text('Sign in'), findsOneWidget);
      expect(find.text('Doctor workspace'), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'disabled previews cannot be opened through navigation or controller',
    (tester) async {
      final scope = container(preview: false);
      addTearDown(scope.dispose);
      await tester.pumpWidget(
        UncontrolledProviderScope(container: scope, child: const MediFlowApp()),
      );
      await tester.pumpAndSettle();
      expect(find.text('Explore the interface'), findsNothing);
      expect(
        () => scope.read(previewRoleProvider.notifier).open(Role.administrator),
        throwsStateError,
      );
      scope.read(appRouterProvider).go('/preview/administrator');
      await tester.pumpAndSettle();
      expect(find.text('Administrator workspace'), findsNothing);
      expect(
        scope.read(appRouterProvider).routeInformationProvider.value.uri.path,
        '/sign-in',
      );
    },
  );

  testWidgets(
    'a patient preview cannot deep-link into the administrator preview',
    (tester) async {
      final scope = container();
      addTearDown(scope.dispose);
      await tester.pumpWidget(
        UncontrolledProviderScope(container: scope, child: const MediFlowApp()),
      );
      scope.read(previewRoleProvider.notifier).open(Role.patient);
      scope.read(appRouterProvider).go('/preview/administrator');
      await tester.pumpAndSettle();
      expect(find.text('Administrator workspace'), findsNothing);
      expect(
        scope.read(appRouterProvider).routeInformationProvider.value.uri.path,
        '/sign-in',
      );
    },
  );
}
