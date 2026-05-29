#!/usr/bin/env bash
# DingTalk 文档校对工具 — macOS 一键安装脚本
#
# 用法（运营同学）：
#   curl -fsSL https://gitlab.alibaba-inc.com/dingding/dingtalk-docs/-/raw/main/tools/review/install.sh | bash
#
# 说明：脚本会自动检测并按需安装 Xcode CLT、Homebrew、Node.js、pnpm、配置 SSH key、克隆仓库、装依赖、启动服务。
# 已安装的步骤会自动跳过（幂等）。全程除一次 GitLab 贴 SSH 公钥外无需手动操作。

set -euo pipefail

# ===== 颜色 =====
BLUE='\033[1;34m'; GREEN='\033[1;32m'; YELLOW='\033[1;33m'; RED='\033[1;31m'; RESET='\033[0m'

# ===== 配置 =====
REPO_URL="git@gitlab.alibaba-inc.com:dingding/dingtalk-docs.git"
REPO_HOST="gitlab.alibaba-inc.com"
REPO_DIR="${HOME}/dingtalk-docs"
NODE_MIN_MAJOR=18
SSH_KEY="${HOME}/.ssh/id_ed25519"

# ===== 工具函数 =====
step() { echo; echo -e "${BLUE}▶ $*${RESET}"; }
ok()   { echo -e "  ${GREEN}✓${RESET} $*"; }
warn() { echo -e "  ${YELLOW}⚠${RESET} $*"; }
fail() { echo -e "  ${RED}✗${RESET} $*" >&2; exit 1; }
# curl | bash 模式下 stdin 已被占用，必须从 /dev/tty 读取交互
prompt_continue() { read -r -p "  $* " _ < /dev/tty || true; }

trap 'echo; echo -e "${RED}安装中断。如需帮助请联系开发同学。${RESET}" >&2' ERR

echo
echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${RESET}"
echo -e "${BLUE}║   DingTalk 文档校对工具 — Mac 一键安装                          ║${RESET}"
echo -e "${BLUE}║   预计耗时 5–15 分钟（取决于网络与已装组件）                       ║${RESET}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${RESET}"

# ===== 0. 前置自检 =====
step "步骤 0/6：环境自检"

if [[ "$(uname -s)" != "Darwin" ]]; then
  fail "本脚本仅支持 macOS。当前系统：$(uname -s)"
fi
ok "macOS $(sw_vers -productVersion) 识别成功"

if ! ping -c 1 -W 2000 "${REPO_HOST}" >/dev/null 2>&1; then
  fail "无法连接 ${REPO_HOST}，请先连接公司 VPN 后重新运行本脚本。"
fi
ok "公司网络连接正常"

# ===== 1. Xcode Command Line Tools =====
step "步骤 1/6：检查 Xcode Command Line Tools（git 依赖）"

if xcode-select -p >/dev/null 2>&1; then
  ok "已安装：$(xcode-select -p)"
else
  warn "未安装。即将弹出系统安装窗口，请点击「安装」并等待完成。"
  xcode-select --install >/dev/null 2>&1 || true
  echo -n "  等待安装中"
  wait_seconds=0
  while ! xcode-select -p >/dev/null 2>&1; do
    sleep 10
    wait_seconds=$((wait_seconds + 10))
    echo -n "."
    if [[ ${wait_seconds} -ge 900 ]]; then
      echo
      fail "等待超过 15 分钟。请手动完成安装后重新运行本脚本。"
    fi
  done
  echo
  ok "安装完成：$(xcode-select -p)"
fi

# ===== 2. Homebrew =====
step "步骤 2/6：检查 Homebrew"

if command -v brew >/dev/null 2>&1; then
  ok "$(brew --version | head -1)"
else
  warn "未安装。即将运行 Homebrew 官方安装脚本（会要求输入 Mac 登录密码）。"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" \
    || fail "Homebrew 安装失败，请重试或参考 https://brew.sh"

  # 设置当前 shell PATH + 持久化到 ~/.zprofile
  if [[ -x /opt/homebrew/bin/brew ]]; then
    BREW_BIN=/opt/homebrew/bin/brew
  elif [[ -x /usr/local/bin/brew ]]; then
    BREW_BIN=/usr/local/bin/brew
  else
    fail "Homebrew 安装后未找到 brew 命令"
  fi
  eval "$(${BREW_BIN} shellenv)"
  PROFILE_LINE="eval \"\$(${BREW_BIN} shellenv)\""
  if ! grep -qsF "${PROFILE_LINE}" "${HOME}/.zprofile" 2>/dev/null; then
    echo "${PROFILE_LINE}" >> "${HOME}/.zprofile"
  fi
  ok "已安装并写入 PATH：$(brew --version | head -1)"
fi

# ===== 3. Node + pnpm =====
step "步骤 3/6：检查 Node.js 与 pnpm"

NEED_INSTALL_NODE=0
if command -v node >/dev/null 2>&1; then
  CUR_MAJOR=$(node -v | sed 's/^v//' | cut -d. -f1)
  if [[ "${CUR_MAJOR}" -ge "${NODE_MIN_MAJOR}" ]]; then
    ok "Node.js $(node -v)"
  else
    warn "Node.js 版本过低（$(node -v)，需要 ≥ v${NODE_MIN_MAJOR}），升级中…"
    NEED_INSTALL_NODE=1
  fi
else
  echo "  Node.js 未安装，通过 Homebrew 安装中（约 1–2 分钟）…"
  NEED_INSTALL_NODE=1
fi

if [[ ${NEED_INSTALL_NODE} -eq 1 ]]; then
  brew install node || fail "Node.js 安装失败"
  ok "Node.js $(node -v) 已就绪"
fi

if command -v corepack >/dev/null 2>&1; then
  corepack enable >/dev/null 2>&1 || true
  corepack prepare pnpm@latest --activate >/dev/null 2>&1 || true
fi

if command -v pnpm >/dev/null 2>&1; then
  ok "pnpm $(pnpm -v)"
else
  npm install -g pnpm >/dev/null 2>&1 || fail "pnpm 安装失败"
  ok "pnpm $(pnpm -v)"
fi

# ===== 4. SSH key =====
step "步骤 4/6：配置 SSH 密钥（用于推送代码到 GitLab）"

if [[ -f "${SSH_KEY}" || -f "${HOME}/.ssh/id_rsa" ]]; then
  ok "已存在 SSH 密钥，跳过生成"
  [[ ! -f "${SSH_KEY}" && -f "${HOME}/.ssh/id_rsa" ]] && SSH_KEY="${HOME}/.ssh/id_rsa"
else
  echo "  正在生成 SSH 密钥…"
  mkdir -p "${HOME}/.ssh" && chmod 700 "${HOME}/.ssh"
  ssh-keygen -t ed25519 -C "$(whoami)@dingtalk-docs" -N "" -f "${SSH_KEY}" >/dev/null
  ok "已生成：${SSH_KEY}"
fi

# 启动 ssh-agent + 添加到 Keychain（容错多个 macOS 版本）
eval "$(ssh-agent -s)" >/dev/null 2>&1 || true
ssh-add --apple-use-keychain "${SSH_KEY}" >/dev/null 2>&1 \
  || ssh-add -K "${SSH_KEY}" >/dev/null 2>&1 \
  || ssh-add "${SSH_KEY}" >/dev/null 2>&1 || true

# 测试 SSH 是否已通
test_ssh() {
  ssh -T -o StrictHostKeyChecking=accept-new -o ConnectTimeout=5 \
    -o BatchMode=yes "git@${REPO_HOST}" 2>&1 || true
}

SSH_TEST_OUT=$(test_ssh)
if echo "${SSH_TEST_OUT}" | grep -qiE "welcome|successfully|gitlab"; then
  ok "SSH 已连通 GitLab"
else
  PUBKEY=$(cat "${SSH_KEY}.pub")
  echo "${PUBKEY}" | pbcopy 2>/dev/null || true

  echo
  echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
  echo -e "${YELLOW}  请把 SSH 公钥添加到 GitLab（仅首次需要做一次）${RESET}"
  echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
  echo "  ① 公钥已自动复制到剪贴板"
  echo "  ② 即将自动打开 GitLab 添加密钥页面"
  echo "  ③ Title 随意（如 my-mac），Key 框 ⌘+V 粘贴"
  echo "  ④ 点击 Add key 保存"
  echo "  ⑤ 回到本终端按回车继续"
  echo

  open "https://${REPO_HOST}/-/profile/keys" 2>/dev/null \
    || echo "  （请手动打开：https://${REPO_HOST}/-/profile/keys）"

  prompt_continue "完成后按回车继续…"

  SSH_TEST_OUT=$(test_ssh)
  if echo "${SSH_TEST_OUT}" | grep -qiE "welcome|successfully|gitlab"; then
    ok "SSH 已连通 GitLab"
  else
    echo
    echo -e "${RED}SSH 验证失败。请确认已在 GitLab 点击 'Add key' 保存。${RESET}"
    echo -e "${RED}详细输出：${RESET}"
    echo "${SSH_TEST_OUT}" | sed 's/^/    /'
    fail "SSH key 未添加成功，请重新运行本脚本"
  fi
fi

# ===== 5. clone 仓库 =====
step "步骤 5/6：获取代码仓库"

if [[ -d "${REPO_DIR}/.git" ]]; then
  echo "  仓库已存在，拉取最新代码…"
  cd "${REPO_DIR}"
  git fetch --quiet origin || warn "git fetch 失败，继续使用本地代码"
  CUR_BRANCH=$(git rev-parse --abbrev-ref HEAD)
  git pull --ff-only --quiet origin "${CUR_BRANCH}" 2>/dev/null \
    || warn "本地有未提交修改或冲突，已跳过 pull（保留本地状态）"
  ok "已更新（当前分支：${CUR_BRANCH}）"
elif [[ -e "${REPO_DIR}" ]]; then
  fail "${REPO_DIR} 已存在但不是 git 仓库。请手动确认并删除/重命名后再运行。"
else
  echo "  首次克隆约需 3–5 分钟（仓库约 1.1 GB），请耐心等待…"
  git clone "${REPO_URL}" "${REPO_DIR}" || fail "git clone 失败"
  ok "已克隆到 ${REPO_DIR}"
fi

# 兼容：tools/review 当前位于 feat/docs 分支，合并到 main 后此段自动短路
if [[ ! -d "${REPO_DIR}/tools/review" ]]; then
  warn "当前分支未找到 tools/review，切换到 feat/docs…"
  cd "${REPO_DIR}"
  git fetch --quiet origin feat/docs 2>/dev/null || true
  git checkout --quiet feat/docs 2>/dev/null \
    || git checkout --quiet -b feat/docs origin/feat/docs \
    || fail "切换 feat/docs 失败，请联系开发同学"
  ok "已切换到 feat/docs 分支"
fi

# ===== 6. 装依赖 + 启动 =====
step "步骤 6/6：安装校对工具依赖"

cd "${REPO_DIR}/tools/review"
pnpm install || fail "依赖安装失败"
ok "依赖已就绪"

# 创建桌面快捷启动脚本
DESKTOP_DIR="${HOME}/Desktop"
if [[ -d "${DESKTOP_DIR}" ]]; then
  SHORTCUT="${DESKTOP_DIR}/启动校对工具.command"
  cat > "${SHORTCUT}" <<EOF
#!/bin/bash
cd "${REPO_DIR}/tools/review" && exec pnpm dev
EOF
  chmod +x "${SHORTCUT}"
  ok "已创建桌面快捷方式：启动校对工具.command"
fi

echo
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${RESET}"
echo -e "${GREEN}║   ✓ 安装完成！即将启动校对工具…                                  ║${RESET}"
echo -e "${GREEN}║   浏览器会自动打开 http://localhost:5173                        ║${RESET}"
echo -e "${GREEN}║   退出请在本终端按 Ctrl + C                                     ║${RESET}"
echo -e "${GREEN}║   下次使用：双击桌面上的「启动校对工具.command」                    ║${RESET}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${RESET}"
echo

# SKIP_LAUNCH=1 给自动化测试用，跳过实际启动
if [[ "${SKIP_LAUNCH:-0}" == "1" ]]; then
  ok "SKIP_LAUNCH=1，不启动 pnpm dev（测试模式）"
  exit 0
fi

exec pnpm dev
