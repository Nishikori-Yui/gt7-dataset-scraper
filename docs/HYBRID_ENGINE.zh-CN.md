# 混合引擎指南

[English](HYBRID_ENGINE.md) | [简体中文](HYBRID_ENGINE.zh-CN.md)

本文说明如何构建并使用混合执行路径（`--engine hybrid`）。
各模式的实测命令与结果请参考 [MODE_MATRIX.zh-CN.md](MODE_MATRIX.zh-CN.md)。

## 推荐策略
- 生产默认建议使用：`--engine hybrid --playwright-policy off`。
- 在已验证的 smoke 结果中，`hybrid_no_pw_rust` 相比纯 Python 基线更快，且质量校验结果一致。
- Playwright 建议仅作为回退路径，在确实需要浏览器提取时再启用。

## 混合模式使用的组件
- Go 下载器：`engines/gt7_downloader`
- Node/Playwright Worker：`engines/gt7_playwright`
- Rust 规格归一化器：`engines/gt7_spec_normalizer`
- C++ 合并引擎（可选）：`engines/gt7_db_merge_cpp`

Python 爬虫仍作为编排层，SQLite schema 不变。

## 依赖环境准备
建议最低工具链：
- Python `3.10+`
- Go `1.21+`
- Node.js `18+` 与 `npm`
- Rust stable（`cargo`）

一键初始化（推荐）：
```bash
./scripts/bootstrap_hybrid_env.sh
```

可选参数：
- `--no-system-install`：仅做 venv 与本地组件构建
- `--skip-playwright-browser`：跳过 `npx playwright install chromium`
- `--skip-build`：只安装/检查工具链与 Python 依赖
- `--skip-cpp-merge-build`：跳过构建 `local/bin/gt7-db-merge`

macOS（Homebrew）：
```bash
brew install python go node rustup-init
rustup-init -y
source "$HOME/.cargo/env"
```

Ubuntu/Debian：
```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip golang-go nodejs npm curl build-essential
curl https://sh.rustup.rs -sSf | sh -s -- -y
source "$HOME/.cargo/env"
```

创建 Python 虚拟环境：
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

检查工具链版本：
```bash
python --version
go version
node --version
npm --version
cargo --version
```

## 构建步骤

### 1) Go 下载器
```bash
cd engines/gt7_downloader
go build -o ../../local/bin/gt7-downloader .
```

### 2) Node Playwright Worker
```bash
cd engines/gt7_playwright
npm install
npx playwright install
npm run build
```

运行策略：
- 若存在 `./local/bin/gt7-playwright`，优先使用该可执行入口。
- 否则直接使用 `engines/gt7_playwright/dist/cli.js`。

可选 wrapper：
```bash
cat > local/bin/gt7-playwright <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
node "$(cd "$(dirname "$0")/../.." && pwd)/engines/gt7_playwright/dist/cli.js" "$@"
EOF
chmod +x local/bin/gt7-playwright
```

### 3) Rust 规格归一化器
```bash
cd engines/gt7_spec_normalizer
cargo build --release
cp target/release/gt7-spec-normalizer ../../local/bin/
```

### 4) C++ 合并引擎（可选）
```bash
cd engines/gt7_db_merge_cpp
./build.sh
```

## 运行示例
```bash
python -m gt7_scraper \
  --engine hybrid \
  --locale gb \
  --base-locale gb \
  --db ./output/gt7.db \
  --images ./output/images \
  --skip-images \
  --workers 4 \
  --commit-batch 50 \
  --sqlite-wal \
  --engines-dir ./local/bin
```

`scripts/build_dbs.py` 的 Hero 校验模式：
- `--hero-check off`：关闭 Hero 校验
- `--hero-check strict`：只要有差异就失败（退出码 `3`）
- `--hero-check soft`：始终输出差异报告，且仅在以下两个条件同时满足时失败：
  - `mismatch_ratio > --hero-soft-max-ratio`（默认 `0.05`）
  - `mismatch_rows > --hero-soft-max-count`（默认 `20`）
  - soft 失败退出码：`4`

`soft` 模式示例：
```bash
python scripts/build_dbs.py \
  --engine hybrid \
  --locales gb,us,cn,jp \
  --base-locale gb \
  --out-dir ./output \
  --images ./output/images \
  --image-policy all-locales \
  --playwright-policy off \
  --hero-check soft \
  --hero-soft-max-ratio 0.05 \
  --hero-soft-max-count 20 \
  --hero-manifest ./gt7_scraper/mappings/hero_expected_counts.json \
  --engines-dir ./local/bin
```

`scripts/build_dbs.py` 的汇总库生成策略：
- `--combined-mode rescrape`（默认）：保持旧行为，逐语言直接写入 `gt7.db`
- `--combined-mode merge`：先生成 `gt7.<locale>.db`，再合并
- `--merge-engine python|cpp|go`：当 `combined-mode=merge` 时的合并后端
- `--merge-cpp-bin`：C++ 合并二进制路径（默认 `./local/bin/gt7-db-merge`）
- `--merge-go-bin`：Go 合并二进制路径（默认 `./local/bin/gt7-db-merge-go`）

示例（`merge + cpp`，失败自动回退 Python SQL 合并）：
```bash
python scripts/build_dbs.py \
  --engine hybrid \
  --locales gb,us,cn,jp \
  --base-locale gb \
  --combined-mode merge \
  --merge-engine cpp \
  --merge-cpp-bin ./local/bin/gt7-db-merge \
  --playwright-policy off \
  --engines-dir ./local/bin
```

构建流程默认使用 hero 清单。若要从本地 reference 图片重新生成：
```bash
python scripts/generate_hero_manifest.py \
  --reference-images-dir ./output/reference/images \
  --out ./gt7_scraper/mappings/hero_expected_counts.json
```

启用 Playwright 回退：
```bash
python -m gt7_scraper \
  --engine hybrid \
  --use-playwright \
  --playwright-engine node \
  --playwright-workers 4 \
  --engines-dir ./local/bin
```

## 引擎解析与回退
- 下载器：
  - `--engine hybrid` 会优先使用 Go 下载器。
  - 若未找到 `gt7-downloader`，自动回退到 Python 下载逻辑。
- Playwright：
  - `--playwright-engine node` 会优先使用 Node worker。
  - 若脚本/二进制缺失，自动回退到 Python Playwright 路径。
- 规格归一化：
  - `--spec-engine rust` 会优先使用 Rust 二进制。
  - 若二进制缺失或执行失败，自动回退到 Python 归一化逻辑。
- 汇总合并：
  - `--combined-mode merge --merge-engine cpp` 时优先使用 C++ 合并；
  - `--combined-mode merge --merge-engine go` 时优先使用 Go 合并；
  - 若二进制缺失或失败，自动回退 Python SQL 合并。
- Hero 校验：
  - `--hero-check-engine rust` 时优先使用 Rust Hero 校验引擎；
  - 若二进制缺失或失败，自动回退 Python Hero 校验逻辑。

## 验证清单
- CLI 参数检查：
```bash
python -m gt7_scraper --help
python scripts/build_dbs.py --help
```
- Python 编译检查：
```bash
python -m compileall gt7_scraper gt7_query scripts
```
- Node 语法检查：
```bash
node --check engines/gt7_playwright/dist/cli.js
```
- Rust 构建检查：
```bash
cd engines/gt7_spec_normalizer && cargo build --release
cd engines/gt7_hero_check_rust && cargo build --release
cd engines/gt7_query_go && go build -o ../../local/bin/gt7-query-go .
cd engines/gt7_db_merge_go && go build -o ../../local/bin/gt7-db-merge-go .
```

## 可选打包
可生成带统一入口的可分发包：
```bash
./scripts/package_gt7db.sh --flavor lite
./scripts/package_gt7db.sh --flavor full
```
