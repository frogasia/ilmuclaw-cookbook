# Tool-call discipline

> Stop the agent from calling tools in loops.

## Problem

Agents sometimes call the same tool, with the same arguments, over and
over — getting the same result each time and making no progress. A
`read` of an unchanged file four times in a row. A `command_status`
poll that never changes state. A pair of tools alternating A-B-A-B
without moving forward. Each call costs tokens and wall-clock; a bad
loop can burn a turn's worth of budget before the user cancels it.

This failure is distinct from *deliberate* retry after a known error
(tool returned HTTP 500, a file lock was held). That case is covered
by the retry-discipline recipe. This recipe is about the *unconscious*
version — the agent doesn't notice the repetition, keeps trying, and
doesn't stop on its own.

The fix layers two independent safeguards: a runtime backstop that
OpenClaw already knows how to apply if you enable it, and a prompt
rule that gives the agent an earlier, softer exit.

## Snippet

**Layer 1 — runtime backstop.** OpenClaw ships with `tools.loopDetection`
disabled by default. Enable it with a tight profile:

```sh
openclaw config set tools.loopDetection.enabled true
openclaw config set tools.loopDetection.warningThreshold 6
openclaw config set tools.loopDetection.criticalThreshold 12
openclaw gateway restart
```

The two thresholds are deliberately tighter than OpenClaw's shipped
defaults (`10` and `20`). Workshop-length sessions and smaller-model
agents benefit from a quicker trip; long-running personal agents
doing legitimate bulk work may not. If the tight profile blocks work
you actually want, roll back to defaults by omitting the threshold
lines (leave only `enabled true`), or set them to `10` / `20`.

The detector that catches the common case is `genericRepeat` — same
tool, same arguments, same result. It's on by default once
`loopDetection.enabled` is true; you don't need to touch it. Two other
detectors (`pingPong`, `knownPollNoProgress`) are also on by default
and handle the less common alternating and status-poll shapes. For
the full configuration surface — history size, per-agent overrides,
the circuit-breaker threshold — ask your agent to DeepWiki
`tools.loopDetection` in `openclaw/docs`, or read
<https://github.com/openclaw/docs>.

**Layer 2 — prompt rule.** Check whether
`~/.openclaw/workspace/AGENTS.md` already contains a
`## Tool-call discipline` section. If it's missing, add the block
below. If it's already there, nothing to do.

```markdown
## Tool-call discipline

If you call a tool and the next call would have the same tool name
and the same arguments, stop. Calling it a third time with the same
shape is almost never what the user wants.

Instead, do one of:

- vary the call (different args, different tool, different approach)
- report what you tried and what came back, and ask the user what
  to do next

Worked example.

Wrong shape:
> I'll read `install.sh` to find the config path.
> *(reads install.sh, sees the line)*
> Let me re-read `install.sh` to confirm.
> *(reads install.sh again, identical result)*
> Re-reading once more to be thorough.
> *(reads install.sh a third time)*

Right shape:
> I'll read `install.sh` to find the config path.
> *(reads install.sh, sees the line)*
> Confirmed — it's at `install.sh:216`, `agents.defaults.thinkingDefault`.
> The second read would return the same bytes, so I'm skipping it.
```

Then restart the gateway so the next session reads the updated
`AGENTS.md`:

```sh
openclaw gateway restart
```

**Persistence.** `AGENTS.md` is bootstrap-injected into every future
session's system prompt, including sub-agent sessions — so the rule
propagates to delegated work. To undo, remove the
`## Tool-call discipline` section and restart the gateway again.

**Boundary with the retry-discipline recipe.** This recipe targets
unconscious same-tool-same-args looping. If your agent is
deliberately retrying after a known failure (tool errored, timeout,
HTTP 500), that's a different shape — see the retry-discipline
recipe.

## Why it works

Two safeguards, failing independently. The runtime backstop is a
hard stop at the OpenClaw layer — it sees the raw tool-call history
and blocks the cycle past `criticalThreshold` regardless of what the
agent is doing in its prompt. The prompt rule gives the agent an
earlier, softer exit before the backstop trips, and it propagates to
sub-agents via `AGENTS.md` bootstrap injection. If the prompt rule
works, the backstop is silent. If the prompt rule fails, the
backstop catches it. You don't need both to work on the same turn;
you need at least one.

Tightening the thresholds below the shipped defaults is the part of
the snippet that's most opinionated. The default `10 / 20` were
chosen for a long-running personal-agent setup; workshop-length
sessions and smaller models hit the failure mode faster and benefit
from a shorter fuse. If the tight profile produces false positives
on legitimate repetitive work, the rollback is two lines.
