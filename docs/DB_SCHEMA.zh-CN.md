# 数据库结构

[English](DB_SCHEMA.md)

SQLite 表结构定义在 `gt7_scraper/db/schema.py`。车辆和厂商各保存一条基准记录；本地化文本和规格按语言单独存储。`--base-locale` 决定写入基准字段的语言。

| 表 | 内容 |
| --- | --- |
| `cars`、`manufacturers` | 基准记录与原始解析数据 |
| `car_texts`、`manufacturer_i18n` | 多语言名称和描述 |
| `car_specs`、`spec_code_i18n` | 多语言规格值与规范化标签 |
| `aspiration_codes`、`aspiration_i18n` | 进气形式代码与标签 |
| `drivetrain_codes`、`drivetrain_i18n` | 传动形式代码与标签 |
| `country_iso_map`、`country_i18n` | GT7 国家 ID、ISO3 代码和多语言名称 |
| `car_images` | 可选的本地图片路径；启用图片下载时创建 |
| `fetch_log`、`meta` | 抓取历史和数据集元信息 |

读取本地化文本时优先使用 `car_texts`。规格按 `car_id` 与 `locale` 查询，使用 `sort_order` 保持页面顺序。`cars.raw_json` 保存解析得到的原始数据。

查询本地化名称和规格的示例：

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
