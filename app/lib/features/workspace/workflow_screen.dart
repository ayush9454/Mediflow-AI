import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api/api_client.dart';
import '../../core/config/app_config.dart';
import '../../core/contracts/contracts.g.dart';
import '../auth/session.dart';
import '../reports/report_api.dart';
import '../reports/report_screen.dart';
import '../reviews/review_screen.dart';

/// A fresh request client and widget state for each account, role and workspace.
class WorkflowHost extends ConsumerWidget {
  const WorkflowHost({
    this.reportId,
    this.directory = false,
    this.reviews = false,
    super.key,
  });
  final String? reportId;
  final bool directory, reviews;
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final account = ref.watch(sessionProvider).account;
    if (account == null ||
        account.role == Role.patient ||
        (reportId != null && account.role != Role.doctor)) {
      return const Center(child: Text('Sign in with an authorized account.'));
    }
    return _SessionWorkflow(
      key: ValueKey(
        '${account.hospitalId}/${account.uid}/${account.role.value}/$reportId/$directory/$reviews',
      ),
      account: account,
      reportId: reportId,
      directory: directory,
      reviews: reviews,
    );
  }
}

class _SessionWorkflow extends ConsumerStatefulWidget {
  const _SessionWorkflow({
    required this.account,
    required this.reportId,
    required this.directory,
    required this.reviews,
    super.key,
  });
  final Account account;
  final String? reportId;
  final bool directory, reviews;
  @override
  ConsumerState<_SessionWorkflow> createState() => _SessionWorkflowState();
}

class _SessionWorkflowState extends ConsumerState<_SessionWorkflow> {
  late final PatientReportApi api;
  @override
  void initState() {
    super.initState();
    api = PatientReportApi(
      ref.read(appConfigProvider).apiBaseUrl ??
          Uri.parse('https://unconfigured.invalid'),
      ref.read(reportHttpClientFactoryProvider)(),
    );
  }

  String token() {
    final session = ref.read(sessionProvider);
    if (session.account?.uid != widget.account.uid ||
        session.account?.hospitalId != widget.account.hospitalId ||
        session.account?.role != widget.account.role ||
        session.token == null ||
        !session.token!.expiresAt.isAfter(DateTime.now())) {
      throw const ApiFailure(
        'Your session ended. Sign in again.',
        code: ErrorCode.unauthenticated,
      );
    }
    return session.token!.value;
  }

  @override
  Widget build(BuildContext context) => widget.reportId != null
      ? DoctorReviewScreen(
          account: widget.account,
          reportId: widget.reportId!,
          api: api,
          token: token,
          onSessionEnded: () => ref.read(sessionProvider.notifier).expire(),
        )
      : WorkflowPanel(
          account: widget.account,
          api: api,
          token: token,
          directory: widget.directory,
          reviews: widget.reviews,
          onSessionEnded: () => ref.read(sessionProvider.notifier).expire(),
        );
}

class WorkflowPanel extends StatefulWidget {
  const WorkflowPanel({
    required this.account,
    required this.api,
    required this.token,
    this.directory = false,
    this.reviews = false,
    this.onSessionEnded,
    super.key,
  });
  final Account account;
  final PatientReportApi api;
  final String Function() token;
  final bool directory, reviews;
  final VoidCallback? onSessionEnded;
  @override
  State<WorkflowPanel> createState() => _WorkflowPanelState();
}

class _WorkflowPanelState extends State<WorkflowPanel>
    with WidgetsBindingObserver {
  final cases = <CaseSummary>[];
  final doctors = <DoctorSummary>[];
  String? cursor, doctorCursor, message;
  int generation = 0;
  bool busy = false, choosing = false;
  Timer? poll;
  CaseSummary? pendingCase;
  String? pendingDoctor, pendingKey;

  bool get foreground =>
      mounted &&
      (WidgetsBinding.instance.lifecycleState == null ||
          WidgetsBinding.instance.lifecycleState == AppLifecycleState.resumed);
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    unawaited(load());
    poll = Timer.periodic(const Duration(seconds: 15), (_) {
      if (foreground &&
          TickerMode.of(context) &&
          !busy &&
          pendingCase == null &&
          !choosing) {
        unawaited(load());
      }
    });
  }

  void clear() {
    generation++;
    busy = false;
    cases.clear();
    doctors.clear();
    cursor = null;
    doctorCursor = null;
    pendingCase = null;
    pendingDoctor = null;
    pendingKey = null;
  }

  void failure(ApiFailure error) {
    setState(() {
      if ({
        ErrorCode.unauthenticated,
        ErrorCode.permissionDenied,
        ErrorCode.expired,
        ErrorCode.conflict,
      }.contains(error.code)) {
        clear();
      }
      message = error.message;
    });
    if (error.code == ErrorCode.unauthenticated) widget.onSessionEnded?.call();
  }

  Future<void> load({bool more = false, bool moreDoctors = false}) async {
    if (busy || !foreground) return;
    if (!more && !moreDoctors) clear();
    final current = generation;
    setState(() {
      busy = true;
      message = null;
    });
    try {
      if (widget.directory || moreDoctors) {
        final page = await widget.api.doctors(
          widget.token(),
          cursor: moreDoctors ? doctorCursor : null,
        );
        if (!mounted || current != generation || !foreground) return;
        setState(() {
          doctors.addAll(page.items);
          doctorCursor = page.nextCursor;
        });
      } else {
        final page = await widget.api.cases(
          widget.token(),
          cursor: more ? cursor : null,
        );
        if (!mounted || current != generation || !foreground) return;
        setState(() {
          cases.addAll(page.items);
          cursor = page.nextCursor;
        });
        if (!more && widget.account.role == Role.administrator) {
          final directory = await widget.api.doctors(widget.token());
          if (!mounted || current != generation || !foreground) return;
          setState(() {
            doctors.addAll(directory.items);
            doctorCursor = directory.nextCursor;
          });
        }
      }
    } on ApiFailure catch (error) {
      if (mounted && current == generation) failure(error);
    } catch (_) {
      if (mounted && current == generation) {
        setState(() {
          clear();
          message =
              'The workflow could not be loaded safely. Refresh and retry.';
        });
      }
    } finally {
      if (mounted && current == generation) setState(() => busy = false);
    }
  }

  Future<void> choose(CaseSummary item) async {
    final current = generation;
    choosing = true;
    final doctor = await showDialog<DoctorSummary>(
      context: context,
      builder: (context) => SimpleDialog(
        title: const Text('Choose an active eligible doctor'),
        children: [
          for (final doctor in doctors)
            SimpleDialogOption(
              onPressed: () => Navigator.pop(context, doctor),
              child: Text('${doctor.displayName} · ${doctor.department}'),
            ),
          if (doctors.isEmpty)
            const Padding(
              padding: EdgeInsets.all(16),
              child: Text(
                'No eligible doctors loaded. Refresh or load more doctors.',
              ),
            ),
        ],
      ),
    );
    choosing = false;
    if (!mounted || current != generation || doctor == null) return;
    pendingCase = item;
    pendingDoctor = doctor.doctorId;
    pendingKey = operationKey();
    await assign();
  }

  Future<void> assign() async {
    if (busy || pendingCase == null) return;
    final current = generation;
    setState(() {
      busy = true;
      message = null;
    });
    try {
      final item = await widget.api.assign(
        widget.token(),
        pendingCase!,
        pendingDoctor!,
        pendingKey!,
      );
      if (!mounted || current != generation || !foreground) return;
      setState(() {
        cases.removeWhere((row) => row.caseId == item.caseId);
        cases.insert(0, item);
        pendingCase = null;
        pendingDoctor = null;
        pendingKey = null;
        message = 'Assignment recorded.';
      });
    } on ApiFailure catch (error) {
      if (mounted && current == generation) {
        if (!error.retryable) {
          pendingCase = null;
          pendingDoctor = null;
          pendingKey = null;
        }
        failure(error);
      }
    } catch (_) {
      if (mounted && current == generation) {
        setState(
          () => message =
              'The response was interrupted. Retry the same assignment to check its outcome.',
        );
      }
    } finally {
      if (mounted && current == generation) setState(() => busy = false);
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      unawaited(load());
    } else {
      setState(() {
        clear();
        message = 'Return to refresh the workflow.';
      });
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    poll?.cancel();
    clear();
    widget.api.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final editable = !busy && pendingCase == null;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(
          widget.directory
              ? 'Active eligible doctors'
              : widget.reviews
              ? 'Assigned cases · review history'
              : widget.account.role == Role.administrator
              ? 'Hospital case assignments'
              : 'Your assigned cases',
          style: Theme.of(context).textTheme.titleLarge,
        ),
        const Text('Synthetic workflow demonstration'),
        Align(
          alignment: Alignment.centerLeft,
          child: TextButton.icon(
            onPressed: editable ? load : null,
            icon: const Icon(Icons.refresh),
            label: const Text('Refresh'),
          ),
        ),
        if (busy) const LinearProgressIndicator(),
        if (message != null) Text(message!),
        if (pendingCase != null && !busy)
          FilledButton(
            onPressed: assign,
            child: const Text('Retry same assignment'),
          ),
        if (widget.directory) ...[
          for (final doctor in doctors)
            ListTile(
              title: Text(doctor.displayName),
              subtitle: Text('${doctor.department} · ${doctor.doctorId}'),
            ),
          if (doctorCursor != null)
            TextButton(
              onPressed: editable ? () => load(moreDoctors: true) : null,
              child: const Text('Load more doctors'),
            ),
        ] else ...[
          if (cases.isEmpty && !busy) const Text('No cases to display.'),
          for (final item in cases)
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SelectableText(
                      'Case ${item.caseId} · Patient ${item.patientId}',
                    ),
                    Text(
                      workflowLabel(
                        item.processingStatus,
                        item.reviewStatus,
                        item.assignedDoctorId,
                        item.expiresAt,
                      ),
                    ),
                    Text(
                      'Assigned doctor: ${item.assignedDoctorId ?? 'Awaiting assignment'}',
                    ),
                    Text(
                      'Created ${item.createdAt.toLocal()} · case version ${item.version}',
                    ),
                    if (item.failureCode != null)
                      Text('Processing diagnostic: ${item.failureCode!.value}'),
                    if (widget.account.role == Role.administrator)
                      OutlinedButton(
                        onPressed:
                            editable &&
                                item.expiresAt?.isAfter(DateTime.now()) != false
                            ? () => choose(item)
                            : null,
                        child: Text(
                          item.assignedDoctorId == null
                              ? 'Assign doctor'
                              : 'Reassign doctor',
                        ),
                      )
                    else ...[
                      OutlinedButton(
                        onPressed: editable
                            ? () => context.push('/results/${item.reportId}')
                            : null,
                        child: const Text('Open laboratory evidence'),
                      ),
                      FilledButton(
                        onPressed: editable
                            ? () => context
                                  .push('/review/${item.reportId}')
                                  .then((_) {
                                    if (mounted) unawaited(load());
                                  })
                            : null,
                        child: Text(
                          widget.reviews
                              ? 'Open review history'
                              : 'Review case',
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          if (cursor != null)
            TextButton(
              onPressed: editable ? () => load(more: true) : null,
              child: const Text('Load more cases'),
            ),
          if (widget.account.role == Role.administrator && doctorCursor != null)
            TextButton(
              onPressed: editable ? () => load(moreDoctors: true) : null,
              child: const Text('Load more eligible doctors'),
            ),
        ],
      ],
    );
  }
}
