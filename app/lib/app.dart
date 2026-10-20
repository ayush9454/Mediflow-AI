import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/routing/app_router.dart';
import 'core/theme/app_theme.dart';

class MediFlowApp extends ConsumerWidget {
  const MediFlowApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) => MaterialApp.router(
    title: 'MediFlow AI',
    debugShowCheckedModeBanner: false,
    theme: buildAppTheme(),
    routerConfig: ref.watch(appRouterProvider),
  );
}
