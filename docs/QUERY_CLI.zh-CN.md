# 数据库查询 CLI 与 API

[English](QUERY_CLI.md) | [简体中文](QUERY_CLI.zh-CN.md)

本文说明 `gt7_query` 的使用方式。默认假设数据库由 `gt7_scraper` 生成（见 `DATASET_GENERATION.zh-CN.md`）。

## CLI
后端选项（全局）：
- `--query-engine python|go`（默认：`python`）
- `--query-go-bin ./local/bin/gt7-query-go`
- 若 Go 后端缺失或执行失败，CLI 会给出 warning 并自动回退到 Python 后端。
- 当前已验证的 Go 范围：`list`（不含 `max_power`/`weight`）、`stats`、`overview`。
- `car` 与 `list --sort max_power|weight` 当前会有意回退到 Python 后端。

### 列表（仅 id + name）
```bash
python -m gt7_query list --db output/gt7.db --locale gb --sort manufacturer --limit 5
```

排序选项：
- `manufacturer`
- `country`
- `drivetrain`
- `max_power`（使用 gb 的 spec 值，不做单位换算）
- `weight`（使用 gb 的 spec 值，不做单位换算）

说明：
- `--locale` 控制输出的本地化内容（`car_texts`、`manufacturer_i18n`、i18n 标签）在存在时优先使用。
- `max_power` 与 `weight` 的排序始终使用 `gb` 的 `car_specs` 值以保持可比性。
- `country` 排序优先使用国家映射表；若映射表缺失，则回退到 `cars.raw_json` + 映射 JSON。

输出格式：
- `--format json`（默认）
- `--format text`
- `--out path/to/output.json`

示例（文本输出）：
```bash
python -m gt7_query list --db output/gt7.db --locale cn --sort country --limit 20 --format text
```

### 单车详情
```bash
python -m gt7_query car --db output/gt7.db --locale cn --car-id car31 --format json
```

输出字段：
- `id`, `name`
- `manufacturer`（优先本地化名称）
- `country`（`country_id`, `iso3`, 本地化名称）
- `drivetrain`（code + label）
- `aspiration`（code + label）
- `intro`, `detail`
- `specs`（按 `sort_order` 排序）
- `images`（若存在 hero/thumbnail）

说明：
- 若存在 `car_texts` 的本地化行，会优先使用其中的 `name/intro/detail`，否则使用 `cars` 的基准值。
- `specs` 从指定 locale 的 `car_specs` 读取，并通过 `spec_code_i18n` 联结标签。

### 统计
```bash
python -m gt7_query stats --db output/gt7.db --locale gb --by country
```

统计维度：
- `manufacturer`
- `country`
- `drivetrain`

### 概览
```bash
python -m gt7_query overview --db output/gt7.db
```

Go 后端示例：
```bash
python -m gt7_query --query-engine go --query-go-bin ./local/bin/gt7-query-go list --db output/gt7.db --locale gb --sort manufacturer --limit 5
```

## Python API

```python
from pathlib import Path
from gt7_query.queries import list_cars, get_car_details, stats_by_country

db = Path("output/gt7.db")

cars = list_cars(db, locale="gb", sort_by="manufacturer", limit=10)
car = get_car_details(db, "car31", locale="cn")
stats = stats_by_country(db, locale="gb")
```

## 排序说明
- `max_power` 与 `weight` 使用 gb 语言的 `car_specs` 值，不做单位换算。
- 若国家相关表缺失，`list --sort country` 会回退到 `raw_json` + 映射文件。

## JSON 输出示例（car）
```json
{
  "id": "car31",
  "name": "...",
  "manufacturer": {"id": "...", "name": "..."},
  "country": {"country_id": "carctry5", "iso3": "DEU", "name": "Germany"},
  "drivetrain": {"code": "FR", "label": "FR"},
  "aspiration": {"code": "TC", "label": "Turbocharger"},
  "intro": "...",
  "detail": "...",
  "specs": [{"spec_key": "max_power", "spec_label": "Max Power", "spec_value": "203", "spec_unit": "HP", "spec_raw": "203 HP", "sort_order": 3}],
  "images": [{"image_type": "hero", "image_path": "...", "sort_order": 1}]
}
```

## 常见场景
- 按马力排序生成列表做快速比较。
- 导出单车 JSON 供下游处理。
- 按厂商或国家统计做质量检查。
