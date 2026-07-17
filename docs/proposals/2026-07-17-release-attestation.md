# Proposal: Immutable-release attestation (prepare to re-use dearauditor mechanism)

**Status:** design note — *prepared, not implemented* (per direction: no rush) · **Date:** 2026-07-17

## What we have

Every QMS record and the consolidated dossier already carry an **attestation
block**: `pinned_inputs_hash = content_hash(pins)` (pack hash, battery, SUT hash,
judge, seed, engine version), the r05 baseline tag, and an *unsigned* signature
block. A reviewer can recompute the hash from the pins and confirm the record was
produced from the stated inputs. What's missing is a **tamper-evident anchor**:
proof the document existed, unaltered, at a point in time.

## What dearauditor-qms-baseline does

The baseline anchors controlled documents to **immutable GitHub releases**
(`QMS-YYYY-MM-DD-RNNN` tags). A published release is effectively append-only and
timestamped by GitHub; the release (tag + commit sha + attached assets) becomes
the immutable reference an auditor can cite.

## The seam we've prepared

The dossier already exposes a `signing` block:

```json
"signing": {
  "status": "unsigned",
  "mechanism": "github_immutable_release (planned)",
  "release_anchor": null,
  "note": "Draft evidence; sign by anchoring to an immutable GitHub release."
}
```

`release_anchor` is where the anchor lands once implemented — nothing else needs
to change in the record shape.

## Implementation sketch (when we do it)

1. **Freeze** the dossier (its `pinned_inputs_hash` is already stable and
   content-only — no timestamp in the hash, so it's reproducible).
2. **Publish** to an immutable release in the *project* repo (never the engine
   repo): create a `QMS-<product>-<date>-R<n>` tag, attach `dossier.html` +
   `dossier.json`, and record in `release_anchor`:
   ```json
   {"repo": "...", "tag": "QMS-tcga-lung-2026-07-17-R001",
    "release_id": 123, "commit_sha": "…", "asset_sha256": "…", "published_at": "…"}
   ```
3. **Verify** (a `harness attest --verify` command): re-fetch the release asset,
   confirm `asset_sha256` matches, and confirm `pinned_inputs_hash` matches the
   dossier's — tamper-evident end to end.

## Design constraints to honour

- **Content vs metadata:** the anchor (tag, timestamp, sha) is run-metadata — it
  must not enter `pinned_inputs_hash` (which stays content-only and reproducible),
  exactly the timestamp discipline used everywhere else.
- **PHI boundary:** only attest artifacts that are already aggregate-safe. The
  dossier can contain case-derived text (a pathology excerpt), so anchoring a
  dossier that includes real case content must publish to a **private/controlled**
  release, never a public one — the same rule as the project repos.
- **Human signature is still separate:** the immutable anchor proves *integrity
  and existence*, not *approval*. The unsigned signoff block is signed by a
  person; the release anchor is orthogonal evidence.

## Not doing now

No release creation, no GitHub API calls, no new dependency. This note + the
`release_anchor` seam are the whole "prepare to re-use" deliverable.
