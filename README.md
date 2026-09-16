# Student Ad Competition Copilot

Private distribution repository for the `student-ad-competition-copilot` Codex skill.

## Package

- Skill path: `skills/student-ad-competition-copilot`
- Current version: `0.2.1`
- Release status: `stable-release`
- Supported tracks: print advertising, ad copy, and marketing plans for 大广赛 and 学院奖

The repository contains only the installable runtime package. Research corpora, raw media, development audits, temporary recovery data, and historical run outputs are intentionally excluded.

## Install in Codex

Ask Codex to use `$skill-installer` with:

- Repository: `Yuzeskyare/student-ad-competition-copilot`
- Path: `skills/student-ad-competition-copilot`
- Ref: `v0.2.1`

Access to this private repository is required. The installer can use existing Git credentials or `GH_TOKEN`/`GITHUB_TOKEN`.

The skill becomes available on the next Codex turn after installation.

## Integrity

`skills/student-ad-competition-copilot/version.json` records the release version and SHA-256 hashes for the other 65 runtime files. The complete installed package contains 66 files including `version.json` itself.

## Update policy

Published tags are immutable. New releases use a new semantic version tag. Installations should pin a tag when reproducibility matters.

## Distribution boundary

This repository is private. Do not mirror, republish, or redistribute its contents without the project owner's permission.
