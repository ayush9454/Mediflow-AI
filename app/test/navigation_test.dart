import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mediflow_ai/app.dart';
import 'package:mediflow_ai/core/config/app_config.dart';
import 'package:mediflow_ai/core/contracts/contracts.g.dart';
import 'package:mediflow_ai/core/routing/app_router.dart';
import 'package:mediflow_ai/features/auth/preview_controller.dart';

ProviderContainer container({bool preview = true}) => ProviderContainer(
  overrides: [
    appConfigProvider.overrideWithValue(
      AppConfig(apiBaseUrl: null, enableRolePreview: preview),
    ),
  ],
);

void main() {
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
        expect(field.enabled, isFalse);
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
