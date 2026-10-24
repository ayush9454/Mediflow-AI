import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mediflow_ai/app.dart';
import 'package:mediflow_ai/core/config/app_config.dart';
import 'package:mediflow_ai/core/contracts/contracts.g.dart';
import 'package:mediflow_ai/core/routing/app_router.dart';
import 'package:mediflow_ai/features/auth/preview_controller.dart';
import 'package:mediflow_ai/features/auth/session.dart';
import 'package:mediflow_ai/features/reports/report_screen.dart';
import 'result_api_test.dart' show fixture, resultReport;
import 'evidence_screen_test.dart' show jsonResponse;
import 'report_workflow_test.dart' show DeviceFiles;

class SeededGateway implements SessionGateway {
  SeededGateway(this.role);
  final Role role;
  String hospitalId = 'hospital_demo';
  @override
  Future<IdentityToken> signIn(String email, String password) async =>
      IdentityToken('verified', DateTime.now().add(const Duration(hours: 1)));
  @override
  Future<Account> account(String token) async => Account(
    uid: role.value,
    hospitalId: hospitalId,
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
  testWidgets(
    'result route clears clinical content on logout and denies anonymous navigation',
    (tester) async {
      final scope = ProviderContainer(
        overrides: [
          appConfigProvider.overrideWithValue(
            const AppConfig(apiBaseUrl: null, enableRolePreview: false),
          ),
          sessionGatewayProvider.overrideWithValue(SeededGateway(Role.doctor)),
          reportPlatformProvider.overrideWithValue(DeviceFiles()),
          reportHttpClientFactoryProvider.overrideWithValue(
            () => MockClient((request) async {
              if (request.url.path.endsWith('/result')) {
                return jsonResponse({
                  'schemaVersion': '1.0',
                  'kind': 'draft',
                  'draft': fixture('analysis'),
                  'approved': null,
                });
              }
              return jsonResponse({
                ...resultReport().toJson(),
                'hospitalId': 'hospital_demo',
                'assignedDoctorId': 'doctor',
              });
            }),
          ),
        ],
      );
      addTearDown(scope.dispose);
      await scope
          .read(sessionProvider.notifier)
          .signIn('synthetic@example.test', 'synthetic');
      await tester.pumpWidget(
        UncontrolledProviderScope(container: scope, child: const MediFlowApp()),
      );
      await tester.pumpAndSettle();
      scope.read(appRouterProvider).push('/results/report_1');
      await tester.pumpAndSettle();
      expect(find.text('AI candidate · not approved'), findsOneWidget);
      scope.read(sessionProvider.notifier).signOut();
      await tester.pumpAndSettle();
      expect(find.text('AI candidate · not approved'), findsNothing);
      expect(find.text('Sign in'), findsOneWidget);
      scope.read(appRouterProvider).go('/results/report_1');
      await tester.pumpAndSettle();
      expect(find.text('Sign in'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    },
  );
  testWidgets(
    'same user moving hospital replaces the entire protected reports controller',
    (tester) async {
      final gateway = SeededGateway(Role.patient);
      final owners = <String>[];
      final scope = ProviderContainer(
        overrides: [
          appConfigProvider.overrideWithValue(
            const AppConfig(apiBaseUrl: null, enableRolePreview: false),
          ),
          sessionGatewayProvider.overrideWithValue(gateway),
          reportPlatformProvider.overrideWithValue(DeviceFiles()),
          reportHttpClientFactoryProvider.overrideWithValue(
            () => MockClient(
              (request) async =>
                  http.Response('{"items":[],"nextCursor":null}', 200),
            ),
          ),
        ],
      );
      addTearDown(scope.dispose);
      await scope
          .read(sessionProvider.notifier)
          .signIn('synthetic@example.test', 'synthetic');
      await tester.pumpWidget(
        UncontrolledProviderScope(container: scope, child: const MediFlowApp()),
      );
      await tester.pumpAndSettle();
      final oldController = tester
          .widget<PatientReportsPanel>(find.byType(PatientReportsPanel))
          .controller;
      owners.add(oldController.owner);
      gateway.hospitalId = 'another_hospital';
      await scope.read(sessionProvider.notifier).revalidate();
      await tester.pumpAndSettle();
      final newController = tester
          .widget<PatientReportsPanel>(find.byType(PatientReportsPanel))
          .controller;
      owners.add(newController.owner);
      expect(owners, ['hospital_demo/patient', 'another_hospital/patient']);
      expect(identical(oldController, newController), isFalse);
      expect(oldController.mounted, isFalse);
      scope.read(sessionProvider.notifier).signOut();
      await tester.pumpAndSettle();
      await tester.pumpWidget(const SizedBox());
    },
  );

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
          reportHttpClientFactoryProvider.overrideWithValue(
            () => MockClient(
              (request) async => http.Response(
                '{"schemaVersion":"1.0","items":[],"nextCursor":null}',
                200,
              ),
            ),
          ),
          reportPlatformProvider.overrideWithValue(DeviceFiles()),
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
      expect(
        find.text(
          role == Role.patient
              ? 'Your laboratory reports'
              : role == Role.doctor
              ? 'Your assigned cases'
              : 'Hospital case assignments',
        ),
        findsOneWidget,
      );
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
