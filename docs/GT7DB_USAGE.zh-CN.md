# gt7db 使用指南

[English](GT7DB_USAGE.md) | [简体中文](GT7DB_USAGE.zh-CN.md)

本文说明如何使用 `gt7db` 统一入口执行抓取、构建与查询流程。

## 首选起步方式
优先使用预编译 release 包：
- https://github.com/Nishikori-Yui/gt7-dataset-scraper/releases/latest
- 选择 `GT7DB_*_LITE_<OS>_<ARCH>`

下载后先执行：
```bash
./GT7DB_vX.Y.Z_LITE_linux_AMD64/bin/gt7db doctor --json
```

## 命令面
`gt7db` 支持以下命令：
- `scrape`：执行 `python -m gt7_scraper`
- `build-dbs`：执行 `python scripts/build_dbs.py`
- `query`：执行 `python -m gt7_query`
- `doctor`：输出运行时布局与默认后端策略

## 发布包模式与源码模式
在发布包模式（release 解压目录）下，`gt7db` 会在参数缺失时注入默认值：
- `scrape`：`--engine hybrid --catalog-engine go --spec-engine rust --backend-fallback off`
- `build-dbs`：`--engine hybrid --catalog-engine go --spec-engine rust --merge-engine go --hero-check-engine rust --backend-fallback off`
- `query`：`--query-engine go --query-fallback off`

在源码模式（仓库本地 checkout）下，不会注入上述发布包默认参数。

如果你显式传入参数（例如 `--query-engine python`），会优先使用你传入的值。

## 常见工作流
### 1) 健康检查
```bash
./bin/gt7db doctor --json
```

### 2) 抓取单语言
```bash
./bin/gt7db scrape \
  --locale gb \
  --base-locale gb \
  --db ./output/gt7.gb.db \
  --images ./output/images \
  --skip-images
```

### 3) 构建多语言库与汇总库
```bash
./bin/gt7db build-dbs \
  --locales cn,jp,gb,us \
  --base-locale gb \
  --out-dir ./output/release-run \
  --combined-mode merge \
  --skip-images \
  --car-list scripts/example_car_ids_10.txt
```

### 4) 查询
```bash
./bin/gt7db query overview --db ./output/release-run/gt7.db
./bin/gt7db query list --db ./output/release-run/gt7.db --locale gb --limit 10
```

更完整的查询参数与输出格式见 `QUERY_CLI.zh-CN.md`。

## 环境变量
- `GT7DB_ROOT`：强制指定运行时根目录。
- `GT7DB_PYTHON`：强制指定 launcher 使用的 Python 可执行路径。

`GT7DB_NATIVE_DIR` 会在发布包模式下由 launcher 自动注入给子进程。

## 故障排查
- `error: no Python runtime found`：
  - 发布包模式检查 `runtime/python/`
  - 源码模式检查 `.venv` 或系统 `python3/python`
- 原生二进制缺失：
  - 执行 `gt7db doctor --json`
  - 检查 `runtime/native/` 是否包含必需二进制
- 无回退直接失败：
  - 发布包默认 `fallback=off`
  - 仅在你明确需要回退行为时，显式传入对应 fallback 参数

## 相关文档
- 发布打包体系：`RELEASE_PACKAGING.zh-CN.md`
- 数据集生成：`DATASET_GENERATION.zh-CN.md`
- 查询 CLI 细节：`QUERY_CLI.zh-CN.md`
- 混合后端说明：`HYBRID_ENGINE.zh-CN.md`
