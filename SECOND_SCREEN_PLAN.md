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

## Phase B2 — Typed app data + data hub

Move the current transit-shaped runner state into typed, named app data:
- Add `AppData` with optional `weather`, `subway`, and `bikes` payloads, plus
  typed `DataKey` values (`weather`, `subway`, `bikes`).
- Add `DataHub` to subscribe to the existing services, store the latest
  `AppData`, start/stop feeds, and notify the runner on source updates.
- Change `RenderContext` to carry `data: AppData` and `now`; panes read source
  payloads through `ctx.data`.
- Transit requires `weather` + `subway`; bikes remain optional and render as
  placeholders when missing. Hello requires no data.
- Keep `getImage(...)` backward compatible for golden tests by wrapping legacy
  weather/train/bike arguments into `AppData`.
- No intended visual change, cadence tuning, new screen behavior, or e-ink
  quality work in this phase.

## Phase B3 — Display intent + transition waveforms

Split display updates by intent instead of overloading `clear=True`:
- Add a display intent model with `normal`, `screen_transition`, and
  `maintenance_clear`.
- Screen switches use `screen_transition`: a user-driven full-screen GLR16 update
  that is allowed through immediately.
- Hourly anti-ghosting keeps the maintenance path.
- The post-large-update cooldown suppresses routine `normal` churn after a
  screen transition or maintenance clear, so a large GLR16 update is not followed
  immediately by a full-screen DU tick.
- Keep the current `partial`/`clear` arguments temporarily for compatibility,
  but treat intent as the source of waveform/cooldown policy.
- No new pane-level waveform selection yet; this creates the hook for future
  screen/pane profile fidelity.

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

**Phase gate:** after each implementation phase, stop for local + Raspberry Pi
manual testing before starting the next phase. Do not begin Phase B/C/D follow-up
work until the previous phase has passed both environments.

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
- **Phase A:** COMPLETE. Runner timing now has an injected clock and the runner
  decision path is covered by a recording fake display.
- **Phase B:** CODE COMPLETE, pending D2 manual testing. `Screen` now owns
  `requires()`, `should_redraw(ctx, prev_ctx)`, and a lightweight display
  profile. Transit redraws when the displayed seconds value, top-two trains, or
  subway availability changes. Hello declares no required data and no regular
  redraws.
- **Phase B2:** COMPLETE. Runner now owns lifecycle/timing/display decisions
  only; `DataHub` owns feed subscriptions and latest typed `AppData`. Mac and
  Pi manual gates passed on commit `2d59e8b`.
- **Operational fixes:** CODE COMPLETE, pending Mac + Pi manual testing. Feed
  loops now stop promptly, Open-Meteo has a request timeout, and initial weather
  failures retry quickly instead of waiting a full weather interval.
- **Phase B3:** CODE COMPLETE, pending Mac + Pi manual testing. Display updates
  now carry explicit intents so screen transitions are immediate full-screen
  GLR16 updates, while routine redraws are blocked briefly after large updates.
- **Phase C:** NOT STARTED. Phase B added guard tests for its own contract and
  runner behavior, but the broader Phase C checklist is gated on D2 local + Pi
  manual testing. Pixel goldens are still transit-only; add the hello golden
  only after D2 passes.
- **Pi timing note:** After Phase A, the physical panel showed skipped seconds
  (example: 25, 27, 31, 34, 35, 36, 37, 38, 40) rather than a steady 1 Hz
  cadence. That matches the current display pipeline: the runner can generate a
  frame every second, but the async display queue keeps only the latest pending
  frame and the IT8951 update can take longer than one second. Phase B preserves
  transit's requested every-displayed-second redraw behavior, while preventing
  static screens from churning. Next e-ink quality work should decide whether to
  remove seconds, update only the seconds glyph, or instrument actual panel
  update latency before tuning cadence.
- **Debug timing instrumentation:** `DEBUG_FRAME_HISTORY=true` keeps
  `debug_output/current_display.png` behavior and also saves timestamped frames
  to `debug_output/frames/` with per-frame queue timing in
  `debug_output/frame_manifest.csv`. The Pi path logs consumed frame metadata,
  queue wait/overwrite counts, and full/partial e-ink update durations.
