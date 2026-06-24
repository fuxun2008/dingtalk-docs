# scripts/hooks/

入仓的 git hooks。默认 `.git/hooks/` 不进版本控制，每个 contributor 都要自己复制；本目录解决这个分发问题。

## 启用（每台机器一次性）

```bash
git config core.hooksPath scripts/hooks
```

验证：

```bash
git config --get core.hooksPath
# 应输出: scripts/hooks
```

## 当前 hooks

| Hook | 作用 |
|---|---|
| `pre-push` | push 前自动跑 `scripts/generate_sitemap.py`，sitemap.xml 落后于当前 `.mdx` 状态时中断 push 并提示 commit |

## 紧急绕过

如果 hook 出问题、需要单次绕过：

```bash
git push --no-verify
```
