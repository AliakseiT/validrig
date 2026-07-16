# QMS Traceability — what the harness produces, and what it supports

**Purpose.** Make explicit which artifact the harness produces maps to which
regulatory obligation, so the boundary is clear: the harness generates the
**performance-and-change evidence slice** of a conformity dossier — not the
dossier, and not a management system.

**Not legal advice.** This is an engineering traceability aid. Confirm the
obligation mapping and the provider/deployer determination with your notified
body / regulatory advisor; both are fast-moving and deployment-specific.

## Artifacts produced (per project repo, written to the run store)

| Artifact | File | Layer |
|---|---|---|
| Run record (pins) | `runs.sqlite` | evidence |
| Generations | `runs/<id>/generations.parquet` | evidence |
| Judge grades | `runs/<id>/grades.parquet` | evidence |
| Human calibration grades | `calibration/<id>.jsonl` | evidence |
| InputContract | `runs/<id>/contract.json` | derived |
| ValidationReport (structured) | `runs/<id>/validation_report.json` | derived |
| RegressionDiff | `diffs/<a>__<b>.json` | derived |
| **V&V Plan** | `runs/<id>/qms/vv_plan.yml` | QMS record |
| **V&V Report** | `runs/<id>/qms/vv_report.{md,json}` | QMS record |
| **Calibration Status** | `runs/<id>/qms/calibration_status.json` | QMS record |
| **Change Request** | `qms/change_<a>__<b>.{md,json}` | QMS record |
| **Package Manifest** | `runs/<id>/qms/package_manifest.json` | QMS index |

Every QMS record carries an attestation (pinned-inputs hash + r05 baseline tag
`QMS-2026-07-09-R005`) and an **unsigned** signature block — draft evidence a
human reviews and signs.

## Mapping to obligations

| Harness output | MDR Art. 5(5) | EU AI Act (high-risk) | ISO/IEC 42001 |
|---|---|---|---|
| V&V Plan + Report | (f) technical documentation: design/performance & V&V data | Art. 15 accuracy/robustness; Art. 17 QMS (test planning) | A.6 AI system lifecycle (V&V) |
| InputContract | (f) performance characterization | Art. 15 (performance envelope); Art. 13 transparency (input needs) | A.6 (system behaviour understanding) |
| Calibration Status | evidence-quality assurance for (f)/(h) | Art. 15 (measurement validity of the eval) | A.6 (verification of AI-derived measures) |
| RegressionDiff + Change Request | change control feeding (g) manufacture-per-documentation | Art. 43(4) predetermined changes / substantial-modification assessment | A.6 change management |
| MonitoringSnapshot *(M5, not built)* | (h) review of clinical-use experience | Art. 72 post-market monitoring | A.6 operation & monitoring |
| AIMS register/event *(not built)* | — | supports Art. 9 risk management | A.5 AI risk & impact assessment |

## The boundary — what the harness does NOT produce

These are required for an Art. 5(5) in-house device but are **out of scope** for
this tool (they belong to the QMS baseline and the project's regulatory work):

- The **QMS** itself (Art. 5(5)(b)) — see `dearauditor-qms-baseline`.
- The **equivalence justification** (Art. 5(5)(c)).
- The **public declaration** of GSPR conformity (Art. 5(5)(e)).
- The **risk-management file** (ISO 14971), **usability** (IEC 62366-1), and
  **clinical evaluation**.
- Under the AI Act, if the hospital **builds/substantially modifies** the AI in
  house it may be a **provider** (Art. 25) owing the full Art. 9–17 set — not the
  lighter deployer duties (Art. 26). The harness supports Art. 15 (and inputs to
  9/13/72); it does not discharge the provider obligation set.

## Repository model

- **Engine repo** (the harness factory): engine code + the synthetic demo pack
  (a fixture) + these docs. Contains no project data.
- **Project repo** (one per intended use): the pack, the run store, and all
  produced artifacts above — including calibration status and the QMS package.
  PHI never enters the engine repo; pseudonymization happens at project
  ingestion (not yet built).
