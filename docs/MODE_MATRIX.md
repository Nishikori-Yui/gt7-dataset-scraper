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

| Case | Extra Args | Exit | hero_total | detail_missing | Notes |
|---|---|---:|---:|---:|---|
| `py_no_pw` | `--engine python` | 0 | 41 | 0 | Stable baseline |
| `py_pw_python` | `--engine python --use-playwright --playwright-engine python --playwright-workers 1` | 0 | 41 | 0 | Slower than no-playwright |
| `hybrid_no_pw_rust` | `--engine hybrid --engines-dir ./local/bin --spec-engine rust --playwright-engine node` | 0 | 41 | 0 | Recommended default |
| `hybrid_no_pw_python_spec` | `--engine hybrid --engines-dir ./local/bin --spec-engine python --playwright-engine node` | 0 | 41 | 0 | Similar quality; spec path differs |
| `hybrid_pw_node` | `--engine hybrid --engines-dir ./local/bin --spec-engine rust --use-playwright --playwright-engine node --playwright-workers 1` | 0 | 41 | 0 | Slowest; now quality-correct after fallback fix |

Duration comparison (same 10-car run, seconds):

| Case | duration_sec | Relative to `hybrid_no_pw_rust` |
|---|---:|---:|
| `hybrid_no_pw_rust` | 72 | 1.00x |
| `hybrid_no_pw_python_spec` | 74 | 1.03x |
| `py_no_pw` | 78 | 1.08x |
| `py_pw_python` | 138 | 1.92x |
| `hybrid_pw_node` | 296 | 4.11x |

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

| Case | Extra Args | Exit | duration_sec | Result |
|---|---|---:|---:|---|
| `build_dbs_python` | `--engine python` | 0 | 109 | Generated `gt7.<locale>.db` for `cn/jp/gb/us` and combined `gt7.db` |
| `build_dbs_hybrid` | `--engine hybrid --engines-dir ./local/bin --spec-engine rust` | 0 | 106 | Generated `gt7.<locale>.db` for `cn/jp/gb/us` and combined `gt7.db` |

## Recommended Defaults
- Single locale scrape: `hybrid_no_pw_rust`
- Multi-locale build: `scripts/build_dbs.py --engine hybrid --playwright-policy off`
- Use Playwright only when you explicitly need browser fallback behavior.

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
