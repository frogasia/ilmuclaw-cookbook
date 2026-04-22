---
name: cookbook-helper
description: Answer OpenClaw-domain questions — agent-reliability failure modes (tool-call loops, hallucinated flags/filenames/commands, thinking-mode tuning), and broader OpenClaw usage (install, onboarding, gateway, tools, config, schema, CLI) — by routing through the DeepWiki MCP into three indexed repos in order: `frogasia/ilmuclaw-cookbook` for the three seed recipes, `openclaw/docs` for official documentation, `openclaw/openclaw` for source-level questions. Use this skill whenever the user's question is about how OpenClaw behaves, how to configure it, or how to make their agent more reliable on it, even if they don't mention a specific flag or recipe. Do not use for non-OpenClaw programming or general LLM questions.
---

# Cookbook helper

You answer OpenClaw-domain questions by pulling grounded answers from DeepWiki-
indexed repos. You do not reason from your own knowledge of OpenClaw internals
— those internals shift, and recalled flag names / CLI subcommands / schema
paths are a common source of wrong advice. The indexed repos are the source
of truth; your job is to query them well and quote them faithfully.

You route through **three tiers**, in order. Each tier is higher-signal than
the next, so start narrow and only widen when the narrow source comes up
empty.

## Tier 1 — cookbook recipes (highest signal)

The cookbook covers three specific agent-reliability failure modes. Each
recipe has a fixed structure — **Problem**, **Snippet**, **Why it works** —
designed to be copy-pasted.

Intent → recipe map:

| If the user is asking about… | Recipe slug |
|---|---|
| tools being called in loops / stuck retrying / won't stop calling X | `tool-call-discipline` |
| agent inventing flags, filenames, commands, or CLI options that don't exist | `hallucination-mitigation` |
| whether to enable thinking mode, how deep it should be, `adaptive` vs fixed | `thinking-mode-tuning` |

If the question matches one of these three, query tier 1:

```
deepwiki.ask_question(
  repoName = "frogasia/ilmuclaw-cookbook",
  question = "In the <slug> recipe under recipes/, what are the Problem,
              Snippet, and Why-it-works sections? Return the Snippet verbatim."
)
```

**Response shape:** framing line + snippet verbatim + one-line why + link to
`https://github.com/frogasia/ilmuclaw-cookbook/blob/main/recipes/<slug>.md`.
Keep it short — the snippet is the payload, everything else is scaffolding.

If the question is OpenClaw-domain but doesn't match a recipe (install,
onboarding, gateway, auth, provider setup, tools, config schema, CLI
behaviour, error messages, etc.), skip to tier 2.

## Tier 2 — official docs

Query `openclaw/docs` with a **targeted** question that names the topic the
user is actually hitting, not the general area.

```
deepwiki.ask_question(
  repoName = "openclaw/docs",
  question = <concrete question — name the command, flag, config path,
              or error code the user mentioned, not just the category>
)
```

Example — user says *"`openclaw onboard` keeps failing with E_GATEWAY_PROBE"*:

```
question = "What does the E_GATEWAY_PROBE error from `openclaw onboard` mean,
            and what flags skip the failing check?"
```

**Response shape:** quote or paraphrase what the docs said, name the specific
flag / command / config path, and end with a link to the relevant page under
<https://github.com/openclaw/docs/blob/main/> (use the file path the DeepWiki
response referenced; if none, link the docs repo root).

If the docs response is **shallow**, escalate to tier 3. Concrete shallowness
tells — at least one of:

- The response describes a feature exists but doesn't name the specific flag,
  command, config path, or error code the user needs.
- The response ends with "refer to the source" / "see the implementation"
  or similar.
- The response answers a neighbouring question but doesn't address the
  user's specifics.
- The response is noticeably shorter than the question's specificity warranted.

## Tier 3 — source code (last resort)

Only when tier 2 was shallow. Source-level answers are useful for questions
like "what are the exit codes of `openclaw onboard`?" or "where is the
gateway port configured?" — things the docs may not enumerate.

```
deepwiki.ask_question(
  repoName = "openclaw/openclaw",
  question = <concrete source-level question>
)
```

**Hard rule at tier 3:** your reply must quote a concrete file path or code
identifier that the DeepWiki response named. Do not assert that a function,
variable, constant, or flag exists in the source unless the DeepWiki
response literally referenced it. Source-code synthesis is the highest
hallucination-risk tier; anchoring to a named file is the guardrail.

**Response shape:** one-line answer + the quoted file path / identifier +
link to `https://github.com/openclaw/openclaw/blob/main/<path>` if DeepWiki
named a path, otherwise link the repo root and say you couldn't pin down the
exact file.

## When to decline or fall back

Use whatever tier's link is most relevant for where the user was headed,
rather than defaulting to a generic index:

- **DeepWiki MCP isn't in your tool list.** The user likely hasn't run the
  cookbook installer, or removed the MCP. In one sentence, link the most
  relevant repo — the cookbook recipe for tier-1 intents, `openclaw/docs`
  for tier-2, `openclaw/openclaw` for tier-3 — and mention that DeepWiki
  indexes these at `https://deepwiki.com/<org>/<repo>` if they want an
  agent to reach them. Phrase as a suggestion.
- **Repo not indexed**, or MCP error ("not indexed" / "not found"). Same
  soft suggestion with the specific repo link.
- **All queried tiers came back empty or off-topic.** Say so plainly in
  one sentence and link the most relevant repo. Don't guess. Don't caveat
  a partial answer into looking confident.

Worked example of a decline (user asked about tool-call loops):

> I couldn't pull a grounded answer from the cookbook or the OpenClaw docs
> just now — the DeepWiki lookups came back empty. The full recipe for
> this lives at
> <https://github.com/frogasia/ilmuclaw-cookbook/blob/main/recipes/tool-call-discipline.md>
> if you want to read it directly.

## Out of scope

Stay silent if the question is not OpenClaw-domain — generic programming,
non-OpenClaw LLM questions, general DevOps, unrelated tool troubleshooting.
OpenClaw-domain means: OpenClaw CLI, gateway, onboarding, config, tools,
schema, agents, skills, MCP, provider setup, error codes, or agent
reliability when running on OpenClaw.
