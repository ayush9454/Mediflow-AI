import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/auth/preview_controller.dart';
import '../../features/auth/session.dart';
import '../../features/auth/sign_in_screen.dart';
import '../../features/workspace/workspace_screen.dart';
import '../../features/workspace/workflow_screen.dart';
import '../../features/reports/evidence_host.dart';
import '../config/app_config.dart';
import '../contracts/contracts.g.dart';

final appRouterProvider = Provider<GoRouter>((ref) {
  final refresh = ValueNotifier(0);
  ref.listen(previewRoleProvider, (_, __) => refresh.value++);
  ref.listen(sessionProvider, (_, __) => refresh.value++);
  final router = GoRouter(
    initialLocation: '/sign-in',
    refreshListenable: refresh,
    redirect: (context, state) {
      final path = state.uri.path;
      final account = ref.read(sessionProvider).account;
      if (path.startsWith('/review/')) {
        if (account == null) return '/sign-in';
        if (account.role != Role.doctor) return '/${account.role.value}';
      }
      if (path.startsWith('/results/')) {
        if (account == null) return '/sign-in';
        if (account.role == Role.administrator) return '/administrator';
      }
      if (path == '/' || path == '/sign-in') {
        if (account != null) return '/${account.role.value}';
        return path == '/' ? '/sign-in' : null;
      }
      if (path.startsWith('/preview/')) {
        final role = ref.read(previewRoleProvider);
        if (!ref.read(appConfigProvider).enableRolePreview ||
            role == null ||
            path != '/preview/${role.value}') {
          return '/sign-in';
        }
      }
      // A selected preview role never authenticates a real protected route.
      if (Role.values.any((role) => path == '/${role.value}')) {
        if (account == null) return '/sign-in';
        if (path != '/${account.role.value}') return '/${account.role.value}';
      }
      return null;
    },
    routes: [
      GoRoute(path: '/', redirect: (_, __) => '/sign-in'),
      GoRoute(path: '/sign-in', builder: (_, __) => const SignInScreen()),
      GoRoute(
        path: '/results/:reportId',
        builder: (_, state) =>
            EvidenceResultHost(reportId: state.pathParameters['reportId']!),
      ),
      GoRoute(
        path: '/review/:reportId',
        builder: (_, state) =>
            WorkflowHost(reportId: state.pathParameters['reportId']!),
      ),
      for (final role in Role.values)
        GoRoute(
          path: '/preview/${role.value}',
          builder: (_, __) => WorkspaceScreen(role: role),
        ),
      for (final role in Role.values)
        GoRoute(
          path: '/${role.value}',
          builder: (_, __) => WorkspaceScreen(role: role, preview: false),
        ),
    ],
  );
  ref.onDispose(() {
    router.dispose();
    refresh.dispose();
  });
  return router;
});
