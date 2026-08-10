# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SMM3 is a smart-meter monitoring system for M5Stack devices. A parent unit reads electricity usage from a smart meter via the BP35A1 Wi-SUN module and broadcasts it over ESP-NOW; one or more child units receive the data and display it, supporting multiple visualization modes and real-time power tracking.

The codebase includes three program variants (pick based on hardware and meter capability):
- **Standard**: Full history tracking (requires 30+ days of smart meter history)
- **Lite** (`lite/`): Limited to 13-day history (for meters with shorter retention)
- **ATOM S3**: Optimized for constrained ATOM S3 hardware (128×128 display, 512KB SRAM, no PSRAM) — main active development target

## Two Runtimes — Do Not Mix Them Up

This repo contains code for **two unrelated firmware/language environments**. Always check which one a file belongs to before applying fixes from the other:

| Aspect | M5Stack UIFlow MicroPython | CircuitPython |
| --- | --- | --- |
| Files | `smm3_main_web.py`, `smm3_sub.py`, `smm3_sub_core2.py`, `bp35a1.py`, `func_main.py`, `func_sub.py`, `func_sub_core2.py`, `calc_charge.py`, `calc_charge/`, `lite/*`, `ambient/*` | `smm3_sub_atoms3.py`, `smm3_sub_atoms3r.py`, `test_atoms3/*` |
| Devices | M5StickC Plus (parent), M5Stack Basic, M5Stack Core2 | M5Stack ATOM S3 / ATOM S3R |
| Telltale imports | `from m5stack import ...`, `m5stack_ui`, `machine`, `wifiCfg`, `ntptime`, `urequests` | `board`, `busio`, `digitalio`, `displayio`, `adafruit_display_text`, `adafruit_bitmap_font` |
| ESP-NOW API | `espnow.broadcast(data=...)`, `espnow.recv_data()` — no peer objects | `espnow.ESPNow()` + `espnow.Peer(...)`, `.send(message, peer)` |

Wire protocol is shared: both sides exchange the same string-based messages (`M:CUML...`, `REQ00`–`REQ30`, ...), which is how parent/child interoperate despite the API difference.

The "CircuitPython Constraints" section below (f-strings, `decode()`, ESP-NOW argument order, etc.) applies **only** to the right-hand column. Do not apply it when editing `smm3_main_web.py`, `smm3_sub.py`, `smm3_sub_core2.py`, or anything under `lite/`.

`smm3_main.py` / `lite/smm3-lite_main.py` (the pre-Web-dashboard parent programs, without hard WDT / freeze defenses) were moved to `archives/` on 2026-08-09 and are no longer part of the active codebase — see the `archives/` row below.

## Development Environment

**CircuitPython side** (ATOM S3): CircuitPython 9.2.9 confirmed working; 10.x (tested with 10.2.1) showed misbehavior, cause not recorded — stick to 9.x. Use `circup` for libraries:
```bash
circup install adafruit_display_text adafruit_bitmap_font adafruit_ticks
```

**UIFlow MicroPython side** (parent / Basic / Core2): M5Stack's MicroPython fork (UIFlow firmware, "V1.10.2 or later" per `README.md`), deployed by copying files into `/apps/` and the root of the device per the layout in `README.md` section 4 (ファイル構成). No `circup`/pip step — `m5stack`, `m5stack_ui`, `machine`, `wifiCfg` etc. are built into the firmware. `ambient.py` and `logging.py` are optional/external deps fetched from the URLs listed in `README.md`, not part of this repo.

## File Organization

| Path | Purpose |
|------|---------|
| `smm3_main_web.py` | **Current parent unit** (UIFlow MicroPython) — GAS dashboard upload, hard WDT, and freeze defenses. This is what runs on the deployed device; see `docs/ARCHITECTURE.md` §5 before touching its send paths. The pre-Web `smm3_main.py` this was derived from is archived (see `archives/` row) |
| `smm3_sub_atoms3.py` | Child unit for ATOM S3 (CircuitPython) — main active target |
| `smm3_sub_atoms3r.py` | Child unit for ATOM S3R (CircuitPython) — **partially working, paused**. Same code as `smm3_sub_atoms3.py` plus a guard that disables rotation when IMU init fails. Backlight stays off (I2C-controlled chip at 0x30 on the same GPIO0/GPIO45 bus that CircuitPython's `bitbangio` cannot write to); see the file's own docstring before touching |
| `smm3_sub_core2.py` | Child unit for Core2 (UIFlow MicroPython) — reference implementation for layout/algorithm logic |
| `smm3_sub.py` | Child unit for Basic (UIFlow MicroPython) |
| `bp35a1.py` | Wi-SUN module driver for smart meter communication (parent only) |
| `func_main.py` / `func_sub.py` / `func_sub_core2.py` | Config/UI helpers per device (Google Sheets config fetch, beep, status LED) |
| `calc_charge.py` | The charge-calculation module actually imported by `smm3_main_web.py` (`from calc_charge import CalcCharge`) — see "Modular Charge Calculation" below for how it gets there |
| `calc_charge/` | Source modules for charge calculation, one per power company, not imported directly |
| `lite/` | Alternative main programs (parent + Basic/Core2 children) for meters with short history. `smm3-lite_main_web.py` is the GAS/Web + freeze-defense variant (the pre-Web `smm3-lite_main.py` it was derived from is archived, see `archives/` row) |
| `ambient/` | Optional Ambient-integration variants of the parent program (`smm3_main_web_amb*.py`, `smm3-lite_main_web_amb*.py`) plus a lightweight self-contained Ambient client (`ambient_lite.py`). Not used by the mainline `smm3_main_web.py`/`smm3-lite_main_web.py` (memory-constrained tradeoff, see `ambient/README.md`) |
| `gas_dashboard/` | Google Apps Script web app (`Code.js`, `History.js`, `Dashboard.html`, `appsscript.json`) receiving the parent's HTTPS POSTs; History/InstLog data lives in a Google Sheet. Deploy note: changes need a **new deployment** (or `clasp deploy -i <id>`) to affect a given `/exec` URL — see `docs/ARCHITECTURE.md` §5 for the multi-deployment (production/sample/temp-share) setup sharing this one script. `SampleData.js` and the `isSampleDeployment()`/`isTempShareDeployment()` guards in `Code.js` are the repo owner's own infra for a public demo/temp-share deployment — irrelevant noise for anyone else's own deployment (always evaluates false for other deployment IDs). `Dashboard.dev.html` is a claspignored local-only reference copy, never pushed to GAS. `netlify_shell/` is a static iframe-wrapper template for hiding the GAS "unverified app" banner |
| `docs/` | Architecture documentation (`ARCHITECTURE.md`), extracted session insights, work-in-progress notes |
| `fonts/` | BDF font files for the ATOM S3 build (must be copied onto the device, see `fonts/README.md`) |
| `test_atoms3/` | CircuitPython test/mock programs for the ATOM S3 build |
| `config_files/` | Sample/template JSON config files (`config_main.json`, `config_sub.json`, `api_config.json`); underscore-prefixed versions are blank templates (only for files that carry personal placeholder values — `config_sub.json` has none, so it has no blank counterpart) |
| `archives/` | Frozen historical snapshots of old versions — not active code, do not edit. `20231021/`: an early full snapshot (`bp35a1.py`, `smm3_main.py`, `smm3_sub.py`). `20260809/`: the pre-Web-dashboard parent programs (`smm3_main.py`, `smm3-lite_main.py`) retired when `smm3_main_web.py`/`smm3-lite_main_web.py` became the sole recommended parent programs — see `archives/20260809/README.md` |
| `private/` | Gitignored local scratch files (real configs, ad-hoc test scripts) — not part of the shipped project |

## Key Architectural Concepts

### Hardware Constraints & Implications

**ATOM S3** (primary target, CircuitPython):
- 128×128 pixel display with ~5KB framebuffer
- 512KB SRAM total, no PSRAM — forces aggressive display batching
- F-string implicit concatenation (f"a" f"b") will crash; must use single f-string
- Data structures use `array.array()` instead of lists for memory efficiency
- Labels are often drawn directly to bitmap without intermediate objects

**Core2** (reference design, UIFlow MicroPython):
- 320×240 display, 8MB PSRAM — allows more flexible display management
- `smm3_sub_core2.py` is the reference for layout/algorithm logic; the ATOM S3 version adapts this logic into CircuitPython (different APIs, same display semantics)

### Communication Pattern

1. **Parent** (`smm3_main_web.py`) connects to smart meter and:
   - Broadcasts cumulative power data every 10 minutes (`M:CUML<collect>/<created>/<e_energy>/<monthly_e_energy>/<charge>`)
   - Responds to history requests from children (`REQ00`–`REQ30`)
   - Caches 30+ days of 30-minute history internally; re-fetch is forced with the parent's long-pressed B button

2. **Children** (ATOM S3/Core2/Basic) connect via ESP-NOW and:
   - Receive `M:CUML` (cumulative power + billing period metadata) on every broadcast
   - Request multi-day history (`REQ00`–`REQ30`) sequentially at startup
   - Re-render graphs when data arrives

Messages are plain strings on the wire, so parent and children interoperate even though the parent/Basic/Core2 side uses UIFlow MicroPython's `espnow` module and the ATOM S3 side uses CircuitPython's `espnow` module — these have different APIs (see "Two Runtimes" above) but the same message format.

The full wire-protocol spec (all message formats, the `M:ID` binary layout, the ~250-byte ESP-NOW payload ceiling) and the day-rollover algorithm are in `docs/ARCHITECTURE.md` §3–4. **Read `docs/ARCHITECTURE.md` §8 ("変更してはいけない箇所") before modifying any message format, the day-rollover conditions, or the GAS send paths** — several arrangements that look refactorable are deliberate, measured workarounds for MemoryError/freeze issues.

### Display Rendering (ATOM S3)

`smm3_sub_atoms3.py` uses a 4-mode display with tight memory constraints:

- **MODE_SIMPLE** (g0): Large watt display + cumulative kWh + charge
- **MODE_TODAY** (g1): 30-min resolution graph vs. previous day (6×4 time groups)
- **MODE_WEEK** (g2): 7-day bar chart at 1-hour resolution
- **MODE_MONTH** (g3): 30-day bar chart, split into 4 weeks + avg

Font positioning is pixel-exact (e.g., `WATT_RIGHT_X=109`, `CUML_KWH_RIGHT_X=46`). Layout changes require verification in `test_atoms3/test_watt_mock.py` before deploying to hardware. The measured layout constants live as named constants at the top of `smm3_sub_atoms3.py` with per-line comments — treat those comments as the layout spec.

### Modular Charge Calculation

Each file under `calc_charge/` defines its own `class CalcCharge` with one method per tariff for that power company:

- `tepco.py` — `tepco`, `tepco_smartlife_s`
- `chubu_smartlife.py` — `chubu_smartlife`, `chubu_smartlife_asa`, `chubu_smartlife_yoru`
- `calc_charge_all.py` — merged `CalcCharge` containing every tariff method above

`smm3_main_web.py` does `from calc_charge import CalcCharge` — i.e. it imports the **root-level** `calc_charge.py`, not the `calc_charge/` package. To deploy a given tariff set, copy/rename the desired file from `calc_charge/` to `calc_charge.py` at the repo root (per `README.md`). At runtime the parent picks the specific method via `getattr(calc_instance, config['CHARGE_FUNC'])`, where `CHARGE_FUNC` is a method name supplied by the Google Sheets config. To add a new power company: add a method to the relevant module (or a new module) matching the `(contract, hourly_power, day, UNIT)` signature, then reference its name in the config sheet.

## CircuitPython Constraints (ATOM S3 / `test_atoms3/` only — Verified Issues)

These will crash or silently fail—avoid them. They do **not** apply to the UIFlow MicroPython files (`smm3_main_web.py`, `smm3_sub.py`, `smm3_sub_core2.py`, `lite/*`), which run a different interpreter with different rules:

1. **F-string implicit concatenation**: Multi-line f-strings joined by adjacency do not work
   ```python
   # ❌ SyntaxError
   print(f"a {x}"
         f" b {y}")
   # ✅ Single line
   print(f"a {x} b {y}")
   ```

2. **F-string `!r` conversion**: Use `repr()` instead
   ```python
   # ❌ NameError
   f"{value!r}"
   # ✅
   f"{repr(value)}"
   ```

3. **`bytes.decode(errors=)`**: Pass as positional argument
   ```python
   # ❌ TypeError
   raw.decode("utf-8", errors="ignore")
   # ✅
   raw.decode("utf-8", "ignore")
   ```

4. **ESP-NOW `send()` argument order**: peer is second parameter
   ```python
   # ✅
   espnow_obj.send(message_bytes, peer_obj)
   ```

5. **Broadcast ESP-NOW peer**: Must be added to `peers` even for receive
   ```python
   bcast = espnow.Peer(mac=b"\xff\xff\xff\xff\xff\xff", encrypted=False)
   espnow_obj.peers.append(bcast)
   ```

## Device Deployment

### First-Time Setup (ATOM S3)

1. Flash CircuitPython 9.2.9 to device via esptool (full procedure incl. TinyUF2 bootloader step: `docs/atoms3_setup.md`)
2. Mount as `/Volumes/CIRCUITPY` (auto-mounts after flash)
3. Copy `smm3_sub_atoms3.py` → `/Volumes/CIRCUITPY/code.py`
4. Run `circup install adafruit_display_text adafruit_bitmap_font adafruit_ticks`
5. Copy required BDF files from `fonts/` → `/Volumes/CIRCUITPY/fonts/`
   - Minimum: DSEG7Classic-Bold-32.bdf, Arial-Bold-18.bdf, Arial-Bold-12.bdf
6. Create `/Volumes/CIRCUITPY/settings.toml` from `smm3_sub_atoms3.settings.toml.template` (can be empty)
7. Ctrl-D in REPL to soft-reboot and test

### Serial Console (ATOM S3)

```bash
# Device path (M5Stack ATOM S3)
/dev/cu.usbmodemCD45577CD8CF1 (115200 baud)
# Or use pyserial / screen
```

Ctrl-D in REPL triggers a soft reboot and re-executes `code.py`, useful for testing.

### Parent / Basic / Core2 (UIFlow MicroPython)

Deployed via the UIFlow firmware's own file layout — see `README.md` section 4 (ファイル構成) for the exact `/apps/` + root file list per device role, and section 5 (初期設定) for the Google Sheets setup steps.

## Testing Approach

Since this is hardware-dependent embedded code, traditional unit tests are limited. The mocks in `test_atoms3/` are CircuitPython programs (same constraints as `smm3_sub_atoms3.py`) used by copying them to the device as `code.py`:

- `test_atoms3/test_watt_mock.py` — Mock watt display with fixed value (8888)
  - Run before deploying layout changes to verify rendering
- `test_atoms3/test_display_watt_simple.py` — Full display simulation (displays recent history if available)
- `test_atoms3/test_espnow_recv.py` / `test_send_req.py` — Message sending/receiving tests
- `test_atoms3/test_font_compare.py` — Font size/spacing verification

There is no equivalent mock setup for the UIFlow MicroPython side; changes there are verified on-device.

## Configuration Sources

The parent unit reads configuration from Google Sheets (if available) or local JSON:

1. **Google Sheets API** (preferred):
   - Retrieves `api_config.json` parameters from a template sheet
   - Reads device config, charge function name, hardware parameters
   - Triggered by long-press button or at startup

2. **Local JSON** (fallback):
   - `config_main.json` (parent) / `config_sub.json` (child) — see `config_files/` for samples
   - Loaded if file exists; otherwise default constants in code apply

Add new config parameters as variables in the corresponding function, then update Google Sheets formula to return them.

## Notes on Porting & Maintenance

- **Do not add speculative features** when adapting Core2 code to ATOM S3 (or vice versa) unless explicitly requested. Constrain each variant to its immediate needs.
- **Memory is the limiting factor** on ATOM S3. Profile with `gc.mem_free()` before and after display operations; if < 10KB remains, aggressive batching is needed.
- **Font changes require verification**: Layout is pixel-exact. Test new fonts in `test_watt_mock.py` first, then measure bounding boxes on-device with `label.bounding_box`.
- **Charge calculation is pluggable**: Power-company-specific logic lives in separate modules under `calc_charge/`. Add new tariffs there without modifying the main flow, then redeploy by copying the chosen module to root `calc_charge.py`.
- **Smart meter history is cached on the parent**: Children request it once at startup. If history looks stale, press parent's B button to force a re-fetch.

## See Also

- `docs/ARCHITECTURE.md` — System-wide data flow, ECHONET Lite / ESP-NOW / GAS protocol specs, the 49-slot cumulative data model, freeze/fragmentation defenses (the "why" layer), known structural weaknesses, and the do-not-change list
- `docs/session-insights.md` — Raw design decisions extracted from past debugging sessions (freeze investigation, GAS backfill bugs)
- [Google Sheets Configuration Template](https://docs.google.com/spreadsheets/d/1qYsY8ZOpj6FxqoebCQnvBFYSL8rCK7r_A7R3m9bF7MY/edit#gid=158599453)
- `README.md` — Hardware shopping list, full UIFlow MicroPython file layout, Google Sheets setup steps, button reference, Japanese changelog
