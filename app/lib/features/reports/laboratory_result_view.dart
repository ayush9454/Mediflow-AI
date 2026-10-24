import 'package:flutter/material.dart';

import '../../core/contracts/contracts.g.dart';

/// Renders one tagged, versioned result; never derives an approval from a draft.
class LaboratoryResultView extends StatelessWidget {
  const LaboratoryResultView({
    required this.result,
    required this.pageCount,
    required this.onOpenEvidence,
    super.key,
  });
  final ReportResult result;
  final int? pageCount;
  final void Function(EvidenceReference)? onOpenEvidence;

  @override
  Widget build(BuildContext context) {
    final draft = result.draft, approved = result.approved;
    final rows = draft?.rows ?? approved!.rows;
    final provenance = draft?.provenance ?? approved?.provenance;
    final summary = draft?.summary ?? approved?.summary;
    final unresolved = {
      for (final item
          in approved?.unresolvedAcknowledgements ??
              <UnresolvedAcknowledgement>[])
        item.issueId: item.reason,
    };
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(
          draft != null ? 'AI candidate · not approved' : 'Approved snapshot',
          style: Theme.of(context).textTheme.titleLarge,
        ),
        const SizedBox(height: 8),
        SelectableText(
          'Analysis ${draft?.analysisId ?? approved!.analysisId} · version ${draft?.version ?? approved!.analysisVersion}',
        ),
        if (approved != null) ...[
          Text(
            'Reviewed by ${approved.reviewerId} · ${approved.reviewedAt.toLocal()}',
          ),
          SelectableText('Review ${approved.reviewId}'),
          for (final item in approved.unresolvedAcknowledgements)
            Text('Unresolved · ${item.issueId}: ${item.reason}'),
        ],
        const SizedBox(height: 12),
        const Text(
          'Compare every field with the original page. A matching quotation shows traceability; it does not establish correctness.',
        ),
        const SizedBox(height: 16),
        Text(
          'Document summary',
          style: Theme.of(context).textTheme.titleMedium,
        ),
        SelectableText(summary ?? 'No summary is available.'),
        if (draft != null)
          for (final issue in draft.issues) _Issue(issue: issue),
        if (rows.isEmpty) const Text('No laboratory rows are available.'),
        for (final row in rows)
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    row.analyte,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  Text(
                    draft != null
                        ? 'AI candidate field'
                        : approved!.correctedRowIds.contains(row.rowId)
                        ? 'Clinician corrected · approved'
                        : 'Approved field',
                  ),
                  const SizedBox(height: 8),
                  SelectableText('Result: ${row.result}'),
                  for (final field in <String, String?>{
                    'Unit': row.unit,
                    'Printed interval': row.referenceRange,
                    'Printed flag': row.abnormalityFlag,
                    'Collection date': row.collectionDate,
                  }.entries)
                    SelectableText(
                      '${field.key}: ${field.value ?? 'Missing from extracted data'}',
                    ),
                  for (final issue in row.issues)
                    _Issue(
                      issue: issue,
                      unresolvedReason: unresolved[issue.issueId],
                    ),
                  if (row.evidence.isEmpty)
                    const Text(
                      'Missing evidence · no source page/quotation is available.',
                    ),
                  for (final evidence in row.evidence)
                    if (evidence.page < 1 ||
                        pageCount == null ||
                        evidence.page > pageCount! ||
                        evidence.quotation.trim().isEmpty)
                      Text(
                        'Invalid evidence · source page ${evidence.page} or quotation cannot be verified.',
                      )
                    else ...[
                      const SizedBox(height: 8),
                      Text(
                        'Page ${evidence.page} · ${evidence.extractionMethod == ExtractionMethod.ocr ? 'OCR; visually check the scan' : 'Digital text'}',
                      ),
                      OutlinedButton.icon(
                        onPressed: onOpenEvidence == null
                            ? null
                            : () => onOpenEvidence!(evidence),
                        icon: const Icon(Icons.find_in_page_outlined),
                        label: Text('Open source page ${evidence.page}'),
                      ),
                    ],
                ],
              ),
            ),
          ),
        const SizedBox(height: 16),
        ExpansionTile(
          title: const Text('Analysis provenance'),
          childrenPadding: const EdgeInsets.all(16),
          expandedCrossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (provenance == null)
              const Text(
                'Analysis provenance was not recorded in this snapshot.',
              )
            else ...[
              SelectableText(
                'Pipeline: ${provenance.pipelineVersion}\nPrompt: ${provenance.promptVersion}\nProvider: ${provenance.modelProvider}\nModel: ${provenance.modelName ?? provenance.modelVersion}\nModel version: ${provenance.modelVersion}',
              ),
              if (draft != null)
                Text(
                  'Schema: ${draft.schemaVersion} · Created ${draft.createdAt.toLocal()}',
                ),
              if (provenance.configuration != null)
                SelectableText(
                  'Configuration: ${provenance.configuration!.version}\nPrompt SHA-256: ${provenance.configuration!.promptSha256}\nSchema SHA-256: ${provenance.configuration!.schemaSha256}',
                ),
              if (provenance.sourceSha256 != null)
                SelectableText('Source SHA-256: ${provenance.sourceSha256}'),
              if (provenance.usage != null)
                Text(
                  'Provider tokens: ${provenance.usage!.inputTokens} input, ${provenance.usage!.outputTokens} output · ${provenance.usage!.elapsedSeconds.toStringAsFixed(2)} s',
                ),
            ],
          ],
        ),
      ],
    );
  }
}

class _Issue extends StatelessWidget {
  const _Issue({required this.issue, this.unresolvedReason});
  final ValidationIssue issue;
  final String? unresolvedReason;
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 6),
    child: Text(
      unresolvedReason != null
          ? 'Unresolved · ${issue.field}: $unresolvedReason'
          : '${issue.severity == IssueSeverity.blocking ? 'Needs review' : 'Flagged'} · ${issue.field}: ${issue.message}',
      style: TextStyle(color: Theme.of(context).colorScheme.error),
    ),
  );
}
