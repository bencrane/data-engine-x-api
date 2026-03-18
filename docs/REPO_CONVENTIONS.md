# Repo Conventions

**Last updated:** 2026-03-18T07:00:00Z

Universal standards for all agents working in `data-engine-x-api`.

## Last-Updated Headers

Every `.md` file in `docs/` must include a `**Last updated:** [ISO 8601 UTC timestamp]` line immediately after the title. When an agent modifies a file, it must update this timestamp. Do not add last-updated headers to files you are not otherwise modifying.

## Commit Convention

Each deliverable in a directive is one standalone commit. Executors do not push unless explicitly told to.

## Work Log

Every executor appends an entry to `docs/EXECUTOR_WORK_LOG.md` as its final commit. See that file for format.

## File Naming

New doc files use `UPPER_SNAKE_CASE.md`. New executor directives use `EXECUTOR_DIRECTIVE_[NAME].md`.

## Do Not Modify Historical Directives

`docs/EXECUTOR_DIRECTIVE_*.md` files are historical scope documents. Do not update their cross-references or content unless the directive specifically scopes that work.
