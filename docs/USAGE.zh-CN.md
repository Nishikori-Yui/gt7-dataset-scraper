# 使用指南

[English](USAGE.md)

## 环境

安装 [uv](https://docs.astral.sh/uv/getting-started/installation/)，在项目目录运行：

```sh
uv sync --locked
```

Go 为可选依赖。运行 `./scripts/bootstrap.sh --build-go` 构建目录解析器和图片下载器，程序会自动检测使用；工具不可用时由 Python 完成相同任务。只有需要浏览器回退时才安装 Playwright 和 Chromium。

Windows 使用相同的 uv 命令。uv 管理 `.venv`，使用 Python 3.10 及以上版本。以下命令通过 `uv run` 执行，无需手动激活；也可在 macOS/Linux 运行 `source .venv/bin/activate`，或在 Windows cmd 运行 `.venv\Scripts\activate`。

## 抓取单个语言

```sh
uv run --locked python -m gt7_scraper \
  --locale gb \
  --limit 10 \
  --car-list scripts/example_car_ids_10.txt \
  --skip-images
```

默认数据库为 `output/gt7.db`。移除 `--limit` 和 `--car-list` 可抓取完整目录。`--resume` 会跳过已成功记录的车辆。默认图片存放在 `output/images/`，使用 `--skip-images` 可跳过下载。

## 构建多个语言版本

```sh
uv run --locked python scripts/build_dbs.py --resume
```

该命令抓取全部 21 种语言，共享图片仅在基准语言阶段下载一套，最终将各语言库合并为 `gt7.db`。`--resume` 保留已有语言库，并跳过已成功记录的车辆。可用 `--locales gb,us,cn` 或 `--limit 10` 做小规模测试。

使用 `--no-combined` 可只保留语言库，使用 `--no-per-locale` 可合并已有语言库。Hero 图片校验默认是 `strict`；不下载图片时请使用 `--image-policy none --hero-check off`。

## 查询数据库

```sh
uv run --locked python -m gt7_query overview --db output/gt7.db
uv run --locked python -m gt7_query list --db output/gt7.db --locale gb --limit 10
uv run --locked python -m gt7_query car --db output/gt7.db --locale cn --car-id car31
uv run --locked python -m gt7_query stats --db output/gt7.db --by country
```

查询统一使用 Python 和 SQLite。发布包也提供相同命令，例如 `bin/gt7db query overview --db output/gt7.db`。

## 浏览器回退

当静态页面数据不足时再安装 Playwright：

```sh
uv sync --locked --extra browser
uv run --locked --extra browser python -m playwright install chromium
uv run --locked python -m gt7_scraper --locale gb --use-playwright
```

运行 `uv run --locked python scripts/gt7db.py doctor --json` 可检查源码环境或发布包。
