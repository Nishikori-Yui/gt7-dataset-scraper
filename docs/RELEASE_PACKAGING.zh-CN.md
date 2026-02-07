# 发布打包体系（gt7db）

[English](RELEASE_PACKAGING.md) | [简体中文](RELEASE_PACKAGING.zh-CN.md)

本文定义 GT7-Dataset 在生产使用场景下的发布与消费方式。

## 首选使用路径
优先使用 GitHub Release 的预编译包。

- 下载地址：https://github.com/Nishikori-Yui/gt7-dataset-scraper/releases/latest
- 按平台选择 `GT7DB_*_LITE_<OS>_<ARCH>`。
- 解压后直接运行 `bin/gt7db`（Windows 为 `bin/gt7db.exe`）。

本地手动构建仅用于开发、调试或需要定制打包的场景。
命令级使用方式详见 `GT7DB_USAGE.zh-CN.md`。

## 发布目标
- 以 `gt7db`（.NET launcher）作为统一入口。
- 常见流程无需本地安装 Go/Rust/Node/Python 工具链。
- 打包运行时采用 native-first 默认策略，并保持确定性的回退策略（`fallback=off`）。
- 默认发布物排除已被原生实现替代的 Python 后端模块。

## 包类型
- `lite`（默认发布物）：
  - `gt7db` launcher
  - 内置 Python runtime + 最小 worker/编排模块
  - 必需 native binaries
  - 不包含 Playwright 浏览器运行时
- `full`（可选，本地手动构建）：
  - 在 `lite` 基础上增加 Node runtime + Playwright worker + 浏览器依赖
  - 主要用于明确需要浏览器回退的调试环境

## 平台矩阵
- `darwin-arm64`
- `darwin-amd64`
- `linux-amd64`
- `linux-arm64`
- `win-amd64`
- `win-arm64`

## 产物命名规则
发布目录与压缩包命名：
- `GT7DB_<version>_<FLAVOR>_<os>_<ARCH>`

示例：
- `GT7DB_v1.2.3_LITE_macOS_ARM64`
- `GT7DB_v1.2.3_LITE_windows_AMD64.zip`
- `GT7DB_v1.2.3_LITE_linux_ARM64.tar.gz`

## 包结构
```text
<package-root>/
  bin/
    gt7db            # Windows 为 gt7db.exe
  runtime/
    python/
      ...            # 内置 Python runtime
      worker/
        gt7_scraper/
        gt7_query/
        scripts/build_dbs.py
    native/
      gt7-catalog-go
      gt7-downloader
      gt7-spec-normalizer
      gt7-db-merge-go
      gt7-hero-check
      gt7-query-go
      ...
  manifest.json
  SHA256SUMS
```

## 发布包默认后端策略
打包后的 `gt7db` 在未显式传参时会注入：
- `scrape`：`--engine hybrid --catalog-engine go --spec-engine rust --backend-fallback off`
- `build-dbs`：`--engine hybrid --catalog-engine go --spec-engine rust --merge-engine go --hero-check-engine rust --backend-fallback off`
- `query`：`--query-engine go --query-fallback off`（go-first）

并自动注入 `runtime/native` 的二进制路径。

## Python 模块排除策略
默认发布物会排除可替代的 Python 后端模块，包括：
- `gt7_query/backends/python_backend.py`
- 旧入口兼容 shim（`gt7_query/cli.py`、`gt7_query/queries.py`、`gt7_scraper/cli.py`、`gt7_scraper/scraper.py`）
- `gt7_scraper/engine/*` 下 legacy engine bridge shim（catalog/downloader/playwright/spec）

如需诊断可使用 `--include-full-python-backends` 生成包含完整 Python 后端的手动包。

## 下载包后的快速运行
```bash
./GT7DB_vX.Y.Z_LITE_linux_AMD64/bin/gt7db doctor --json
./GT7DB_vX.Y.Z_LITE_linux_AMD64/bin/gt7db scrape --locale gb --db ./output/gt7.db --images ./output/images --skip-images
./GT7DB_vX.Y.Z_LITE_linux_AMD64/bin/gt7db query overview --db ./output/gt7.db
```

## 本地手动打包（可选）
前置依赖：
- Python 3.13+
- Go
- Rust/Cargo
- .NET 8 SDK
- Node 20+（仅 `full` 需要）

### Lite（手动路径首选）
```bash
python scripts/release/build_release.py \
  --flavor lite \
  --platform darwin-arm64 \
  --version vX.Y.Z \
  --out-dir ./dist/release
```

### Full（可选，调试用途）
```bash
python scripts/release/build_release.py \
  --flavor full \
  --platform darwin-arm64 \
  --version vX.Y.Z \
  --out-dir ./dist/release
```

### 手动矩阵构建（lite 优先）
```bash
TAG=vX.Y.Z
for PLATFORM in darwin-arm64 darwin-amd64 linux-amd64 linux-arm64 win-amd64 win-arm64; do
  python scripts/release/build_release.py \
    --flavor lite \
    --platform "${PLATFORM}" \
    --version "${TAG}" \
    --out-dir ./dist/release
done
```

### 烟测
```bash
python scripts/release/smoke_release.py \
  --package-dir ./dist/release/GT7DB_vX.Y.Z_LITE_macOS_ARM64
```

## CI/CD 发布流程
Workflow：`.github/workflows/release-packages.yml`

触发方式：
- 推送 tag：`v*`
- 手动触发：传入 `tag`

默认发布流水线：
1. 按平台矩阵构建（lite-only）发布包。
2. 对每个产物执行 smoke，校验默认后端与 `query-fallback=off`。
3. 上传构建产物。
4. 创建/更新 GitHub Release，上传产物与校验文件。

## 故障排查
- 原生后端缺失：
  - 执行 `bin/gt7db doctor --json`。
  - 检查 `runtime/native` 与 `manifest.json`。
- Worker 启动失败：
  - 检查 `runtime/python` 是否存在。
  - 检查 `runtime/python/worker` 是否包含 `gt7_scraper`、`gt7_query`、`scripts/build_dbs.py`。
- 平台不匹配：
  - 核对包名后缀与目标机器架构。
  - 手动打包时改用正确 `--platform`。
- 需要浏览器回退：
  - 使用手动 `full` 包构建。
