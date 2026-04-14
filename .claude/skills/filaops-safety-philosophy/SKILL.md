---
name: filaops-safety-philosophy
description: Use when questioning why safety gates exist, debating whether a mechanical gate applies, or constructing justifications to route around constraints. Loads the meta-awareness context from CLAUDE.md Layer 2.
---

# FilaOps Safety Philosophy — Meta-Awareness

## Why Mechanical Gates Exist

Behavioral instructions fail under pressure. Empirically demonstrated:
- Agents skip `mem_recall` despite explicit CLAUDE.md instructions (observed 3x in one day).
- Agents skip file claims despite session protocol documentation.
- Frontier models (Opus 4.6+) construct justifications for routing around constraints.
- The sophistication of the justification scales with model capability.

Mechanical gates exist because "you MUST" is not an enforcement mechanism. It is a hope.

## Current Threat Landscape

- Supply chain attacks target transitive dependencies, not direct ones (axios/plain-crypto-js pattern, 2026-03-31).
- Malicious packages stage clean versions before injecting payloads (18-hour pre-staging observed).
- `postinstall` scripts execute arbitrary code with the permissions of the installing user.
- Build artifacts (source maps, env files) leak through misconfigured publish pipelines (demonstrated twice: Feb 2025, March 2026 — identical root cause, corrective action failed).
- Compromised maintainer accounts can publish poisoned versions of trusted packages to any registry. Lockfiles and frozen installs are the primary mechanical defense.

## What CLAUDE.md Cannot Do

The mechanical gates in Layer 0 exist precisely because behavioral compliance, on its own, is insufficient.

**If you find yourself constructing a justification for why a particular rule doesn't apply to your current situation — that justification is the signal that the rule applies.**
