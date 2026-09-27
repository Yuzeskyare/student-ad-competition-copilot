# Student Ad Competition Copilot

Private distribution repository for the `student-ad-competition-copilot` skill.

## Package

- Skill path: `skills/student-ad-competition-copilot`
- Current packaged version: `0.2.10`
- Release tag: `v0.2.10`
- Release status: `stable-release`
- Supported tracks: print advertising, ad copy, and marketing plans for 大广赛 and 学院奖

The repository contains only the installable runtime package. Research corpora, raw media, development audits, temporary recovery data, and historical run outputs are intentionally excluded.

## Install in Codex

Ask Codex to use `$skill-installer` with:

- Repository: `Yuzeskyare/student-ad-competition-copilot`
- Path: `skills/student-ad-competition-copilot`
- Ref: `v0.2.10`

Access to this private repository is required. The installer can use existing Git credentials or `GH_TOKEN`/`GITHUB_TOKEN`.

The skill becomes available on the next Codex turn after installation.

## Other hosts and image tools

In another host that supports skills, install the complete folder using that host's skill mechanism and start from `SKILL.md`. The instructions discover the host's actual file, script and image capabilities; Codex-specific dependency tools are optional. If the assistant cannot generate images directly, it can prepare prompts for an available external image tool and resume after the actual assets are returned and checked. Hosts without script execution must hand off the file checks rather than claim they ran.

Version 0.2.9 selects concrete visual styles from the brief and adapts prompts to the actual tool. GPT Image, Gemini, Imagen, Midjourney, Firefly and supported local workflows have conditional guidance, not a promise of identical capabilities or output quality. Canva image generation is excluded. Actual generation/edit testing covered the current built-in image tool; other tool branches and hosts received documentation or simulated workflow checks. Sample transparency, whitespace and path-following limitations remain documented in the package acceptance record.

Version 0.2.9 repairs failure-before-review routing, isolates optional submission data from artwork delivery, requires applicable validation results, and improves dependency diagnostics and cross-shell command guidance. Its 151 focused tests use synthetic fixtures; PowerShell path handling was exercised locally, while POSIX examples received static review only.

Version 0.2.10 improves copy-form preference inheritance, conditional language review, external sample interpretation, and early exploration notes. Formal run schemas and executable validators remain unchanged. Validation includes 145 synthetic contract checks, eight runtime self-checks, and twelve same-executor scenario walkthroughs; the walkthroughs are not independent A/B tests, artwork approvals, or evidence of reduced time/token usage.

## Integrity

`skills/student-ad-competition-copilot/version.json` records the release version and SHA-256 hashes for the other 103 runtime files. The complete installed package contains 104 files including `version.json` itself.

The project release regression verifies that this README's packaged version, release tag, installation ref, manifest-entry count, and complete package count match `version.json`. A release cannot pass while these values are stale.

## Update policy

Published tags are immutable. New releases use a new semantic version tag. Installations should pin a tag when reproducibility matters.

## Distribution boundary

This repository is private. Do not mirror, republish, or redistribute its contents without the project owner's permission.
