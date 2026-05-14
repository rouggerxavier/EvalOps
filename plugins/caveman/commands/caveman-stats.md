# /caveman-stats

Show caveman token usage statistics when hook support is available.

## Workflow

1. Let the caveman `UserPromptSubmit` hook handle `/caveman-stats` when installed.
2. If the hook did not intercept the prompt, explain that live stats require the hook runtime and point to `plugins/caveman/hooks/caveman-stats.js`.

