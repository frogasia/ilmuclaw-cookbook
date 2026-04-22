# Test harness

End-to-end test for [`install.sh`](../install.sh) against a containerised OpenClaw. Never touches your host `~/.openclaw`.

## Quick start

```sh
docker compose -f test/docker-compose.yml run --rm cookbook-test
```

Expected final line:

```
all assertions passed
```

## What it does

1. Spins up the OpenClaw container with a fresh, ephemeral config volume.
2. Runs `openclaw init --non-interactive` to produce a baseline `openclaw.json`.
3. Runs `./install.sh` twice back-to-back — the second run is the idempotency check.
4. Asserts the expected state with `openclaw config get` and file checks:
   - `agents.defaults.thinkingDefault` contains `adaptive`
   - `agents.defaults.tools.deny` contains `canvas`
   - `agents.defaults.tools.allow` contains `read`
   - `~/.openclaw/workspace/skills/cookbook-helper/SKILL.md` exists
5. Invokes one atomic sub-command (`install.sh apply deepwiki-mcp`) to confirm targeted dispatch works.

## Using a local image

If the published `openclaw/openclaw` image is not yet available, build one locally and pass it in:

```sh
COOKBOOK_TEST_IMAGE=openclaw-local:latest \
  docker compose -f test/docker-compose.yml run --rm cookbook-test
```

## Testing a different branch

By default the script pulls the SKILL from the `main` branch. To test a feature branch:

```sh
COOKBOOK_REF=feat/install-script \
  docker compose -f test/docker-compose.yml run --rm cookbook-test
```
