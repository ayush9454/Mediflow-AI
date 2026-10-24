import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_client.dart';
import '../../core/config/app_config.dart';
import '../../core/contracts/contracts.g.dart';
import '../auth/session.dart';
import 'evidence_screen.dart';
import 'report_api.dart';
import 'report_screen.dart';

/// Scope the entire viewer and its in-flight requests to the signed-in identity.
class EvidenceResultHost extends ConsumerWidget {
  const EvidenceResultHost({required this.reportId, super.key});
  final String reportId;
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final account = ref.watch(sessionProvider).account;
    if (account == null || account.role == Role.administrator) {
      return const Scaffold(
        body: Center(child: Text('Sign in to view this result.')),
      );
    }
    return _SessionViewer(
      key: ValueKey(
        '${account.hospitalId}/${account.uid}/${account.role.value}/$reportId',
      ),
      account: account,
      reportId: reportId,
    );
  }
}

class _SessionViewer extends ConsumerStatefulWidget {
  const _SessionViewer({
    required this.account,
    required this.reportId,
    super.key,
  });
  final Account account;
  final String reportId;
  @override
  ConsumerState<_SessionViewer> createState() => _SessionViewerState();
}

class _SessionViewerState extends ConsumerState<_SessionViewer> {
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
  Widget build(BuildContext context) => EvidenceResultScreen(
    account: widget.account,
    reportId: widget.reportId,
    api: api,
    platform: ref.read(reportPlatformProvider),
    token: token,
    onSessionEnded: () => ref.read(sessionProvider.notifier).expire(),
  );
}
