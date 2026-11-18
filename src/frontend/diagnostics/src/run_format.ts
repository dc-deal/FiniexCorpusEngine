/**
 * A run of the pipeline on one line (the operator's 18.a): its command without the module path every one of them shares. Only how
 * it is written changes; the full command stays in the line's tooltip. When it ran is said by `human_time`.
 *
 * Since 208.b the conversion's modules stand in folders by concern, so a run started since reads
 * "python -m backend.conversion.checks.check_run …" while the pipeline database keeps the earlier runs as
 * "python -m backend.conversion.check_run …": both say "check_run …".
 */
const MODULE_PATH = /^python -m backend\.conversion\.(?:(?:contract|reading|checks|judge|measurement|store)\.)?/

export function shortCommand(command: string): string {
  return command.replace(MODULE_PATH, '')
}
