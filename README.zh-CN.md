# GT7 Dataset Scraper

[English](README.md)

抓取 Gran Turismo 7 官方车辆目录并写入 SQLite，可选下载图片到本地。

## 快速开始

安装 [uv](https://docs.astral.sh/uv/getting-started/installation/)，从 [GitHub Releases](https://github.com/Nishikori-Yui/gt7-dataset-scraper/releases/latest) 下载对应平台的压缩包并解压：

```sh
cd GT7DB_vX.Y.Z_linux_AMD64
./scripts/bootstrap.sh
uv run --locked bin/gt7db doctor
uv run --locked bin/gt7db scrape --locale gb --limit 10 --skip-images
uv run --locked bin/gt7db query overview --db output/gt7.db
```

Windows 请先运行 `uv sync --locked`，再运行 `bin\gt7db.cmd`。

## 源码开发

使用 uv 管理 Python 环境和依赖（Python 3.10 及以上版本），缺少合适的 Python 时由 uv 自动下载。Go 为可选依赖，只用于目录解析和图片下载。

```sh
uv sync --locked
uv run --locked python -m gt7_scraper --help
```

安装 Go 1.23 及以上版本后，可用 `./scripts/bootstrap.sh --build-go` 构建可选工具，程序会自动使用；只安装 Python 也能运行。需要浏览器回退时，运行 `uv sync --locked --extra browser` 和 `uv run --locked --extra browser python -m playwright install chromium`。

详见[使用指南](docs/USAGE.zh-CN.md)、[数据库结构](docs/DB_SCHEMA.zh-CN.md)和[发布打包](docs/RELEASE_PACKAGING.zh-CN.md)。

## 法律与许可

Apache-2.0 仅适用于本仓库源码，不包含网站内容、数据、图片、商标或其他第三方材料的授权。抓取前请审查适用条款和法律，不要再分发抓取的数据或资产。详见[法律指引](docs/LEGAL_AND_PUBLISHING.zh-CN.md)。
