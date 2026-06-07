# Second Screen / Render Engine: Refactor & Test Plan

Make each `Screen` self-describe its data needs, redraw triggers, and render
style, so the runner becomes a generic engine instead of a transit-specific
controller. Safety is verified by extending the golden approach to control-flow
decisions, plus phased manual testing on the device.

## Why (current coupling)

The runner embeds transit-specific logic that should live on the screen:
- A data gate: `_check_display_update` returns early unless `weather` + `trains`
  are present.
- Train change-detection: `_get_top_two_trains`, `_has_significant_change`,
  `_previous_top_trains`, `_previous_subway_unavailable`.
- A transit-shaped cadence: the 1 s loop repaints every second because the clock
  shows seconds.

## Phase A — Engine seam (no behavior change)

- Inject a **clock** into the runner's timing (interval + hourly checks) so its
  decisions can be driven deterministically (the `now`-injection pattern we use
  for rendering, extended to the runner).
- Keep the decision methods (`handle_*_update`, `_check_display_update`)
  synchronous and callable directly in tests — no service threads required.
- Add a **recording fake `Display`** that logs each `update(partial, clear, screen)`.
- Deliverable: runner decisions are drivable headlessly. Behavior unchanged →
  pixel goldens and manual smoke stay green.

## Phase B — Screen contract (this is "how screens get timing info")

Add to `Screen`: `requires() -> set[str]`, `should_redraw(ctx, prev_ctx) -> bool`,
and `profile` (waveform / binarize; may start waveform-only).
- **Timing model:** the engine ticks at a base cadence (1 s) *and* on data
  events; each tick builds a `ctx` carrying `now` and asks the active screen
  `should_redraw(ctx, prev)`. A clock screen returns True when the *displayed*
  time changed; a static screen returns False. No per-screen scheduler.
- transit: `requires={weather,trains}`; `should_redraw` = displayed-time changed
  OR top-2 trains changed OR availability flipped (moved out of the runner).
- hello: `requires=set()`; `should_redraw=False`.
- Runner delegates the gate and redraw decision to the active screen; the
  hardcoded weather/train gate and `_has_significant_change` are removed.

## Phase C — Automated tests

1. **Pixel goldens** (existing): transit unchanged confirms the render path is
   untouched; add a hello golden.
2. **Pure unit tests:** `requires()` and `should_redraw()` per screen with
   constructed contexts; the waveform-selection mapping as a pure function.
3. **Decision-trace (forward):** drive `engine.tick(now)` + simulated data events
   over a scripted timeline against the recording fake display; assert the
   `(render/skip, clear, screen)` sequence matches intended behavior.
4. **Engine gating:** no required data → no render; switch → one forced clean
   redraw; static screen → no per-tick repaints.

Explicitly **out of scope:** characterizing the *current* runner as a baseline
(expensive — monkeypatching its time, driving it pre-refactor); and tracing the
`EInkDisplay` waveform/partial-vs-full decisions (Pi-only `IT8951`) — instead
extract those as pure functions (`select_waveform`, `partial_or_full`) and
unit-test the mappings.

## Phase D — Phased MANUAL testing (you), gated to each phase

Run on the Mac (`DEBUG=true`, `QUIET_MODE=false` so logs show) and on the Pi
(interactive run; stop the service first so they don't fight over the panel).

### D1 — after Phase A: baseline unchanged
- [ ] Mac: `uv run runner.py` → transit renders; clock ticks each second; data
      populates; no new errors in the log.
- [ ] Pi: service runs normally; panel updates as before.
- Pass criteria: indistinguishable from pre-refactor behavior.

### D2 — after Phase B: screen contract + switching
- [ ] Mac: transit still updates each second / on data (cadence unchanged).
- [ ] Mac: press `2` → hello shows immediately, even before weather/trains load.
- [ ] Mac: press `1` → transit resumes updating.
- [ ] Mac: on hello, the saved frame does **not** churn every second (static; no flicker).
- [ ] Pi: switch transit↔hello on the panel — transit cadence unchanged; switch
      is a single clean full refresh.
- Pass criteria: switching works both directions; transit behavior unchanged;
  hello is not gated on data; no static-screen churn.

### D3 — after Phase C: regression + e-ink quality
- [ ] Pi: ~1-hour soak on each screen — no new ghosting/latency vs current main.
- [ ] Pi: switch latency and switch flash are acceptable.
- Pass criteria: no quality regression vs `main`; switching is solid.

## Tracking / status

- **This doc is the durable plan** (survives sessions/compaction). Live progress
  is also mirrored in the session task list.
- **Status:** PLANNED. Next action: Phase A on branch `second-screen`.
