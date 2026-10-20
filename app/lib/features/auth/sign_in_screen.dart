import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api/providers.dart';
import '../../core/config/app_config.dart';
import '../../core/contracts/contracts.g.dart';
import '../../core/theme/app_theme.dart';
import 'preview_controller.dart';

class SignInScreen extends ConsumerWidget {
  const SignInScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) => Scaffold(
    body: SafeArea(
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 560),
          child: ListView(
            padding: const EdgeInsets.all(24),
            children: [
              const SizedBox(height: 18),
              Row(
                children: [
                  Container(
                    width: 48,
                    height: 48,
                    decoration: BoxDecoration(
                      color: brandTeal,
                      borderRadius: BorderRadius.circular(15),
                    ),
                    child: const Icon(
                      Icons.health_and_safety_outlined,
                      color: Colors.white,
                    ),
                  ),
                  const SizedBox(width: 12),
                  const Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'MediFlow AI',
                          style: TextStyle(
                            fontSize: 22,
                            fontWeight: FontWeight.w700,
                            color: ink,
                          ),
                        ),
                        Text(
                          'Reports, clearly connected.',
                          style: TextStyle(color: mutedInk),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 36),
              Text(
                'A clearer path\nfrom report to review.',
                style: Theme.of(context).textTheme.headlineLarge,
              ),
              const SizedBox(height: 14),
              const Text(
                'Organize laboratory reports, inspect their evidence, and keep every review connected to its source.',
              ),
              const SizedBox(height: 24),
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: paleTeal,
                  borderRadius: BorderRadius.circular(14),
                ),
                child: const Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(Icons.science_outlined, color: brandTeal),
                    SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        'College demonstration · synthetic reports only',
                        style: TextStyle(
                          color: brandTeal,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 24),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Your workspace',
                        style: Theme.of(context).textTheme.titleLarge,
                      ),
                      const SizedBox(height: 6),
                      const Text(
                        'Use the account provided by your hospital administrator.',
                      ),
                      const SizedBox(height: 20),
                      const TextField(
                        enabled: false,
                        decoration: InputDecoration(
                          labelText: 'Email address',
                          prefixIcon: Icon(Icons.mail_outline),
                        ),
                      ),
                      const SizedBox(height: 12),
                      const TextField(
                        enabled: false,
                        obscureText: true,
                        decoration: InputDecoration(
                          labelText: 'Password',
                          prefixIcon: Icon(Icons.lock_outline),
                        ),
                      ),
                      const SizedBox(height: 16),
                      const FilledButton(
                        onPressed: null,
                        child: Text('Sign in'),
                      ),
                      const SizedBox(height: 12),
                      const Text(
                        'Account access is being set up. Sign-in is not available in this foundation build.',
                      ),
                    ],
                  ),
                ),
              ),
              if (ref.watch(appConfigProvider).enableRolePreview) ...[
                const SizedBox(height: 28),
                Text(
                  'Explore the interface',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: 6),
                const Text(
                  'Debug previews only. These do not sign you in or load patient data.',
                ),
                const SizedBox(height: 14),
                for (final role in Role.values)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: Card(
                      child: ListTile(
                        contentPadding: const EdgeInsets.symmetric(
                          horizontal: 18,
                          vertical: 5,
                        ),
                        leading: Icon(switch (role) {
                          Role.patient => Icons.folder_shared_outlined,
                          Role.doctor => Icons.fact_check_outlined,
                          Role.administrator => Icons.hub_outlined,
                        }, color: brandTeal),
                        title: Text(role.label),
                        subtitle: Text(switch (role) {
                          Role.patient =>
                            'Upload reports and view approved results',
                          Role.doctor =>
                            'Inspect evidence and review assigned cases',
                          Role.administrator =>
                            'Assign cases and follow their progress',
                        }),
                        trailing: const Icon(Icons.arrow_forward, size: 20),
                        onTap: () {
                          ref.read(previewRoleProvider.notifier).open(role);
                          context.go('/preview/${role.value}');
                        },
                      ),
                    ),
                  ),
              ],
              const SizedBox(height: 20),
              const _ServiceStatus(),
              const SizedBox(height: 16),
            ],
          ),
        ),
      ),
    ),
  );
}

class _ServiceStatus extends ConsumerWidget {
  const _ServiceStatus();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final label = ref
        .watch(backendStatusProvider)
        .when(
          data: (health) => health == null
              ? 'Backend connection not configured'
              : 'API reachable · clinical services not connected yet',
          loading: () => 'Checking service connection…',
          error: (_, __) => 'Service unavailable · it may be starting',
        );
    return Row(
      children: [
        const Icon(Icons.cloud_outlined, color: mutedInk, size: 19),
        const SizedBox(width: 8),
        Expanded(child: Text(label, style: const TextStyle(fontSize: 12))),
        IconButton(
          tooltip: 'Check service connection',
          onPressed: () => ref.invalidate(backendStatusProvider),
          icon: const Icon(Icons.refresh, size: 19),
        ),
      ],
    );
  }
}
