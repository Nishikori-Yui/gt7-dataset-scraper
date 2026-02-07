# GT7 Dataset Scraper

[English](../README.md) | [简体中文](README.zh-CN.md)

用于抓取 Gran Turismo 7 官方车辆列表并存储到 SQLite，支持本地图片。

## 重要法律风险提示
- 本仓库许可证仅覆盖本项目源码，不授予任何第三方站点内容、图片资产、商标或品牌素材的使用权。
- 运行抓取前请先审查目标网站条款与适用法律；若条款不允许该用途，请勿在未获授权情况下执行。
- 不要发布或再分发抓取得到的数据集、图片、Logo 或原始 payload。

## 快速开始
```bash
./scripts/bootstrap_python_env.sh
```

```bash
source .venv/bin/activate
python -m gt7_scraper --engine python --locale gb --db ./output/gt7.db --images ./output/images --skip-images
```

可选统一入口（构建后可用）：
```bash
./local/bin/gt7db scrape --engine hybrid --locale gb --db ./output/gt7.db --images ./output/images --skip-images
```

## 依赖安装（纯 Python）
一键初始化（推荐）：
```bash
./scripts/bootstrap_python_env.sh
```

纯 Python 模式下可选 Playwright：
```bash
./scripts/bootstrap_python_env.sh --with-playwright-browser
```

常用参数：
- `--with-playwright`：仅安装 Playwright Python 包
- `--with-playwright-browser`：安装 Playwright 包并下载 Chromium
- `--python-bin PATH`：指定 Python 可执行文件

## 依赖安装（Hybrid）
一键初始化（推荐）：
```bash
./scripts/bootstrap_hybrid_env.sh
```

常用参数：
- `--no-system-install`：仅创建 `.venv` 并构建本地引擎
- `--skip-playwright-browser`：跳过 Playwright Chromium 下载
- `--skip-build`：只安装/检查工具链与 Python 依赖
- `--skip-dotnet-build`：跳过可选的 `gt7db` dotnet launcher 构建

手动安装步骤详见 [HYBRID_ENGINE.zh-CN.md](HYBRID_ENGINE.zh-CN.md)。纯 Python 使用说明见 [DATASET_GENERATION.zh-CN.md](DATASET_GENERATION.zh-CN.md)。

## 可选打包（`gt7db` Lite/Full）
用于生成可分发打包产物：
```bash
./scripts/package_gt7db.sh --flavor lite
./scripts/package_gt7db.sh --flavor full
```

常用参数：
- `--runtime <rid>`：手动指定 dotnet runtime id（如 `osx-arm64`、`linux-x64`）
- `--skip-build`：仅打包当前本地产物
- `--dist-dir <path>`：自定义输出目录

## 推荐模式
- 默认建议使用 `--engine hybrid`。
- 已验证的 smoke 结果中，在同一组 10 车样本上，`hybrid_no_pw_rust` 比纯 Python 更快（`81.417s` vs `150.456s`），且数据质量基线一致。
- 仅在明确需要浏览器回退时再开启 Playwright，因为其耗时明显更高。
- `--engine python` 仍保留为最小依赖的回退方案。
- 性能对比见 [MODE_MATRIX.zh-CN.md](MODE_MATRIX.zh-CN.md)，依赖环境与构建步骤见 [HYBRID_ENGINE.zh-CN.md](HYBRID_ENGINE.zh-CN.md)。
- 本仓库同时用于学习/实验：虽然纯 Python 可以实现主要功能，但会在适合的位置刻意采用 Go/Rust/Node/C++/SQL（选型说明见 [ARCHITECTURE.zh-CN.md](ARCHITECTURE.zh-CN.md)）。

## 文档
- 数据集生成：[DATASET_GENERATION.zh-CN.md](DATASET_GENERATION.zh-CN.md)
- 架构与数据流：[ARCHITECTURE.zh-CN.md](ARCHITECTURE.zh-CN.md)
- 混合引擎指南：[HYBRID_ENGINE.zh-CN.md](HYBRID_ENGINE.zh-CN.md)
- 模式矩阵（实测）：[MODE_MATRIX.zh-CN.md](MODE_MATRIX.zh-CN.md)
- 查询 CLI/API：[QUERY_CLI.zh-CN.md](QUERY_CLI.zh-CN.md)
- 数据库结构：[DB_SCHEMA.zh-CN.md](DB_SCHEMA.zh-CN.md)
- 法律与发布：[LEGAL_AND_PUBLISHING.zh-CN.md](LEGAL_AND_PUBLISHING.zh-CN.md)
- 贡献指南：[CONTRIBUTING.zh-CN.md](CONTRIBUTING.zh-CN.md)

`scripts/build_dbs.py` 的 Hero 校验模式（`off|soft|strict`）见 [HYBRID_ENGINE.zh-CN.md](HYBRID_ENGINE.zh-CN.md)。

## 输出
- SQLite 数据库：`output/gt7.db`
- 图片（可选）：`output/images/`

## 许可协议
Apache-2.0，详见 `LICENSE`。

## 法律提示（简要）
本项目仅用于学习与研究。使用者需自行遵守网站条款与适用法律。本仓库不包含任何
抓取的数据或资产。所有商标与版权归原权利人所有。

详见 [LEGAL_AND_PUBLISHING.zh-CN.md](LEGAL_AND_PUBLISHING.zh-CN.md)。
