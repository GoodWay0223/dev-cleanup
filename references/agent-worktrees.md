# 智能体工作树与本地分支

多个 AI 会话（Claude Code、Codex 等）同时在一台电脑上工作时，每个任务通常开一个 git worktree。游戏项目的工作树带导入缓存和下载资源，每个 2–3 GB，两天就能长出十几 GB，是磁盘被占满的头号原因。

只有用户授权清理工作树时才删；只是“看看占用”时只出报告。

## 先出报告

```bash
python3 <skill-dir>/scripts/worktree_report.py <主仓库> \
  --gh owner/repo \
  --keep <长期保留的工作树名> \
  --asset 'game/data/*' --asset 'test-logs-*'
```

脚本只读，不 fetch、不删除。需要最新远端状态时，先自己 `git -C <主仓库> fetch --prune origin`（只更新本地的远端跟踪引用）。它对每个工作树给出：

- `removable`：可删。
- `removable_after_backup`：可删，但先把列出的少量手写小文件（如调试脚本）复制到工作树之外的备份目录，并在汇报里写明位置。
- `keep`：保留，并给出原因。
- `stale_record`：目录已不在，只需 `git worktree prune`。

`idle import caches` 一行列出闲置 3 天以上、但因为有改动而保留的工作树的导入缓存（`.godot`、`Library` 等）。只删这些缓存，代码和改动不动。

分支部分只列没有被任何工作树检出的本地分支：`deletable` 可删，`keep` 表示有未推送的提交。

## 判定规则（脚本据此实现）

工作树必须**全部**满足才可删：

1. **没人在用**：没有进程打开其中的文件或以它为当前目录（`lsof`）。拿不到进程清单就保留。注意你自己的 shell 若 `cd` 进去也会算“在用”。
2. **闲置**：排除 `.git`、`.godot`、`node_modules`、`Library` 等可重建目录后，最新文件超过 24 小时没改（可调）。最近有改动说明另一个会话可能还在做。
3. **没有未提交的已跟踪改动**：忽略 Godot 的 `*.import`、`*.uid` 这类编辑器自动生成的变化。
4. **未跟踪文件都不是手写的**：允许 `.godot/`、生成物、从对象存储/CDN 拉下的资源（用 `--asset` 声明）。少量手写小文件可先备份后删；多了就保留。
5. **HEAD 不只在本机**：已在 `origin/main`、或某个远端分支包含它、或 `git cherry` 显示补丁已进 main、或该分支的 PR 已 MERGED。

永远保留：

- 主仓库本身（只清它的多余分支）。
- 用户或项目指定的工具工作树（出截图、发布、部署用的），用 `--keep` 传入。
- 被锁定的工作树（`git worktree lock`）。
- Codex 托管的工作树：用 Codex 的归档功能处理。

## 执行删除

对报告中 `removable` 的项，删除前再确认一次没人在用，然后：

```bash
git -C <主仓库> worktree remove --force <工作树绝对路径>
git -C <主仓库> worktree prune
git -C <主仓库> branch -D <该工作树的分支>   # 仅当分支也判定可删
```

`--force` 只是为了越过生成文件造成的“有改动”，前面的判定已经保证没有真实工作。

分支：报告为 `deletable` 的可以 `git branch -D`（压缩合并后 `-d` 会拒绝，所以用 `-D`，前提是判定已通过）。`prNNN` 这类拉下来看 PR 的本地分支：`gh pr view NNN --json state,headRefOid`，已合并且本地提交与 PR 最终提交一致才删；不一致可能是旧版本或本地改动，保留并报告。

绝不碰 GitHub：不删远端分支、不关 PR、不 push。

## 路径里有空格

很多用户把项目放在带空格的目录（如 `My Projects`）。不要用 `git worktree list | while read p h b` 这类按空格切分的写法，改用 `git worktree list --porcelain`；`find` 配 `-print0 | xargs -0`；变量一律加引号。zsh 里通配符没匹配会让整条命令失败，先 `setopt nullglob` 或用 `find`。

## 汇报

列出删了哪些工作树和分支（附依据：在 main / 已推送 / PR 已合并）、备份了哪些文件，以及保留的大工作树和原因（有未提交改动、最近在改、有人在用、只在本机）。保留项由用户决定，不要自行扩大范围。
