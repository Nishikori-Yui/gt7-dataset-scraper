# GT7 Dataset Scraper

[English](../README.md) | [简体中文](README.zh-CN.md)

用于抓取 Gran Turismo 7 官方车辆列表并存储到 SQLite，支持本地图片。

## 快速开始
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

```bash
python -m gt7_scraper --locale gb --db ./output/gt7.db --images ./output/images
```

## 文档
- 数据集生成：`DATASET_GENERATION.zh-CN.md`
- 架构与数据流：`ARCHITECTURE.zh-CN.md`
- 查询 CLI/API：`QUERY_CLI.zh-CN.md`
- 数据库结构：`DB_SCHEMA.zh-CN.md`
- 法律与发布：`LEGAL_AND_PUBLISHING.zh-CN.md`
- 贡献指南：`CONTRIBUTING.zh-CN.md`

## 输出
- SQLite 数据库：`output/gt7.db`
- 图片（可选）：`output/images/`

## 许可协议
Apache-2.0，详见 `LICENSE`。

## 法律提示（简要）
本项目仅用于学习与研究。使用者需自行遵守网站条款与适用法律。本仓库不包含任何
抓取的数据或资产。所有商标与版权归原权利人所有。

详见 `LEGAL_AND_PUBLISHING.zh-CN.md`。
