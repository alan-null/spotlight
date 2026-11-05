# Repeatable performance measurements

This harness uses the Python standard library and Bash, with optional GNU time for accurate process memory measurements. Run it against any Spotlight revision without copying the harness into that revision. It does not impose timing assertions on the test suite.

## Continuous integration

The [GitHub Actions workflow](../.github/workflows/ci.yml) runs on pushes, pull requests, and manual dispatches in the Spotlight repository. It runs the regression suite and harness checks on Python 3.11 and 3.14. A separate job builds the benchmark Docker image with GNU time, resolves its immutable image ID, and runs all scenarios with 30 samples and three warmups using the constrained Docker runner described below. Download the JSON report from the run's `spotlight-benchmarks-<commit>` artifact; artifacts are retained for 30 days.

Test failures and benchmark execution errors fail CI. Timing values are informational: shared runners and images rebuilt across workflow runs are not stable enough for performance thresholds or direct historical comparisons. Use the same immutable image and machine for controlled revision comparisons. CI does not run the interactive terminal smoke script; run it separately with real fzf and tmux as described below.

## Run locally

```sh
python3 benchmarks/run.py --source . --runs 30 --output /tmp/spotlight-before.json
bash benchmarks/docker-run.sh . --runs 30 > /tmp/spotlight-container.json
```

The Docker runner defaults to the existing local Python 3.12 slim image ID `a6e34c598f24`. No image build, package installation, network, or host Node/Python packages are required for timings. RSS is null when GNU time is absent. To use another image containing Python 3.11+ and Bash, set `SPOTLIGHT_BENCH_IMAGE` to an immutable local image ID or a registry reference ending in `@sha256:<digest>`. Mutable tags are rejected, and `--pull=never` prevents accidental image changes. This local default is machine-specific; share or load the same image on another machine before running. The report records the supplied image identity, runtime, CPU model, kernel, actual cgroup limits, source hash, fixtures, and every timing sample.

The container has one CPU of quota, 256 MiB memory with no additional swap, a 128-process limit, a 128 MiB temporary filesystem, no network, a read-only source mount, and a read-only root filesystem. Fixtures and application caches live in temporary memory. The image needs no fzf, tmux, or Git: controlled shell drivers replace fzf and Git. For RSS measurements, the optional Dockerfile adds GNU time to Python slim. Build that image once, then use its immutable image ID for all comparisons:

```sh
docker build -f benchmarks/Dockerfile -t spotlight-bench benchmarks
SPOTLIGHT_BENCH_IMAGE=$(docker image inspect spotlight-bench --format '{{.Id}}') bash benchmarks/docker-run.sh . --runs 30 > /tmp/spotlight-container.json
```

The Dockerfile accepts `--build-arg BASE_IMAGE=python@sha256:<digest>` when a pinned base is available. Its default base tag and apt package resolution can change between builds; reuse the exact built image for comparisons. The build needs network access and is separate from benchmark execution.

## What is measured

| Scenario | Scope |
| --- | --- |
| `theme_bootstrap` | Python startup, theme parsing, shell assignments |
| `actions_warm_cache_200` | Python startup and an existing 200-action disk cache |
| `actions_cold_cache_200` | Python startup, parsing 200 actions, cache construction; application cache removed before each sample |
| `module_preview_inherited_theme` | Actual tmux module static command preview, with the same inherited theme values used by preview children |
| `launcher_commands_driver_200` | Full launcher through generation and consumption of the first Commands tab, then cancellation; warm action cache |
| `launcher_commands_recent5_driver_200` | The same 200-action launch with five deterministic recent invocations, including lookup and promotion |
| `launcher_files_driver_1000` | Full launcher through discovery and consumption of 1,000 files outside Git, then cancellation |

The launcher scenarios use a minimal Bash fzf driver that drains stdin and cancels. They measure startup, discovery, formatting, and launcher teardown, **not real fzf rendering, interactive responsiveness, tmux IPC, popup drawing, or terminal latency**. The fixtures force a known context outside tmux and Git and clear inherited Spotlight configuration. Fixtures and warm-cache preparation are outside the measured region. Runs include three discarded warmups by default. Timings include process creation. Median and nearest-rank p95 are milliseconds; more samples make p95 less noisy.

Fixture version 2 adds five deterministic history entries in an isolated state directory and a populated-history scenario. Older Spotlight revisions can run against the same harness; they simply ignore the history fixture. Reports from fixture versions 1 and 2 must not be compared directly. History writes happen after successful selection, so the canceling driver does not measure persistence latency; the regression suite covers atomic writes and concurrent writers.

`peak_process_rss_kib` is GNU time maximum resident memory for the measured command and waited descendants: the largest individual process footprint, **not summed concurrent process-tree memory**. The parent benchmark Python process and fixture creation are excluded from that metric, but count toward the container memory limit. Direct Python `wait4` accounting is deliberately avoided because the inherited Python fork footprint can inflate the peak of small Bash commands. GNU time contributes a small, consistent launch overhead; compare reports using the same RSS tool. The metric is useful for spotting Python startup/import regressions; use a separate cgroup profiler if aggregate launch memory becomes a concern.

## Compare revisions

Use the same harness and immutable image, run counts, fixture version, machine, and limits. A source checkout can be a separate Git worktree. Store results outside the read-only source mount by redirecting Docker stdout.

```sh
bash benchmarks/docker-run.sh /absolute/path/to/before/spotlight --runs 50 > /tmp/before.json
bash benchmarks/docker-run.sh /absolute/path/to/after/spotlight --runs 50 > /tmp/after.json
python3 benchmarks/run.py --compare /tmp/before.json /tmp/after.json
```

The comparison prints median changes and warns about differing image/runtime/kernel/CPU/resource metadata, RSS tool, harness hash, run count, and warmup count. Negative percentages indicate improvement. Reports include the source revision when Git is available, a hash of the measured source files even when Git is absent or the tree is dirty, and the harness hash. Keep the raw reports for review; JSON files in this directory are ignored by Git. Repeat before/after runs in alternating order on an otherwise idle machine; treat small differences as noise until repeated. Docker CPU quota restricts CPU time, but does not standardize hardware speed, frequency scaling, thermal state, scheduler contention, architecture, or host kernel. One CPU of quota also does not pin execution to one physical core. A dedicated runner on the same machine gives more comparable results than nominally identical quotas across laptops.

Check the harness itself without imposing performance thresholds:

```sh
python3 -m unittest discover -s benchmarks -v
```

“Cold cache” here means the Spotlight action cache is absent. It does not mean a cold operating-system page cache; this harness never drops host caches. Docker shares the host kernel and filesystem cache. Image startup and fixture construction are also excluded from the samples. These are application component measurements, not a complete end-to-end latency guarantee.

For less sensitivity to host drift, alternate revisions automatically:

```sh
python3 benchmarks/paired.py /absolute/path/to/before/spotlight /absolute/path/to/after/spotlight --runs 20 --output-dir /tmp/spotlight-paired
python3 benchmarks/paired.py /absolute/path/to/before/spotlight /absolute/path/to/after/spotlight --docker --runs 20 --output-dir /tmp/spotlight-paired-docker
```

Each pass measures both revisions, reversing their order on alternate passes. It uses the same `run.py` fixtures and accounting with one measured sample per scenario per pass, recreating fixtures outside measurement. Two full warmup passes are discarded by default. The output directory contains aggregate before/after reports with all samples. Source or environment changes within a revision fail the run; differences between revisions are reported as comparison warnings. The Docker option starts a separate constrained container per revision and pass; container startup remains outside measured samples. Pairing reduces drift but cannot remove contention or make different hosts equivalent.

## Real terminal smoke test

Use a real tmux session with fzf installed to exercise behavior separately: open Commands, switch through tmux tabs and Files, open previews, refresh Commands, change a theme, cancel, then reopen through the popup binding. Check that queries survive tab switching, unavailable modules disappear on a fresh launch, selection targets the originating pane, and the popup uses the current theme. Run the launcher once outside tmux as well. Do not call a controlled-driver timing result a real-terminal smoke test.

The optional [PTY smoke script](../tests/smoke_terminal.py) exercises real fzf and a private tmux server without reading user configuration. Run `python3 tests/smoke_terminal.py`; use `--outside-only` when private tmux sockets are unavailable. It verifies cancellation and exact command insertion without execution, then popup navigation, refresh, originating-pane insertion, and theme persistence. It uses bounded waits and cleans up only its own server. GUI/terminal appearance still benefits from a manual check in the target terminal.
