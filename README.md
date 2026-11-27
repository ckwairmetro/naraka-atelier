# Naraka Atelier

[English](#english) · [简体中文](#简体中文)

[Download the bilingual installation page · 下载双语安装页面](https://github.com/ckwairmetro/naraka-atelier/releases/download/v0.2.9.2/installation.html)

## English

Naraka Atelier customizes the local appearance of NARAKA: BLADEPOINT. The Windows release includes the catalogue and the Python runtime. On a new PC, download the release ZIP and use the installed copy of Naraka.

### Install on Windows

1. Sign in to GitHub with an account that has access to this private repository. Under **Assets**, download **NarakaAtelier-v0.2.9.2-win-x64.zip**. [Download the release](https://github.com/ckwairmetro/naraka-atelier/releases/tag/v0.2.9.2)
2. In File Explorer, right-click the ZIP and choose **Extract All**. Keep **NarakaAtelier.exe** and the **_internal** folder together.
3. Close Naraka and its launcher, then double-click **NarakaAtelier.exe**. If the window fails to open, install the **Evergreen WebView2 Runtime** from Microsoft and try again. [Microsoft WebView2 download](https://developer.microsoft.com/en-us/microsoft-edge/webview2/#download)
4. Atelier detects a single Steam installation automatically. If it asks for a folder, choose the one containing **NarakaBladepoint.exe**. In Steam, you can find it through **Manage → Browse local files**.
5. When Atelier reports that the client is verified, choose your cosmetic settings and apply them with the game closed. You can open Naraka again when Atelier finishes.

### Compatibility

- Windows 10 or 11, 64-bit. This release targets **Steam build 26771036** and includes the catalogue for **client version 1.5.9.2**. A game update can change the required file hashes even when the client version shown is the same.
- If Atelier reports a client or resource mismatch, use Steam’s **Properties → Installed Files → Verify integrity of game files** to repair altered files. If Steam installs a newer build, use an Atelier release that explicitly supports it.
- If automatic detection picks a different copy of the game, close Atelier and run `NarakaAtelier.exe --game-dir "C:\Path To\NARAKA BLADEPOINT"` from the extracted folder. For a separate Atelier profile, add `--state-dir "C:\Path To\Atelier State"`.

## 简体中文

Naraka Atelier 用于自定义《永劫无间》在本机显示的外观。Windows 发布包已内置外观目录和 Python 运行环境。新电脑装好游戏后，下载发布包即可，无需另行下载或导入目录。

### Windows 安装步骤

1. 使用有权访问此私有仓库的 GitHub 账号登录，在发布页面的 **Assets（资源）** 中下载 **NarakaAtelier-v0.2.9.2-win-x64.zip**。[下载发布包](https://github.com/ckwairmetro/naraka-atelier/releases/tag/v0.2.9.2)
2. 在文件资源管理器中右键点击 ZIP，选择 **全部解压缩**。请将 **NarakaAtelier.exe** 和 **_internal** 文件夹保留在同一目录下。
3. 退出《永劫无间》及其启动器，双击 **NarakaAtelier.exe**。如果窗口无法打开，请安装微软的 **Evergreen WebView2 运行时**后重试。[微软 WebView2 下载](https://developer.microsoft.com/en-us/microsoft-edge/webview2/#download)
4. Atelier 会自动识别单个 Steam 游戏安装。如果提示选择目录，请选择包含 **NarakaBladepoint.exe** 的文件夹。可在 Steam 中通过 **管理 → 浏览本地文件** 找到该目录。
5. 客户端验证通过后，选择所需的外观设置，并在游戏关闭时应用。应用完成后即可重新启动游戏。

### 兼容性

- 支持 64 位 Windows 10 或 11。本发布包适配 **Steam 构建版本 26771036**，内置 **客户端版本 1.5.9.2** 的目录。游戏更新后，即使显示的客户端版本号相同，文件校验值也可能改变。
- 如果 Atelier 提示客户端或资源文件不匹配，可在 Steam 中选择 **属性 → 已安装文件 → 验证游戏文件的完整性**来修复被修改的文件。如果 Steam 已安装更新的构建版本，请使用明确支持该版本的 Atelier 发布包。
- 如果自动识别选中了另一份游戏，关闭 Atelier 后，在解压目录中运行 `NarakaAtelier.exe --game-dir "C:\Path To\NARAKA BLADEPOINT"`。如需使用独立的 Atelier 配置，可加上 `--state-dir "C:\Path To\Atelier State"`。

[Developer build notes · 开发者打包说明](app/README.md)
