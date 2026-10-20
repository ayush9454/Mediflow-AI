import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/auth/preview_controller.dart';
import '../../features/auth/sign_in_screen.dart';
import '../../features/workspace/workspace_screen.dart';
import '../config/app_config.dart';
import '../contracts/contracts.g.dart';

final appRouterProvider = Provider<GoRouter>((ref) {
  final refresh = ValueNotifier(0);
  ref.listen(previewRoleProvider, (_, __) => refresh.value++);
  final router = GoRouter(
    initialLocation: '/sign-in',
    refreshListenable: refresh,
    redirect: (context, state) {
      final path = state.uri.path;
      if (path == '/') return '/sign-in';
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
        return '/sign-in';
      }
      return null;
    },
    routes: [
      GoRoute(path: '/', redirect: (_, __) => '/sign-in'),
      GoRoute(path: '/sign-in', builder: (_, __) => const SignInScreen()),
      for (final role in Role.values)
        GoRoute(
          path: '/preview/${role.value}',
          builder: (_, __) => WorkspaceScreen(role: role),
        ),
      for (final role in Role.values)
        GoRoute(
          path: '/${role.value}',
          builder: (_, __) => const SignInScreen(),
        ),
    ],
  );
  ref.onDispose(() {
    router.dispose();
    refresh.dispose();
  });
  return router;
});
