# Database schema

[简体中文](DB_SCHEMA.zh-CN.md)

The SQLite schema is initialized in `gt7_scraper/db/schema.py`. Each car and manufacturer has one canonical row; localized text and specifications are stored separately by locale. `--base-locale` selects which locale populates canonical fields.

| Table | Contents |
| --- | --- |
| `cars`, `manufacturers` | Canonical records and source payloads |
| `car_texts`, `manufacturer_i18n` | Localized names and descriptions |
| `car_specs`, `spec_code_i18n` | Localized values and normalized labels |
| `aspiration_codes`, `aspiration_i18n` | Aspiration codes and labels |
| `drivetrain_codes`, `drivetrain_i18n` | Drivetrain codes and labels |
| `country_iso_map`, `country_i18n` | GT7 country IDs, ISO3 codes, and localized names |
| `car_images` | Optional local image paths; created when image downloading is enabled |
| `fetch_log`, `meta` | Fetch history and dataset metadata |

Localized reads should prefer `car_texts` over canonical text. Specifications are keyed by `car_id` and `locale`; use `sort_order` to preserve display order. `cars.raw_json` retains the parsed source data.

Example: read a localized car name and its specifications:

```sql
SELECT c.id, COALESCE(t.name, c.name) AS name
FROM cars AS c
LEFT JOIN car_texts AS t ON t.car_id = c.id AND t.locale = 'cn'
WHERE c.id = 'car31';

SELECT spec_key, spec_value, spec_unit, spec_raw
FROM car_specs
WHERE car_id = 'car31' AND locale = 'cn'
ORDER BY sort_order;
```
