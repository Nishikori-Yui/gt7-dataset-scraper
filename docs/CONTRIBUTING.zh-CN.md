# 贡献指南

[English](CONTRIBUTING.md)

- 主流程使用 Python；Go 仅保留目录解析和图片下载。
- 不要提交抓取数据、数据库、图片、Logo、凭证或 `output/` 中的文件。
- 源码注释使用英文；修改面向用户的说明时同步更新中文指南。
- 提交 PR 前运行 `uv run python -m unittest discover -s tests -v`。修改打包逻辑时再运行发布包烟测。
- 贡献内容遵循 Apache-2.0 许可协议。
