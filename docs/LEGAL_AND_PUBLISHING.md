# Legal & Publishing Guidance

[English](LEGAL_AND_PUBLISHING.md) | [简体中文](LEGAL_AND_PUBLISHING.zh-CN.md)

This document provides general, non-legal guidance for responsible use and publication.
It is **not legal advice**. You are responsible for reviewing the applicable terms of
service and local laws before running the scraper.

## Key Principles
1. Respect site terms.
2. Do not redistribute scraped assets.
3. Separate code and data.
4. Avoid endorsement confusion.
5. Use minimal access for testing.

## Publishing Checklist
- Ensure `output/` and `*.db` files are ignored in `.gitignore`.
- Do not commit any scraped images, logos, or JSON payloads.
- Keep the repo focused on code and documentation only.
- Add a legal notice to README.
- Keep trademark/copyright notices intact in output datasets if used internally.

## Where Terms Usually Restrict Usage
Most site terms reserve ownership of content and prohibit re-use to build databases or
redistribute assets. If a term disallows such usage, do not proceed without permission.

## Suggested README Notice (short form)
- This project is for educational purposes only.
- Users are responsible for complying with the website terms and applicable laws.
- The repository does not include scraped data or assets.
- All trademarks and copyrights belong to their respective owners.

## Optional Hardening (if you publish widely)
- Default to `--skip-images` in examples.
- Provide a `--car-list` example to encourage small-scope runs.
- Make Playwright optional and clearly documented.
- Add a CONTRIBUTING note requiring no datasets/assets in PRs.
