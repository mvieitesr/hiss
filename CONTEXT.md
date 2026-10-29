# Hiss

A small, self-hostable issue tracker built as teaching material for a course on
CI/CD with GitHub Actions and Docker.

## Language

**Project**:
A named container that groups related issues.
_Avoid_: team, workspace, repository

**Issue**:
A single unit of tracked work inside a Project. Has a status (`open`, `in_progress`, `done`) and a priority (`low`, `medium`, `high`).
_Avoid_: ticket, task, bug, card

**Label**:
A named tag that can be attached to any number of Issues to categorize them (e.g. `bug`, `feature`).
_Avoid_: category, tag (reserved for Release Tags)

**Comment**:
A timestamped note attached to an Issue.
_Avoid_: note, reply

**Environment**:
A deployment target for the application. Exactly three exist: **dev**, **staging**, and **prod**. Each runs on the user's own machine as a separate deployment. They appear when CD exists; they are not the day-0 launch.
_Avoid_: stage, tier, instance

**Local Stack**:
The single Compose deployment used before CD exists. One app + Postgres, host port chosen locally, image from the clone owner's GHCR after a build → push → pull round-trip.
_Avoid_: environment, dev (reserved for the Environment), local environment

**Release Tag**:
A git tag that triggers a deployment. `X.Y.Z-snapshot` deploys to staging; `X.Y.Z` deploys to prod. The container image is tagged with the same name.
_Avoid_: version tag, release candidate

**Lesson Tag**:
A git tag that marks a pedagogical checkpoint of the repository (for example `workflows-duplicated`). It does not trigger a deployment.
_Avoid_: snapshot (reserved for `X.Y.Z-snapshot`), checkpoint, course tag, task tag

**Feature Flag**:
An environment-variable switch that enables or disables a feature per Environment without changing the deployed image.
_Avoid_: toggle, config switch

**Edge Build**:
The container image built from a push to `main`, tagged with the 8-character commit SHA and deployed to dev. Has no Release Tag.
_Avoid_: nightly, latest, snapshot build
</content>
