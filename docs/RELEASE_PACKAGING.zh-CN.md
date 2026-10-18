# 发布包

[English](RELEASE_PACKAGING.md)

从 [GitHub Releases](https://github.com/Nishikori-Yui/gt7-dataset-scraper/releases/latest) 下载发布包。压缩包包含源码、指南、`pyproject.toml`、`uv.lock`，以及适配目标平台的两个 Go 工具。请先安装 [uv](https://docs.astral.sh/uv/getting-started/installation/)，再进入解压目录运行 `uv sync --locked`，各平台命令相同。

macOS/Linux 和 Windows 均使用 `uv run --locked bin/gt7db`。入口使用包内项目配置和 `.venv`，提供 `scrape`、`build-dbs`、`query` 和 `doctor`。源码与发布包均自动检测 `local/bin` 中的可选工具，不可用时由 Python 完成相同任务；数据库合并、校验和查询使用 Python 与 SQLite。uv 按需安装 Python 和依赖，浏览器需单独安装。

支持 macOS arm64/amd64、Linux arm64/amd64 和 Windows arm64/amd64。压缩包名称格式为 `GT7DB_<version>_<os>_<ARCH>`。

## 本地构建

使用 uv 和 Go 1.23 及以上版本。Go 会为所选平台交叉编译，请在目标平台验证生成的包：

```sh
uv run --locked python scripts/release/build_release.py \
  --platform darwin-arm64 \
  --version vX.Y.Z \
  --out-dir ./dist/release
```

添加 `--skip-build` 可复用 `local/bin` 中已有的 Go 二进制。发布包目录与压缩包会生成在 `dist/release` 下。

在目标平台执行烟测：

```sh
uv run --locked python scripts/release/smoke_release.py \
  --package-dir ./dist/release/GT7DB_vX.Y.Z_macOS_ARM64
```

烟测使用 `uv.lock` 锁定的依赖，会验证文件校验和、启动路径、命令入口和 SQLite 查询。推送 `v*` tag 时，GitHub Actions 会构建六个平台的发布包并上传；也可以在 Actions 页面手动传入版本 tag 运行。
