# Contributing

[简体中文](CONTRIBUTING.zh-CN.md)

- Keep the main workflow in Python. Go is limited to the catalog parser and image downloader.
- Do not commit scraped data, databases, images, logos, credentials, or files from `output/`.
- Keep source comments in English and update the Chinese guide when changing user-facing instructions.
- Run `python -m unittest discover -s tests -v`. Use the release smoke check when changing packaging.
- Contributions are licensed under Apache-2.0.
