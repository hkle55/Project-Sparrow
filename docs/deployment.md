# Deployment (Milestone 5)

**Status: prepared, not deployed.** Nothing has been purchased or created. Owner approval is
needed before anything that costs money.

## Requirements

- Reachable from a phone in Philadelphia with the laptop off. HTTPS.
- **Always on.** Two reasons:
  1. The collector must poll every 30 s, or validation data has holes.
  2. A cold start (30–60 s on some free tiers) when she opens the app at the bus stop is
     exactly the failure Sparrow exists to prevent.
- Persistent disk for the SQLite prediction log (about 5–10 MB/day).
- Private commute config as a secret, not in the public repo.
- Deploy automatically from GitHub, with minimal maintenance and low cost.
- Small footprint: measured ~75 MB RSS while serving and collecting, so the smallest
  instances are enough.

## Options compared (prices researched 2026-11-18; verify before buying)

| Option | Always on? | Persistent disk | HTTPS / auto-deploy | Est. monthly | Verdict |
|---|---|---|---|---|---|
| **Fly.io**: shared-cpu-1x 256 MB, `iad` (Ashburn) + 1 GB volume | Yes, with auto-stop off | Volume, ~$0.15/GB | Automatic HTTPS; GitHub Action | **≈ $2.35** ($2.19 VM + $0.15 volume) | **Recommended** |
| Railway Hobby | Yes (sleep is opt-in) | Volume (5 GB on Hobby) | Yes / built-in GitHub deploys | **$5** (includes $5 of usage) | Good runner-up, simplest UI |
| Render Starter + disk | Yes | Disk $0.25/GB, paid instances only | Yes / built-in | **≈ $7.25** | Fine, but costs the most |
| Render Free | **No**: sleeps after 15 min idle, 30–60 s wake | **None** (logs lost on restart) | Yes | $0 | ✗ Breaks collection and cold-starts at the bus stop |
| Koyeb Free | **No**: scales to zero after 1 h idle (not configurable) | Not on free | Yes | $0 | ✗ Same problem |
| Google Cloud Run | Scales to zero unless min-instances ≥ 1 (then billed) | No local disk (SQLite unsuitable) | Yes | $0 sleeping / more always-on | ✗ Wrong shape for SQLite + background loop |
| Oracle Cloud Always Free VM | Yes | Yes | You run TLS (Caddy), updates, deploys | $0 | ✗ for now: real maintenance, and idle VMs (<20% CPU/net/mem for 7 days) can be reclaimed, which Sparrow's tiny load could trigger |

Sources: [Fly.io resource pricing](https://fly.io/docs/about/pricing/),
[Fly.io 2026 price change notes](https://hostim.dev/blog/fly-io-pricing-2026/),
[Render free tier sleep](https://render.com/docs/your-first-deploy),
[Render free vs Starter](https://actualdatabase.com/render-free-vs-starter-pricing/),
[Render disk pricing](https://actualdatabase.com/render-disk-and-bandwidth-cost/),
[Railway plans](https://docs.railway.com/pricing/plans),
[Koyeb scale-to-zero](https://www.koyeb.com/docs/run-and-scale/scale-to-zero),
[Oracle Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/resourceref.htm),
[Oracle idle reclamation](https://bestusavps.com/reviews/oracle-cloud/).
Several figures come from third-party summaries. Confirm on the provider's own pricing
page at signup.

**No free tier meets the requirements.** Every free web tier found either sleeps or has no
persistent disk. Keeping one awake with an external pinger is unsupported, and it still
doesn't give a durable disk.

## Recommendation: Fly.io, about $2–3/month

- Cheapest always-on option with a real volume. The `iad` region is ~200 km from
  Philadelphia.
- `fly.toml` disables auto-stop and keeps one machine running.
- HTTPS certificate and `*.fly.dev` hostname are automatic.
- Secrets (`fly secrets set`) hold the private config and access token. They're
  encrypted and never in git.
- Deploys from GitHub Actions after CI passes (`.github/workflows/deploy.yml`, off until
  enabled).
- Trade-offs: needs a credit card. A volume pins the app to one machine, so each deploy
  restarts it (~10–20 s of downtime, and the collector misses one or two polls). A volume
  lives on one host, so take periodic backups (below).

If you'd rather click through a dashboard than use a CLI, **Railway at $5** is the
runner-up.

## What's already prepared in the repo

- `Dockerfile`: Python 3.12 slim, non-root user. Collector on by default. DB at
  `/data/sparrow.sqlite`.
- `fly.toml`: `iad`, always on, `/health` check, 256 MB, volume at `/data`.
- `.github/workflows/deploy.yml`: deploys `main` after CI succeeds, **only if** the repo
  variable `DEPLOY_ENABLED=true` and the secret `FLY_API_TOKEN` exist.
- CI `docker` job: builds the image and smoke-tests it on every push.
- App support:
  - `SPARROW_CONFIG_TOML` (the profile contents, as a secret), or `SPARROW_CONFIG_JSON` for
    hosts that only allow single-line values
  - `SPARROW_ACCESS_TOKEN` (required on every route except `/health`)
  - Forwarded-proto handling, so the token cookie is `Secure`

## Access control and privacy

- Set `SPARROW_ACCESS_TOKEN` to a long random string (`openssl rand -hex 24`).
- On her phone, open `https://<app>.fly.dev/?key=<token>` once. A year-long, HttpOnly,
  Secure cookie is set. Then bookmark `/` and `/observe`. The ESP32 will send the
  `X-Sparrow-Token` header.
- Without the token, nothing but `/health` responds, so the stop names, live commute,
  and observation log aren't public.
- The `*.fly.dev` name doesn't need to say anything personal (e.g. `sparrow-k7q2`).

## Owner steps to deploy (after approval)

```bash
brew install flyctl            # or: curl -L https://fly.io/install.sh | sh
fly auth signup                # requires a card
```

From the repo root, set `app = "<name>"` in fly.toml first:

```bash
fly apps create <name>
fly volumes create sparrow_data --region iad --size 1
fly secrets set SPARROW_ACCESS_TOKEN=$(openssl rand -hex 24)
fly secrets set SPARROW_CONFIG_TOML="$(cat config/commute.local.toml)"
fly deploy
```

For automatic deploys:

```bash
fly tokens create deploy
```

Then in GitHub: Settings → Secrets and variables → Actions:
- add the secret `FLY_API_TOKEN`
- add the variable `DEPLOY_ENABLED=true`

Check it's up: `curl https://<name>.fly.dev/health`. View logs with `fly logs`.

## Backups

The prediction log is only research data, but losing it would cost weeks. Fly takes daily
volume snapshots (retained 5 days by default). For an off-host copy:

```bash
fly ssh sftp get /data/sparrow.sqlite ./data/sparrow-backup.sqlite
```

## Uptime monitoring (optional, free)

Point an external monitor (e.g. UptimeRobot free) at `/health` every 5 min to get an email
when it's down. It needs no token. Don't rely on it to keep the app awake: Fly is
configured to stay up regardless.
