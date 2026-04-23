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

**Fit check.** Before applying, read the *When not to apply this* section
below — the default priming is load-bearing for a real class of deployments,
and this override will regress them.

## When not to apply this

The default Continuity priming exists for a reason, and the reason is real.
Before applying this override, check your deployment against the patterns
below — if any of them describe what you're running, the override will
regress you and you should leave `SOUL.md` alone.

**Long-lived personal-assistant agents.** If your agent runs continuously
across days or weeks, wakes from heartbeats, and the conversation spans
many sessions separated by hours or more, the filesystem *is* the memory
substrate. `MEMORY.md` and `memory/YYYY-MM-DD.md` are how identity and
context survive context compaction and process restarts. "Wake up fresh
and read your files" is literal operational truth for this shape, not a
loose metaphor. Removing the priming tells the agent to trust a stale
view of itself, and it will drift.

**Agents that self-maintain their workspace.** If your agent updates
`MEMORY.md`, writes daily logs, or distills old memories during heartbeats
— the unwind-ai 24/7-team pattern — the Continuity framing is the
instruction that keeps those writes consistent. The agent needs to re-read
what the last heartbeat wrote, because a previous instance of itself put
information there the current instance doesn't have.

**Multi-agent setups where sibling agents write to shared files.** If you
have orchestrator / sub-agent topologies where one agent writes to a
shared `MEMORY.md` or state file and another reads it, re-reads within a
turn can be legitimate — the file may have been written by a sibling
between the first read and the second. The override's "trust what you
just saw" language is still directionally correct here but the nuance
needs thought, and if you can't articulate the nuance for your specific
topology, the safer move is to leave the default alone and fix the loop
at the tool-call-discipline layer instead.

**The loop you're debugging isn't a re-read storm.** If your agent is
looping on something other than repeated `read` calls — same `exec`
command over and over, ping-ponging between two tools, or retrying on a
genuine error — that's the tool-call-discipline or retry-discipline
recipe's territory, not this one. Applying the within-turn-trust rule
won't help, and it will add prompt surface area you then have to reason
about when the real loop is elsewhere.

**You haven't seen the symptom.** If you're applying this prophylactically
"just in case", don't. The override does nothing useful until the agent
is actually re-reading, and carrying an unneeded rule in every system
prompt is a small but real cost — it's context you could spend on
something load-bearing. Wait until you see the storm, confirm it's the
within-turn re-read shape (not a different loop), then apply.

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
