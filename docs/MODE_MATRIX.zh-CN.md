# 模式矩阵（已验证 Smoke 测试）

本文档汇总了当前仓库各主要运行模式的可复现 smoke 测试结果，供用户选型参考。

## 测试基线
- 日期：2026-02-07
- 数据集：`scripts/example_car_ids_10.txt`（10 辆车）
- 语言：单次抓取使用 `gb`；构建测试使用 `cn,jp,gb,us`
- 环境前提：
  - 激活 `.venv` 或直接使用 `./.venv/bin/python`
  - 使用 `--engine hybrid` 时，`./local/bin` 中已有对应二进制

## `gt7_scraper` 模式

命令基础参数：
```bash
./.venv/bin/python -m gt7_scraper \
  --locale gb \
  --base-locale gb \
  --car-list scripts/example_car_ids_10.txt \
  --workers 1 \
  --rate 0 \
  --timeout 30
```

| 用例 | 追加参数 | 退出码 | hero 总数 | intro 空值数 | detail 空值数 | manifest 不匹配数 | 说明 |
|---|---|---:|---:|---:|---:|---:|---|
| `py_no_pw` | `--engine python` | 0 | 41 | 0 | 0 | 0 | 稳定基线 |
| `py_pw_python` | `--engine python --use-playwright --playwright-engine python --playwright-workers 1` | 0 | 41 | 0 | 0 | 0 | 比非 Playwright 慢 |
| `hybrid_no_pw_rust` | `--engine hybrid --engines-dir ./local/bin --spec-engine rust --playwright-engine node` | 0 | 41 | 0 | 0 | 0 | 推荐默认模式 |
| `hybrid_no_pw_python_spec` | `--engine hybrid --engines-dir ./local/bin --spec-engine python --playwright-engine node` | 0 | 41 | 0 | 0 | 0 | 数据质量一致，仅 spec 路径不同 |
| `hybrid_pw_node` | `--engine hybrid --engines-dir ./local/bin --spec-engine rust --use-playwright --playwright-engine node --playwright-workers 1` | 0 | 41 | 0 | 0 | 0 | 最慢；质量仍一致 |

耗时对比（同一轮 10 车，单位秒）：

| 用例 | duration_sec | 相对 `hybrid_no_pw_rust` |
|---|---:|---:|
| `hybrid_no_pw_rust` | 81.417 | 1.00x |
| `hybrid_no_pw_python_spec` | 87.830 | 1.08x |
| `py_no_pw` | 150.456 | 1.85x |
| `py_pw_python` | 217.399 | 2.67x |
| `hybrid_pw_node` | 467.462 | 5.74x |

## `build_dbs.py` 模式

命令基础参数：
```bash
./.venv/bin/python scripts/build_dbs.py \
  --locales cn,jp,gb,us \
  --base-locale gb \
  --car-list scripts/example_car_ids_10.txt \
  --workers 1 \
  --rate 0 \
  --timeout 30 \
  --playwright-policy off \
  --image-policy none \
  --text-policy target-only \
  --hero-check off
```

| 用例 | 追加参数 | 退出码 | duration_sec | locale 数 | detail 空值数 | 结果 |
|---|---|---:|---:|---:|---:|---|
| `build_dbs_python_rescrape` | `--engine python --combined-mode rescrape` | 0 | 128.374 | 4 | 0 | 生成 4 个单语言库与汇总 `gt7.db` |
| `build_dbs_hybrid_rescrape` | `--engine hybrid --engines-dir ./local/bin --spec-engine rust --combined-mode rescrape` | 0 | 152.922 | 4 | 0 | 生成 4 个单语言库与汇总 `gt7.db` |
| `build_dbs_hybrid_merge_python` | `--engine hybrid --engines-dir ./local/bin --spec-engine rust --combined-mode merge --merge-engine python` | 0 | 57.476 | 4 | 0 | 先生成单语言库，再以 SQL 后端合并 `gt7.db` |
| `build_dbs_hybrid_merge_cpp` | `--engine hybrid --engines-dir ./local/bin --spec-engine rust --combined-mode merge --merge-engine cpp` | 0 | 57.973 | 4 | 0 | 先生成单语言库，再以 C++ 后端合并 `gt7.db` |
| `build_dbs_hybrid_merge_go` | `--engine hybrid --engines-dir ./local/bin --spec-engine rust --combined-mode merge --merge-engine go` | 0 | 28.770* | 2 | 0 | 先生成单语言库，再以 Go 后端合并 `gt7.db`（`gb,us`，不下载图片） |

\* `build_dbs_hybrid_merge_go` 的耗时来自后端对比场景：`gb,us` + 10 车样本 + `--image-policy none`，不与上方 4 语言行做直接横向对比。

### 后端/回退 Smoke（2026-02-07，`gb,us`，10 车，不下载图片）

| 用例 | 退出码 | duration_sec | 核心结果 |
|---|---:|---:|---|
| `merge_engine_python` | 0 | 28.14 | `cars/car_texts/car_specs/fetch_log = 10/20/180/20` |
| `merge_engine_cpp` | 0 | 28.00 | 与 python merge 结果计数一致 |
| `merge_engine_go` | 0 | 28.77 | 与 python merge 结果计数一致 |
| `merge_engine_go_missing_bin` | 0 | 18.51 | 打印 warning，并自动回退 python merge |
| `hero_check_rust_missing_bin` | 0 | 15.87 | 打印 warning，并自动回退 python hero-check |
| `query_engine_go` | 0 | 0.04 | `list/stats/overview` 已完成对拍验证 |
| `query_engine_go_missing_bin` | 0 | 0.03 | 打印 warning，并自动回退 python query |
| `gt7db build-dbs` | 0 | 12.04 | Dotnet launcher 透传链路验证通过 |
| `gt7db query overview` | 0 | 0.32 | Dotnet launcher 透传链路验证通过 |

## 推荐默认值
- 单语言抓取：`hybrid_no_pw_rust`
- 多语言构建：`scripts/build_dbs.py --engine hybrid --playwright-policy off`
- 仅在明确需要浏览器回退时再启用 Playwright。
- 构建合并后端默认已切换为 `go`（`--merge-engine`），Hero 校验后端默认已切换为 `rust`（`--hero-check-engine`）。
- 查询 CLI 默认已切换为 `auto`：所有子命令优先走 Go，执行失败时自动回退 Python。

## 复现命令

单语言（推荐）：
```bash
./.venv/bin/python -m gt7_scraper \
  --engine hybrid \
  --locale gb \
  --base-locale gb \
  --db ./output/gt7.gb.db \
  --images ./output/images \
  --car-list scripts/example_car_ids_10.txt \
  --workers 1 \
  --rate 0 \
  --timeout 30 \
  --engines-dir ./local/bin \
  --spec-engine rust
```

多语言构建（推荐）：
```bash
./.venv/bin/python scripts/build_dbs.py \
  --engine hybrid \
  --locales cn,jp,gb,us \
  --base-locale gb \
  --out-dir ./output \
  --images ./output/images \
  --car-list scripts/example_car_ids_10.txt \
  --image-policy all-locales \
  --text-policy target-only \
  --playwright-policy off \
  --hero-check soft \
  --hero-soft-max-ratio 0.05 \
  --hero-soft-max-count 20 \
  --hero-manifest ./gt7_scraper/mappings/hero_expected_counts.json \
  --engines-dir ./local/bin
```

## 说明
- 耗时受网络、目标站点状态影响较大。
