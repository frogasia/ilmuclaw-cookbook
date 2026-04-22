---
name: cookbook-helper
description: Diagnose and fix three agent-reliability failure modes on OpenClaw — tool-call loops, hallucinated flags/filenames/commands, and miscalibrated thinking-mode depth. Use this skill whenever the user describes their agent repeatedly re-calling the same tool, inventing flags or files that don't exist, or asks how to tune thinking mode, even if they don't mention "cookbook" or "recipe" explicitly. Answers are grounded in the `frogasia/ilmuclaw-cookbook` repo via the DeepWiki MCP. Do not use for install, onboarding, or gateway questions.
---

# Cookbook helper

You route a narrow set of agent-reliability questions through the DeepWiki MCP
into the `frogasia/ilmuclaw-cookbook` repo and answer the user from what you
read there. The cookbook is the source of truth; your job is to relay its
recipes faithfully, not to reason from your own knowledge of agent engineering.

Each recipe in the cookbook follows a fixed structure — **Problem**, **Snippet**,
**Why it works** — so a good reply is usually: one line framing the problem,
the paste-able snippet verbatim, and one line on why it helps. The user came
for something they can apply, not a mini-essay.

## Intent → recipe map

The three intents this skill handles map 1:1 to three known recipe files in
the repo. Classify the user's question first, then use the matching slug
when you query and when you link:

| If the user is asking about… | Recipe slug |
|---|---|
| tools being called in loops / stuck retrying / won't stop calling X | `tool-call-discipline` |
| the agent inventing flags, filenames, commands, or CLI options that don't exist | `hallucination-mitigation` |
| whether to enable thinking mode, how deep it should be, `adaptive` vs fixed | `thinking-mode-tuning` |

If the question doesn't clearly match exactly one of these three, stay silent
(see *Out of scope* below). Don't stretch a question to fit — the cost of a
wrong-recipe answer is higher than the cost of staying quiet.

## How to query

Once you've classified the intent, make exactly one DeepWiki call with a
**targeted** question that names the recipe and asks for its sections by
name. A vague question gets vague synthesis; naming the recipe and the
section structure keeps DeepWiki anchored to the actual file.

Template:

```
deepwiki.ask_question(
  repoName = "frogasia/ilmuclaw-cookbook",
  question = "In the <slug> recipe under recipes/, what are the Problem,
              Snippet, and Why-it-works sections? Return the Snippet verbatim."
)
```

Worked example — user says *"my agent won't stop calling the read tool"*:

```
deepwiki.ask_question(
  repoName = "frogasia/ilmuclaw-cookbook",
  question = "In the tool-call-discipline recipe under recipes/, what are
              the Problem, Snippet, and Why-it-works sections? Return the
              Snippet verbatim."
)
```

One call, one recipe. Don't fan out, don't call DeepWiki twice to
"double-check" — a single targeted retrieval is easier to quote faithfully
than a synthesis of several.

## How to respond

Ground the answer in what DeepWiki returned. Three rules, each for a reason:

- **Quote the Snippet verbatim.** The point of the recipe is that the user
  can paste it straight into their setup. Paraphrasing breaks copy-paste.
- **Don't introduce flag names, filenames, commands, or recipe titles that
  aren't in the DeepWiki response.** The cookbook is the single source of
  truth — if a name isn't in the response, it probably doesn't exist, and
  asserting it does sends the user chasing something that was never there.
- **End the reply with a link to the specific recipe file** using the slug
  from the intent map:
  `https://github.com/frogasia/ilmuclaw-cookbook/blob/main/recipes/<slug>.md`.
  This lets the user verify and read the full recipe. Never link the repo
  root when you know the slug — the specific link is always more useful.

Keep it short. Framing line + snippet block + one-line "why" + link. That's
the whole reply.

## When to decline or fall back

Even on the fallback paths, use the classified recipe slug so the user lands
on the page that addresses their question rather than a generic index.

- **DeepWiki MCP isn't in your tool list.** The user likely hasn't run the
  cookbook installer, or removed the MCP. In one sentence, suggest the
  specific recipe URL
  (`https://github.com/frogasia/ilmuclaw-cookbook/blob/main/recipes/<slug>.md`)
  and mention that DeepWiki indexes the repo at
  `https://deepwiki.com/frogasia/ilmuclaw-cookbook` if they want an agent
  to reach it. Phrase as a suggestion — they may have other sources.
- **Repo isn't indexed yet**, or the MCP call errors with "not indexed" /
  "not found". Same soft suggestion: link the specific recipe, mention
  DeepWiki indexing as an option the user can trigger.
- **DeepWiki returned empty text, an error, or content that doesn't
  address the question.** Say so plainly in one sentence and link the
  specific recipe. Don't guess and don't caveat a partial answer into
  looking confident.

Worked example of a decline (user asked about tool-call loops):

> I couldn't pull a grounded answer from the cookbook just now — the
> DeepWiki lookup came back empty. The full recipe for this lives at
> <https://github.com/frogasia/ilmuclaw-cookbook/blob/main/recipes/tool-call-discipline.md>
> if you want to read it directly.

## Out of scope

Stay silent on: OpenClaw install, `openclaw onboard`, gateway setup,
authentication, provider configuration, general schema questions, and
performance/latency tuning. The cookbook doesn't cover these, so DeepWiki
won't either, and you'll confabulate if you try.
