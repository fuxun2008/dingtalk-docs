# DingTalk Help Center

Documentation site at https://help.dingtalk.io — powered by [Mintlify](https://mintlify.com).

## Local development

```bash
npm i -g mint    # one-time
mint dev         # http://localhost:3000
mint broken-links
```

## Structure

```
.
├── docs.json          # site config (colors, languages, navigation)
├── index.mdx          # English (default lang)
├── quickstart.mdx
├── guides/
├── zh/                # Chinese mirror
├── ja/                # Japanese mirror
├── logo/
└── favicon.svg
```

Three languages keep **identical file structure** for translation alignment.

## Deployment

Push to `main` → Mintlify GitHub App auto-builds → live at https://help.dingtalk.io.
