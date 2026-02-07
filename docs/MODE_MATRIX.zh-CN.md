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

| 用例 | 追加参数 | 退出码 | hero 总数 | detail 空值数 | 说明 |
|---|---|---:|---:|---:|---|
| `py_no_pw` | `--engine python` | 0 | 41 | 0 | 稳定基线 |
| `py_pw_python` | `--engine python --use-playwright --playwright-engine python --playwright-workers 1` | 0 | 41 | 0 | 比非 Playwright 慢 |
| `hybrid_no_pw_rust` | `--engine hybrid --engines-dir ./local/bin --spec-engine rust --playwright-engine node` | 0 | 41 | 0 | 推荐默认模式 |
| `hybrid_no_pw_python_spec` | `--engine hybrid --engines-dir ./local/bin --spec-engine python --playwright-engine node` | 0 | 41 | 0 | 数据质量一致，仅 spec 路径不同 |
| `hybrid_pw_node` | `--engine hybrid --engines-dir ./local/bin --spec-engine rust --use-playwright --playwright-engine node --playwright-workers 1` | 0 | 41 | 0 | 最慢；已通过质量回退修复 |

耗时对比（同一轮 10 车，单位秒）：

| 用例 | duration_sec | 相对 `hybrid_no_pw_rust` |
|---|---:|---:|
| `hybrid_no_pw_rust` | 72 | 1.00x |
| `hybrid_no_pw_python_spec` | 74 | 1.03x |
| `py_no_pw` | 78 | 1.08x |
| `py_pw_python` | 138 | 1.92x |
| `hybrid_pw_node` | 296 | 4.11x |

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

| 用例 | 追加参数 | 退出码 | duration_sec | 结果 |
|---|---|---:|---:|---|
| `build_dbs_python` | `--engine python` | 0 | 109 | 生成 `cn/jp/gb/us` 四个单语言库 + `gt7.db` |
| `build_dbs_hybrid` | `--engine hybrid --engines-dir ./local/bin --spec-engine rust` | 0 | 106 | 生成 `cn/jp/gb/us` 四个单语言库 + `gt7.db` |

## 推荐默认值
- 单语言抓取：`hybrid_no_pw_rust`
- 多语言构建：`scripts/build_dbs.py --engine hybrid --playwright-policy off`
- 仅在明确需要浏览器回退时再启用 Playwright。

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
