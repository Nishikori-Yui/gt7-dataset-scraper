# 贡献指南

[English](CONTRIBUTING.md) | [简体中文](CONTRIBUTING.zh-CN.md)

感谢贡献。请保持仓库干净并遵守合规要求。

## 规则
- 不提交任何抓取数据、图片、Logo 或数据库文件。
- 不提交 `output/` 下的文件。
- 不提交任何第三方资产或受版权保护的内容。
- 代码注释保持英文。
- 文档优先维护英文版，允许在 `docs/` 下提供可选翻译（例如 `*.zh-CN.md`）。

## 文件放置规则
- 运行时编排代码放在 `gt7_scraper/app/` 与 `gt7_query/app/`。
- 业务逻辑放在 `gt7_scraper/domain/` 与 `gt7_query/domain/`。
- 后端适配器（python/native bridge）放在 `gt7_scraper/backends/` 与 `gt7_query/backends/`。
- 基础设施辅助（DB/HTTP/IO）放在 `gt7_scraper/infra/` 与 `gt7_query/infra/`。
- 仅用于兼容转发的模块放在 `gt7_scraper/compat/` 与 `gt7_query/compat/`。
- 原生工具链源码继续保留在顶层 `engines/`，不要迁入运行时包目录。

## PR 检查清单
- [ ] 未包含数据或资产
- [ ] 未包含 `output/` 文件
- [ ] 未包含 `.db` 文件
- [ ] 代码可运行

## 安全
- 不提交密钥或凭证。

## 许可协议
- 贡献内容遵循项目许可证（Apache-2.0）。
