import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/contracts/contracts.g.dart';
import '../../core/theme/app_theme.dart';
import '../auth/preview_controller.dart';

class WorkspaceScreen extends ConsumerStatefulWidget {
  const WorkspaceScreen({required this.role, super.key});
  final Role role;

  @override
  ConsumerState<WorkspaceScreen> createState() => _WorkspaceScreenState();
}

class _WorkspaceScreenState extends ConsumerState<WorkspaceScreen> {
  int selectedTab = 0;

  @override
  Widget build(BuildContext context) {
    final role = widget.role;
    final tabs = switch (role) {
      Role.patient => ['Reports', 'History', 'Account'],
      Role.doctor => ['Assigned cases', 'Reviews', 'Account'],
      Role.administrator => ['Cases', 'Doctors', 'Account'],
    };
    return Scaffold(
      appBar: AppBar(
        title: const Text(
          'MediFlow AI',
          style: TextStyle(fontWeight: FontWeight.w700),
        ),
        actions: [
          TextButton(
            onPressed: () {
              ref.read(previewRoleProvider.notifier).close();
              context.go('/sign-in');
            },
            child: const Text('Leave preview'),
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 720),
            child: ListView(
              padding: const EdgeInsets.all(24),
              children: [
                Container(
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: paleTeal,
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: const Text(
                    'Interface preview · no sign-in or patient data',
                    style: TextStyle(
                      color: brandTeal,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
                const SizedBox(height: 28),
                Text(
                  '${role.label} workspace',
                  style: Theme.of(context).textTheme.headlineMedium,
                ),
                const SizedBox(height: 8),
                Text(switch (role) {
                  Role.patient => 'Your reports, with every review in view.',
                  Role.doctor => 'Source evidence beside every review.',
                  Role.administrator => 'Clear assignments. Visible progress.',
                }),
                const SizedBox(height: 26),
                if (selectedTab == 2)
                  const _Panel(
                    icon: Icons.person_outline,
                    title: 'No signed-in account',
                    body:
                        'This is an interface preview. Account details will appear after secure sign-in is connected.',
                  )
                else if (selectedTab == 1)
                  _Panel(
                    icon: role == Role.administrator
                        ? Icons.badge_outlined
                        : Icons.history,
                    title: role == Role.administrator
                        ? 'Doctor directory'
                        : tabs[1],
                    body: role == Role.administrator
                        ? 'Active doctor profiles and assignment options will appear here. No directory data is loaded.'
                        : 'Completed activity will appear here when the workflow is connected. No records are loaded.',
                  )
                else ...[
                  _Panel(
                    icon: switch (role) {
                      Role.patient => Icons.upload_file_outlined,
                      Role.doctor => Icons.fact_check_outlined,
                      Role.administrator => Icons.assignment_ind_outlined,
                    },
                    title: switch (role) {
                      Role.patient => 'Your report workspace',
                      Role.doctor => 'Your assigned cases',
                      Role.administrator => 'Case assignment workspace',
                    },
                    body: switch (role) {
                      Role.patient =>
                        'Upload a synthetic laboratory PDF, follow its progress, and view results after doctor approval.',
                      Role.doctor =>
                        'Assigned laboratory cases will appear here with extracted fields, validation flags, and the original PDF.',
                      Role.administrator =>
                        'Assign each case to an eligible doctor and follow its status. Clinical documents remain restricted.',
                    },
                  ),
                  const SizedBox(height: 20),
                  if (role == Role.patient) ...[
                    FilledButton.icon(
                      onPressed: null,
                      icon: const Icon(Icons.add),
                      label: const Text('Upload laboratory PDF'),
                    ),
                    const SizedBox(height: 10),
                    const Text(
                      'Upload is not connected yet. Supported scope: English PDFs, up to 10 pages and 10 MB.',
                    ),
                    const SizedBox(height: 26),
                  ],
                  Text(
                    'From document to reviewed record',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 14),
                  const _Step(
                    number: '01',
                    title: 'Upload securely',
                    detail: 'One synthetic report creates one case.',
                  ),
                  const _Step(
                    number: '02',
                    title: 'Extract with evidence',
                    detail: 'Keep printed values linked to their source page.',
                  ),
                  const _Step(
                    number: '03',
                    title: 'Review and approve',
                    detail:
                        'A doctor checks the result before the patient sees it.',
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: selectedTab,
        onDestinationSelected: (index) => setState(() => selectedTab = index),
        destinations: [
          NavigationDestination(
            icon: const Icon(Icons.folder_outlined),
            label: tabs[0],
          ),
          NavigationDestination(
            icon: Icon(
              role == Role.administrator
                  ? Icons.groups_outlined
                  : Icons.history,
            ),
            label: tabs[1],
          ),
          NavigationDestination(
            icon: const Icon(Icons.person_outline),
            label: tabs[2],
          ),
        ],
      ),
    );
  }
}

class _Panel extends StatelessWidget {
  const _Panel({required this.icon, required this.title, required this.body});
  final IconData icon;
  final String title;
  final String body;

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: paleTeal,
              borderRadius: BorderRadius.circular(14),
            ),
            child: Icon(icon, color: brandTeal, size: 30),
          ),
          const SizedBox(height: 20),
          Text(title, style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 10),
          Text(body),
          const SizedBox(height: 16),
          const Text(
            'No live records loaded',
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w600,
              color: mutedInk,
            ),
          ),
        ],
      ),
    ),
  );
}

class _Step extends StatelessWidget {
  const _Step({
    required this.number,
    required this.title,
    required this.detail,
  });
  final String number;
  final String title;
  final String detail;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 20),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 36,
          height: 36,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: paleTeal,
            borderRadius: BorderRadius.circular(10),
          ),
          child: Text(
            number,
            style: const TextStyle(
              color: brandTeal,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 3),
              Text(detail),
            ],
          ),
        ),
      ],
    ),
  );
}
