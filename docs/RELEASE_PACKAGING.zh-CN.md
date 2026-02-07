# 发布打包体系（gt7db）

[English](RELEASE_PACKAGING.md) | [简体中文](RELEASE_PACKAGING.zh-CN.md)

本文定义 GT7-Dataset 的可直接使用发布体系。

## 目标
- 以 `gt7db`（.NET launcher）作为统一入口。
- 常见流程下，用户无需本地安装 Go/Rust/Node/Python。
- 发布包默认非 Python 后端，并默认 `fallback=off`。
- 默认发布物不包含可被原生后端替代的 Python 模块。

## 发布包类型
- `lite`：
  - `gt7db` launcher
  - 内置 Python runtime + 最小 worker 模块
  - 必需 native binaries
  - 不含 Playwright 浏览器运行时
- `full`：
  - `lite` 全部内容
  - 额外包含 Node runtime + Playwright worker + Chromium 浏览器依赖

## 平台矩阵
- `darwin-arm64`
- `darwin-x64`
- `linux-x64`
- `linux-arm64`
- `win-x64`
- `win-arm64`

## 产物命名规则
发布目录与压缩包统一命名为：
- `GT7DB_<version>_<FLAVOR>_<os>_<ARCH>`

示例：
- `GT7DB_v1.2.3_LITE_macOS_ARM64`
- `GT7DB_v1.2.3_FULL_windows_AMD64.zip`
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

## 默认后端策略（发布包）
打包后的 `gt7db` 在未显式传参时会注入：
- `scrape`：`--engine hybrid --catalog-engine go --spec-engine rust --backend-fallback off`
- `build-dbs`：`--engine hybrid --catalog-engine go --spec-engine rust --merge-engine go --hero-check-engine rust --backend-fallback off`
- `query`：`--query-engine go --query-fallback off`（go-first）

同时会自动注入 `runtime/native` 的二进制路径。

## Python 模块排除策略
默认发布包会排除可替代模块，包括：
- `gt7_query/backends/python_backend.py`
- 兼容旧入口 shim（`gt7_query/cli.py`、`gt7_query/queries.py`、`gt7_scraper/cli.py`、`gt7_scraper/scraper.py`）
- `gt7_scraper/engine/*` 下的 legacy engine bridge shim（catalog/downloader/playwright/spec）

如需调试包，可使用 `--include-full-python-backends` 保留完整 Python 后端模块。

## 本地手动打包
前置依赖：
- Python 3.13+
- Go
- Rust/Cargo
- .NET 8 SDK
- Node 20+（`full` 必需）

### Lite
```bash
python scripts/release/build_release.py \
  --flavor lite \
  --platform darwin-arm64 \
  --version vX.Y.Z \
  --out-dir ./dist/release
```

### Full
```bash
python scripts/release/build_release.py \
  --flavor full \
  --platform darwin-arm64 \
  --version vX.Y.Z \
  --out-dir ./dist/release
```

### 一键矩阵构建（手动）
```bash
TAG=vX.Y.Z
for PLATFORM in darwin-arm64 darwin-x64 linux-x64 linux-arm64 win-x64 win-arm64; do
  python scripts/release/build_release.py \
    --flavor lite \
    --platform "${PLATFORM}" \
    --version "${TAG}" \
    --out-dir ./dist/release
  python scripts/release/build_release.py \
    --flavor full \
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

流程：
1. 按 `平台 x flavor` 矩阵构建发布包。
2. 每个产物执行 smoke：
   - 校验默认后端策略是否生效
   - 校验 `query-fallback=off` 是否生效
3. 上传构建产物。
4. 自动创建/更新 GitHub Release，并上传所有产物与校验文件。

## 故障排查
- 原生后端缺失：
  - 执行 `bin/gt7db doctor --json`。
  - 检查 `runtime/native` 与 `manifest.json`。
- Worker 启动失败：
  - 检查 `runtime/python` 是否包含 Python runtime。
  - 检查 `runtime/python/worker` 下是否有 `gt7_scraper`、`gt7_query`、`scripts/build_dbs.py`。
- 平台不匹配：
  - 核对包名平台后缀与目标机器架构。
  - 用正确 `--platform` 重新构建。
- Full 包 Playwright 异常：
  - 检查 `runtime/playwright/browsers` 是否存在。
  - 用 `gt7db doctor --json` 检查 `gt7-playwright` 解析路径。
