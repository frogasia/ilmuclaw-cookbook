# Within-turn trust

> Stop the agent from re-reading the same file within a single turn.

## Problem

An agent calls `read` on a workspace file — `SOUL.md`, a small state JSON, a
config — sees the result, then calls `read` on the exact same file again a
moment later. And again. The same arguments, the same bytes back, no
intervening write. A single turn can burn ten redundant reads on one file:
tens of seconds of wall-clock, tens of thousands of tokens, and a visibly
stuck agent.

The root cause isn't the model being careless — it's a priming collision in
the default workspace. OpenClaw ships `SOUL.md` with a Continuity section
that tells the agent *"Each session, you wake up fresh. These files are your
memory. Read them."* And separately, the runtime already injects `SOUL.md`,
`AGENTS.md`, `IDENTITY.md`, `USER.md`, and `MEMORY.md` into the system prompt
on every turn — the agent starts each turn with the content already in
context. The priming tells the agent to go fetch what it already has, and
smaller models that take instructions literally do exactly that, repeatedly.

This priming makes sense for its intended audience: long-lived
personal-assistant agents that wake across days, maintain their own memory
files, and use the filesystem as the substrate for identity that persists
past context compaction. For that shape, "these files *are* your memory" is
load-bearing truth.

It misfits short-lived task agents. A workshop bot, a single-purpose
assistant, a pipeline worker — anything that runs for one session and doesn't
self-maintain its files between sessions — treats the priming as a standing
order to re-read on no signal. The fix is to add an explicit within-turn
trust rule that overrides the "read them" instruction for deployments where
the original framing doesn't hold.

## Snippet

**To apply.** Check whether `~/.openclaw/workspace/SOUL.md` already contains
a `## Within-turn trust` section. If it's missing, append the block below.
If it's already there, nothing to do.

```markdown
## Within-turn trust

The result of a prior tool call in the same turn is canonical. Do not
re-read the same file or re-query the same state within one turn —
the bytes you saw the first time are still the current bytes unless
you or another tool have written since.

Bootstrap files (SOUL.md, AGENTS.md, IDENTITY.md, USER.md, MEMORY.md)
are already in your system prompt on every turn. You do not need to
`read` them to "wake up" — their content is in front of you before
the turn begins. Treat the Continuity framing above as context about
persistence across sessions, not as an instruction to fetch files
you already have.

Legitimate re-reads exist. If another process is expected to have
written to the file mid-turn (a cron job, a sibling session, the
user editing by hand), re-reading is correct. The rule is "trust
what you just saw", not "never read twice".
```

After adding the block, restart the gateway so the next session reads the
updated `SOUL.md`:

```sh
openclaw gateway restart
```

**Persistence.** `SOUL.md` is bootstrap-injected into every future session's
system prompt, and the injection extends to sub-agent sessions — so the
rule propagates to delegated work automatically. To undo, remove the
`## Within-turn trust` section and restart the gateway again.

**Fit check before applying.** This override suits short-lived task agents
and single-purpose bots. If your agent is a long-lived personal assistant
that maintains its own `MEMORY.md` between sessions via heartbeats, the
default Continuity priming is doing real work for you — leave it alone and
look at tool-call discipline as the more targeted fix for any loop you're
seeing.

## Why it works

Bootstrap injection is the key mechanic to name explicitly. OpenClaw's
runtime reads the workspace `.md` files once at the start of each turn and
concatenates them into the system prompt under a Project Context block
(governed by `agents.defaults.bootstrapMaxChars`, default 20000 per file,
and `bootstrapTotalMaxChars`, default 150000 total). A `read` call against
the same file a moment later returns bytes the agent already has verbatim
in its context. Making that mechanic explicit in the prompt gives the agent
a reason not to re-fetch.

The override wins against the default priming because it's more specific
and more recent. Prompt instructions that conflict tend to resolve toward
the instruction that's more directly applicable to the current situation,
and "don't re-read within this turn" is a concrete, mechanical rule.
"These files are your memory, read them" reads as a broad orientation, not
a hard loop condition. When the override is present, the model has a clear
path that doesn't include repeated reads.

Stating the legitimate re-read case matters. A blanket "don't re-read" rule
would teach the agent to trust stale views in the presence of real external
writes — a cron job running mid-turn, a sibling session editing a shared
file, the user intervening. The phrasing "trust what you just saw" preserves
the agent's judgement for the genuine case while removing the pattern of
unconditional re-fetch.

The pattern is model-agnostic. Models that don't take instructions literally
rarely fall into the storm in the first place; models that do will follow
any rule you give them, so giving them the right rule closes the loop. No
model change required, no loss of capability for the deployments that
actually do use the filesystem as memory.
