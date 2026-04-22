# Hallucination mitigation

> Prompting patterns that keep answers grounded.

## Problem

Agents sometimes state things with full confidence that aren't true — a flag
that doesn't exist, a filename that was never created, a CLI subcommand
invented on the spot, a function signature hallucinated whole. This is a
general property of how language models generate text: when the model is
asked a specific question and the answer isn't strongly represented in the
current context, it often produces a plausible-shaped guess rather than
admitting it doesn't know.

The failure is most visible and most costly when the agent is driving
something with a large, shifting surface — a CLI, an SDK, a config schema,
a codebase — because the user can't tell a fabricated flag from a real one
without going to check. A single invented flag in a paste-ready command can
burn minutes of debugging and erode trust in everything else the agent
said in the same turn.

The fix is a prompt pattern, not a model swap. You give the agent an
explicit rule for what counts as a source, an explicit rule for citing it,
and an explicit exit path for "I don't know" — so guessing stops being the
default fallback.

## Snippet

Paste this into `~/.openclaw/workspace/AGENTS.md`. OpenClaw reads
`AGENTS.md` into every session's system prompt on startup (workspace
bootstrap injection), and into sub-agent sessions too, so the rule
propagates to delegated work.

```markdown
## Grounding discipline

When you name a specific identifier — a flag, filename, config key,
CLI subcommand, function name, error code, or URL path — it must be
backed by a source you've seen in this session. A source is one of:

- a tool result from this turn (a file you `read`, a `web_fetch` body,
  a command's actual output)
- an MCP response you received this turn
- text the user pasted into the conversation

After each identifier, include a short parenthetical pointing at the
source — e.g. `(from install.sh:40)` or `(from web_fetch of docs.x.ai)`
or `(from the user's paste above)`. One citation per identifier is
enough; don't repeat the same citation for every word.

When you don't have a source, say so plainly. Use phrases like
"I don't know the exact flag — want me to check?" or
"I haven't read that file this session; I'd be guessing." Do not
produce a plausible-shaped guess and hope it's right.

Worked example.

Ungrounded (wrong shape):
> Run `openclaw config set agents.thinking adaptive` to enable it.

Grounded (right shape):
> Looking at `install.sh:216` in this repo, the key is
> `agents.defaults.thinkingDefault`, not `agents.thinking`. Run:
> `openclaw config set agents.defaults.thinkingDefault adaptive`
> (from install.sh:216).

If the user asks something you'd need to fabricate to answer, the
right move is a short tool call — read the file, search the docs,
ask the user — not a confident guess.
```

Restart the gateway so the next session picks up the change:

```sh
openclaw gateway restart
```

## Why it works

Three moves stack. First, the "must be backed by a source" rule turns
naming a flag into a lookup problem rather than a generation problem —
the agent has to either recall a concrete source or go fetch one, and
both paths produce real answers. Second, the inline citation makes
confabulation visible to the user at read time: a missing or vague
citation is a signal to double-check before pasting, whereas an
uncited confident answer looks identical to a correct one. Third, the
explicit "I don't know" exit gives the model a non-guess path that's
cheaper than fabricating — without it, guessing is the only way to
complete the turn, so the model guesses.

The pattern is model-agnostic. The mechanism is the prompt shape, not
any one model's training — the same three moves improve grounding on
large frontier models and on smaller local ones. It does cost a little
verbosity and the occasional extra tool call, which is the right
trade when the alternative is a confidently wrong paste-ready command.
