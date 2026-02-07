# Mode Matrix (Validated Smoke Runs)

This page summarizes reproducible smoke-test results for supported run modes.

## Test Setup
- Date: 2026-02-07
- Dataset: `scripts/example_car_ids_10.txt` (10 cars)
- Locale: `gb` for single-run tests; `cn,jp,gb,us` for build tests
- Environment assumptions:
  - `.venv` activated or commands use `./.venv/bin/python`
  - `./local/bin` contains hybrid binaries when using `--engine hybrid`

## `gt7_scraper` Modes

Command base:
```bash
./.venv/bin/python -m gt7_scraper \
  --locale gb \
  --base-locale gb \
  --car-list scripts/example_car_ids_10.txt \
  --workers 1 \
  --rate 0 \
  --timeout 30
```

| Case | Extra Args | Exit | hero_total | intro_missing | detail_missing | manifest_mismatch | Notes |
|---|---|---:|---:|---:|---:|---:|---|
| `py_no_pw` | `--engine python` | 0 | 41 | 0 | 0 | 0 | Stable baseline |
| `py_pw_python` | `--engine python --use-playwright --playwright-engine python --playwright-workers 1` | 0 | 41 | 0 | 0 | 0 | Slower than no-playwright |
| `hybrid_no_pw_rust` | `--engine hybrid --engines-dir ./local/bin --spec-engine rust --playwright-engine node` | 0 | 41 | 0 | 0 | 0 | Recommended default |
| `hybrid_no_pw_python_spec` | `--engine hybrid --engines-dir ./local/bin --spec-engine python --playwright-engine node` | 0 | 41 | 0 | 0 | 0 | Similar quality; spec path differs |
| `hybrid_pw_node` | `--engine hybrid --engines-dir ./local/bin --spec-engine rust --use-playwright --playwright-engine node --playwright-workers 1` | 0 | 41 | 0 | 0 | 0 | Slowest; quality remains aligned |

Duration comparison (same 10-car run, seconds):

| Case | duration_sec | Relative to `hybrid_no_pw_rust` |
|---|---:|---:|
| `hybrid_no_pw_rust` | 81.417 | 1.00x |
| `hybrid_no_pw_python_spec` | 87.830 | 1.08x |
| `py_no_pw` | 150.456 | 1.85x |
| `py_pw_python` | 217.399 | 2.67x |
| `hybrid_pw_node` | 467.462 | 5.74x |

## `build_dbs.py` Modes

Command base:
```bash
./.venv/bin/python scripts/build_dbs.py \
  --locales cn,jp,gb,us \
  --base-locale gb \
  --car-list scripts/example_car_ids_10.txt \
  --workers 1 \
  --rate 0 \
  --timeout 30 \
  --playwright-policy off \
  --image-policy none \
  --text-policy target-only \
  --hero-check off
```

| Case | Extra Args | Exit | duration_sec | locales_count | detail_missing | Result |
|---|---|---:|---:|---:|---:|---|
| `build_dbs_python_rescrape` | `--engine python --combined-mode rescrape` | 0 | 128.374 | 4 | 0 | Generated 4 locale DBs and combined `gt7.db` |
| `build_dbs_hybrid_rescrape` | `--engine hybrid --engines-dir ./local/bin --spec-engine rust --combined-mode rescrape` | 0 | 152.922 | 4 | 0 | Generated 4 locale DBs and combined `gt7.db` |
| `build_dbs_hybrid_merge_python` | `--engine hybrid --engines-dir ./local/bin --spec-engine rust --combined-mode merge --merge-engine python` | 0 | 57.476 | 4 | 0 | Generated per-locale DBs and merged `gt7.db` via SQL backend |
| `build_dbs_hybrid_merge_cpp` | `--engine hybrid --engines-dir ./local/bin --spec-engine rust --combined-mode merge --merge-engine cpp` | 0 | 57.973 | 4 | 0 | Generated per-locale DBs and merged `gt7.db` via C++ backend |
| `build_dbs_hybrid_merge_go` | `--engine hybrid --engines-dir ./local/bin --spec-engine rust --combined-mode merge --merge-engine go` | 0 | 28.770* | 2 | 0 | Generated per-locale DBs and merged `gt7.db` via Go backend (`gb,us`, no images) |

\* `build_dbs_hybrid_merge_go` was measured in a backend-comparison run with `gb,us` + 10-car list + `--image-policy none`, so duration is not directly comparable to the 4-locale rows above.

### Backend/Fallback Smoke (2026-02-07, `gb,us`, 10 cars, no images)

| Case | Exit | duration_sec | Key result |
|---|---:|---:|---|
| `merge_engine_python` | 0 | 28.14 | `cars/car_texts/car_specs/fetch_log = 10/20/180/20` |
| `merge_engine_cpp` | 0 | 28.00 | Same DB counts as python merge |
| `merge_engine_go` | 0 | 28.77 | Same DB counts as python merge |
| `merge_engine_go_missing_bin` | 0 | 18.51 | Warning emitted, auto-fallback to python merge |
| `hero_check_rust_missing_bin` | 0 | 15.87 | Warning emitted, auto-fallback to python hero-check |
| `query_engine_go` | 0 | 0.04 | `list/stats/overview` parity-validated |
| `query_engine_go_missing_bin` | 0 | 0.03 | Warning emitted, auto-fallback to python query |
| `gt7db build-dbs` | 0 | 12.04 | Dotnet launcher passthrough verified |
| `gt7db query overview` | 0 | 0.32 | Dotnet launcher passthrough verified |

## Recommended Defaults
- Single locale scrape: `hybrid_no_pw_rust`
- Multi-locale build: `scripts/build_dbs.py --engine hybrid --playwright-policy off`
- Use Playwright only when you explicitly need browser fallback behavior.
- Build merge backend default is now `go` (`--merge-engine`), and hero-check backend default is `rust` (`--hero-check-engine`).
- Query CLI default backend is now `auto`: Go for `list(manufacturer|country|drivetrain)`, `stats`, `overview`; Python for `car` and `list --sort max_power|weight`.

## Re-run Commands

Single locale, recommended:
```bash
./.venv/bin/python -m gt7_scraper \
  --engine hybrid \
  --locale gb \
  --base-locale gb \
  --db ./output/gt7.gb.db \
  --images ./output/images \
  --car-list scripts/example_car_ids_10.txt \
  --workers 1 \
  --rate 0 \
  --timeout 30 \
  --engines-dir ./local/bin \
  --spec-engine rust
```

Multi-locale build, recommended:
```bash
./.venv/bin/python scripts/build_dbs.py \
  --engine hybrid \
  --locales cn,jp,gb,us \
  --base-locale gb \
  --out-dir ./output \
  --images ./output/images \
  --car-list scripts/example_car_ids_10.txt \
  --image-policy all-locales \
  --text-policy target-only \
  --playwright-policy off \
  --hero-check soft \
  --hero-soft-max-ratio 0.05 \
  --hero-soft-max-count 20 \
  --hero-manifest ./gt7_scraper/mappings/hero_expected_counts.json \
  --engines-dir ./local/bin
```

## Notes
- Durations vary by network and target site behavior.
