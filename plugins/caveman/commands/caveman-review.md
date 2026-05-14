# /caveman-review

Review the current code changes with one-line findings.

## Workflow

1. Use the `caveman-review` skill.
2. Prioritize bugs, risks, regressions, and missing tests.
3. Format each finding as `L<line>: <severity> <problem>. <fix>.`
4. Use `bug`, `risk`, `nit`, or `q` as severity.
5. If there are no findings, say `LGTM` and mention residual test risk only if relevant.

