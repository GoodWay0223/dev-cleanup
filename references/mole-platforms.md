# Mole 与平台用法

Mole 是主要盘点与通用清理工具；本 Skill 负责缩小范围、补充开发场景核验。不要复制其清理规则或调用未公开的内部函数。

## 版本与安装

上游：[macOS](https://github.com/tw93/Mole)、[Windows](https://github.com/tw93/Mole/tree/windows)。本版验证基线为 macOS `V1.59.1` / Windows `V1.32.0-windows`，不是永远有效的最新版。执行前读取本机 `mo --version`、各子命令 `--help`；升级后重新验证，不能猜测参数。

macOS 面向 Apple Silicon / Intel；Windows 分支面向 Windows 10/11、PowerShell 5.1 及以上。Windows 命令和功能与 macOS 不完全相同；Linux 不在本 Skill 支持范围。

只有用户已经要求安装或升级时才执行安装。先查已有位置和版本，使用官方发布及其完整性校验，避免覆盖已有工具。不使用未经审阅的 `curl | bash` / `irm | iex`。

- macOS：已有 Homebrew 可用官方 `brew install mole`。没有 Homebrew 时，下载并审阅固定官方 tag 的 `install.sh`，使用用户目录的 `--prefix`；不要为安装 Mole 顺带安装 Homebrew。官方安装器校验下载二进制的 SHA256 和发布证明，校验失败就停止。
- Windows：优先沿用已安装的官方发行版。需要手动安装时，克隆并审阅官方 Windows tag，运行其 `install.ps1 -InstallDir <user-directory> -AddToPath`。缺少 Git 或 PowerShell 时先说明，不改变机器级 ExecutionPolicy。确需运行本地脚本可仅对该 PowerShell 进程设置 `-ExecutionPolicy Bypass`；不使用 `-Force` 覆盖现有安装，不要求管理员权限。
- 官方安装器通常创建 `mo`/`mole`（Mac）或 `mo.cmd`/`mole.cmd`/`mole.ps1`（Windows）。Scoop 等发行方式可能使用 `mo.exe`。检测实际路径，不假定用户目录名或固定盘符。

## 先预览

两个平台共同支持：

```text
mo --version
mo clean --help
mo clean --dry-run
mo purge --help
mo purge --dry-run
```

`clean --dry-run` 不删除候选文件，但 Mole 可以写入自己的配置和预览清单。把这些清单作为私人审计记录，重新运行前保存本次副本；不要上传个人路径或日志。

可用本 Skill 的只预览包装器保存版本、帮助、输出与扫描限制：

```text
python <skill-dir>/scripts/mole_preview.py clean
python <skill-dir>/scripts/mole_preview.py purge
```

macOS 可将 `python` 换成 `python3`，Windows 也可用 `py -3`。默认报告放在用户的 `.codex/attachments`，不放入 Git 仓库。包装器只接受预览操作，没有删除、更新、管理员清理或任意附加参数入口。退出码 0 也不证明完整盘点；超时、跳过、权限或扫描限制须保留在报告中。`purge` 需要交互的版本可能无法在包装器中完成，改为人工预览并记录限制。

## 平台差异

| 操作 | macOS 验证基线 | Windows 验证基线 |
| --- | --- | --- |
| 空间分析 | `mo analyze --json <path>` 可用于只读输出，选项放路径前 | `mo analyze <path>` 为交互工具；没有 `--json`，包装器拒绝自动调用 |
| clean 范围 | 没有 `--select`、`--categories`、`--exclude` | 不假定有 macOS 的参数；`--system` 扩大到系统且需管理员，不属于默认范围 |
| purge | `--paths` 配置扫描根；`--yes` 会执行清理，不能用于常规批量清理 | `--paths` 配置扫描根；本验证版本没有 `--yes` |
| 打开文件 | `lsof` + 活动任务核验 | 文件锁的只读排他打开 + 构建/测试进程核验 |
| 模拟器 | `xcrun simctl`，仅删除通过年龄和用途核验的具体 UUID | 不存在 iOS `simctl`；保留 Hyper-V、WSL、Docker 和 Android 虚拟设备 |

两个平台的 analyze 交互界面均有删除按键；只做盘点时不要使用删除键。包装器只运行 Mac 的 JSON 模式。`mo purge --paths` 和 `mo clean --whitelist` 会修改 Mole 配置，只在本次范围需要且授权涵盖时修改，并保存原配置以便回退。

## 何时执行 Mole 清理

`clean` 的默认范围可能包含日志、垃圾桶、依赖缓存、浏览器资料；`purge` 会发现 `node_modules`、虚拟环境、Pods、vendor 等本 Skill 默认保留项。Mole 白名单不等于当前清单已经安全。

审核整组和当前版本的选项后，只有工具能把操作严格限制在确认可删的清单时才执行。若选择某个项目会同时删除其依赖、结果或未完成证据，保持原样，列出保留理由。对 Mole 未覆盖的明确生成缓存及已核实的测试导出，沿用审计脚本，冻结路径，逐项补充删除；不要借此自建通用清理引擎。

不要擅自运行 `mo optimize`、`mo uninstall`、`mo remove`、`mo update`，不要使用 sudo/管理员扩大扫描或删除。没有权限的项保持原样。
