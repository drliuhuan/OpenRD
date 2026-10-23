# OpenRD 使用指南 / User guide

[返回首页 / Back to home](../README.md)

## 获取试玩版 / Download the demo

如果你还没有游戏数据，可以从 Internet Archive 下载原官网曾公开提供的试玩安装包。以下链接指向第三方历史存档，OpenRD 不托管或重新分发这些文件。

If you do not have game data, you can download a demo installer originally offered on the game's website, preserved by the Internet Archive. These links point to third-party historical archives; OpenRD does not host or redistribute the files.

- [历史小体积试玩包 / Archived small demo installer — rddemosmall.exe](https://web.archive.org/web/20100919110824id_/http://coregames.com/downloads/rddemosmall.exe)
- [另一版历史试玩包 / Another archived demo installer — RDDEMO.exe](https://web.archive.org/web/20061007084947id_/http://www.coregames.com/downloads/RDDEMO.exe)

**目前上述试玩包的原版开放范围尚未核实，OpenRD 暂不开放其关卡。** 下载包内含有正式地图不代表获得游玩授权；旧导入目录也执行相同限制。可以保存原件，但不会因包内地图数量而开放全部内容。合法持有的已核验基准 ISO 或其正式/演示数据目录仍可启动。

**The native playable scope of these demos has not yet been verified, so OpenRD currently blocks their levels.** Bundled full-game maps do not establish permission to play them; the same policy applies to previously imported directories. Keeping the original download does not unlock its contents. Lawfully held verified reference ISOs and matching full-game/demo data directories remain playable.

存档服务偶尔可能较慢或暂时不可用，可稍后重试或使用备选链接。 / The archive service may occasionally be slow or unavailable; try again later or use the alternative link.

## 快速开始 / Quick start

需要 Python 3.10+。基准 ISO/正式目录的图集准备另需 Pillow、NumPy；安装器/压缩包解包需 7-Zip，InstallShield 另需 unshield。已准备好的基准游戏运行使用 Python 标准库。

Requires Python 3.10+. Preparing the reference ISO or matching game directory also requires Pillow and NumPy. Extracting installers or archives requires 7-Zip; InstallShield packages additionally require unshield. Running prepared reference data uses the Python standard library.

```powershell
python -m pip install -r requirements-build.txt
```

将 ISO 或游戏数据放入项目下的 `game` 文件夹，可以省略输入路径启动；也可以指定包含多个文件或子目录的文件夹。最多扫描 4 层子目录、10000 个条目，不跟随目录符号链接。

Place your ISO or game data in the project's `game` folder to start without an input argument, or specify a folder containing multiple files/subfolders. The scan covers up to 4 subdirectory levels and 10000 entries, without following directory symlinks.

```powershell
python tools/play.py
python tools/play.py "D:\GameData"
```

自动选择优先级为 **ISO → 游戏目录 → CAB → EXE**；同类按浅层目录和文件名顺序选择。先检查文件头，跳过明显损坏或不支持的文件；解析失败的候选也会尝试下一项。不执行原安装程序。能解析但原版试玩范围未核实的来源会明确拒绝，不会把授权失败当作解析失败继续切换内容。输入与跳过原因保存在本地运行目录的 run.json。

Selection priority is **ISO → game directory → CAB → EXE**. Within each type, shallower paths and filenames determine order. Headers are checked first; obviously damaged or unsupported files are skipped, and parsing failures allow the next candidate to be tried. Original installers are never executed. A recognized source with unverified native demo scope is rejected, rather than treating access denial as a parsing failure and switching content. Selection and skip reasons are recorded locally in run.json.

任选一种输入启动。 / Start with any one of these input types.

```powershell
# ISO
python tools/play.py "D:\sources\Rich Diamond.ISO"

# 正式游戏目录，无需额外 ISO / Full-game directory: no additional ISO
python tools/play.py "D:\Games\Rich Diamond"

# 匹配基准的演示目录 / Matching reference demo directory
python tools/play.py "D:\Games\Rich Diamond Demo"
```

打开 [http://127.0.0.1:8770](http://127.0.0.1:8770)。启动命令自动识别输入并准备独立运行缓存，不修改原始数据。按 Ctrl+C 停止；可用 `--port 8780` 改端口、`--cache D:\OpenRD-local` 改缓存目录。

Open [http://127.0.0.1:8770](http://127.0.0.1:8770). The launcher detects your input and prepares an isolated runtime cache without changing the source data. Stop it with Ctrl+C. Use `--port 8780` to change the port or `--cache D:\OpenRD-local` to choose a cache directory.

历史安装包可仅导入资源；这不会开放原版试玩范围未知的关卡。 / Historical installers may be imported as resources only; this does not unlock levels whose native demo scope is unknown.

```powershell
python tools/import_source.py "D:\Downloads\rddemosmall.exe" --output "D:\imports\demo" --seven-zip "C:\Program Files\7-Zip\7z.exe" --unshield "D:\tools\unshield.exe"
```

## 无参数启动与工具准备 / Default launch and extraction tools

准备好 Python 并把合法游戏数据放入 `game` 后，Windows 可双击项目根目录的 `play.cmd`，也可双击关联到 Python 的 `play.py`。终端运行 `python play.py` 或 `python tools/play.py` 不带参数时，走同一套自动选择、工具准备、空闲端口探测和打开浏览器流程。运行目录由程序位置确定，不依赖当前工作目录。出错时 `play.cmd` 会保留窗口显示原因。

Once Python is installed and your lawful game data is in `game`, double-click `play.cmd` on Windows, or `play.py` if Python file associations are configured. Running `python play.py` or `python tools/play.py` without arguments uses the same input-selection, tool-resolution, free-port and browser-launch flow. Paths are relative to the project, not your current working directory. `play.cmd` keeps the error message visible if startup fails.

未指定端口时，从 **8770** 开始探测，占用或不可用则依次尝试 8771、8772……直到找到空闲端口。明确传入 `--port` 时不自动换端口；端口占用会报错。以终端打印的实际地址为准。

Without `--port`, the launcher probes from **8770**, incrementing until it finds an available port. An explicitly supplied port is fixed and produces an error if occupied. Use the actual URL printed by the launcher.

只在遇到 InstallShield 格式时调用 unshield；基准 ISO、已安装基准目录和不需要 InstallShield 的包不会调用它。程序先查 `--unshield`、`OPENRD_UNSHIELD`、PATH 和本地工具目录。缺少时显示下载来源；Windows 默认从 [Scoop 的 unshield 包](https://github.com/ScoopInstaller/Main/blob/master/bucket/unshield.json) 自动下载对应架构的 1.6.2，核对固定 SHA-256 后用 7-Zip 解包，保留所需 DLL。工具放在 `local-tools`，不修改系统 PATH，也不随源码提交。

unshield is invoked only for InstallShield formats, not reference ISOs, matching installed directories or packages that do not require it. The launcher checks `--unshield`, `OPENRD_UNSHIELD`, PATH and local tool directories. If missing, it displays the download source. On Windows it automatically obtains the matching 1.6.2 architecture from [Scoop's unshield package](https://github.com/ScoopInstaller/Main/blob/master/bucket/unshield.json), verifies a pinned SHA-256 and extracts it using 7-Zip, retaining required DLLs. Tools stay in `local-tools`; system PATH and the source repository are unchanged.

`--no-download-tools` 可禁用自动下载；仍可用 `--unshield` 指定已有工具。下载或校验失败会明确提示手动下载，不执行未校验文件。Linux 等系统请通过系统包管理器安装 unshield。7-Zip 仍需预先安装，程序会识别 Windows 常见安装位置。

Use `--no-download-tools` to disable downloads, or `--unshield` to specify your installed tool. Download/checksum failures display manual-download guidance, and unverified files are not executed. On Linux, install unshield through your OS package manager. 7-Zip must already be installed; its common Windows installation path is detected automatically.

解包工具可用不代表关卡获得授权：原版试玩范围未知的内容仍然拒绝游玩。

Availability of extraction tools does not grant level access: unverified native demo scopes remain blocked.

## 自动打开浏览器与局域网 / Browser launch and LAN play

默认仅监听本机 `127.0.0.1`。服务准备完成后自动打开系统默认浏览器；`--no-browser` 禁用自动打开。`--prepare-only` 只准备数据，不启动服务或浏览器。Ctrl+C 会退出并释放端口。

By default, the server listens on `127.0.0.1` and opens your default browser once ready. Use `--no-browser` to disable this. `--prepare-only` prepares data without starting a server or browser. Ctrl+C stops the service and releases its port.

同一局域网的其他设备游玩时，使用 `--host 0.0.0.0`。主机浏览器仍打开本地地址，其他设备访问主机实际局域网 IP；不要访问 `0.0.0.0`。

For other devices on the same LAN, use `--host 0.0.0.0`. The host browser opens the local address; other devices use the host's actual LAN IP, not `0.0.0.0`.

```powershell
python tools/play.py "D:\Games\Rich Diamond Demo" --host 0.0.0.0 --port 8780
# 手机访问示例 / Phone URL example: http://192.168.1.50:8780
```

默认信任回环地址及系统解析出的本机名称/IP。`--trusted-hosts`（别名 `--trustedhosts`）可明确列出允许的访问名称/IP，逗号分隔，不含协议、端口或通配符。回环地址始终保留。它校验 HTTP Host，不是客户端 IP 白名单；跨来源请求也会被拒绝。

Defaults trust loopback and the machine's locally resolved hostname/IPs. `--trusted-hosts` (alias `--trustedhosts`) accepts comma-separated exact hostnames/IPs without scheme, port or wildcard. Loopback remains allowed. This validates HTTP Host, rather than the client's IP; cross-origin requests are also rejected.

```powershell
python tools/play.py "D:\Games\Rich Diamond Demo" --host 0.0.0.0 --port 8780 --trusted-hosts "192.168.1.50,my-pc" --no-browser
```

把示例 IP 换成主机实际局域网 IPv4 地址（Windows 可运行 `ipconfig` 查看）。设备需在同一网络；无法连接时检查 Windows 防火墙是否允许 Python 在私有网络接收连接。程序不自动修改防火墙。不要直接暴露公网：当前接口不提供网络登录或 TLS。

Replace the example IP with the host's LAN IPv4 address (`ipconfig` on Windows). Devices must share the network. If connection fails, check whether Windows Firewall allows Python on private networks. The launcher does not change firewall settings. Do not expose it directly to the internet: it provides no network authentication or TLS.

局域网与 trusted hosts 设置不会开放原版试玩范围未知的关卡。

LAN and trusted-host settings do not unlock sources whose native demo scope is unverified.

## 输入与运行范围 / Input support and limits

| 输入 / Input | 运行方式与内容 / Content and behavior |
| --- | --- |
| 已验证的原 ISO / Verified reference ISO | 基准 Game/Web，80 正式关＋5 演示关、存档及排行榜。 / Baseline Game/Web with 80 full-game levels, 5 demos, saves and rankings. |
| 匹配基准的正式游戏目录 / Matching full-game directory | 相同 Game/Web；没有 DEMO.LVS 时只加载正式关。 / The same Game/Web; missing demo levels are not invented. |
| 匹配基准的仅演示目录 / Matching demo-only directory | 只加载所提供的演示关。 / Only the supplied demo levels are loaded. |
| 其他已支持的正式目录或试玩数据 / Other supported full-game or demo data | 可导入资源；原版试玩/授权范围未核实，关卡暂不开放。 / Resource import only; native demo/licensed scope is unverified, so levels are blocked. |
| 已导入的 framework/bundle.json 目录 / Imported framework/bundle.json directory | 重新应用访问限制，旧目录不豁免。 / Access policy is reapplied; older imported directories are not exempt. |

目录应保留游戏自身的数据文件。基准目录通常含 `CCENG.EXE`、`RICHDIMD.BYT`、`RICHDIMD.GIN`、`ICONS.PCX` 及至少一个 LVS 文件；其他已支持目录由导入工具自动识别。不同发行版同名资源按来源隔离。缺失文件、未知格式或不支持的格子明确报错或禁用。

Keep the game's data files together. Reference directories normally contain `CCENG.EXE`, `RICHDIMD.BYT`, `RICHDIMD.GIN`, `ICONS.PCX` and at least one LVS file. Other supported directories are detected automatically. Same-named resources are isolated by source. Missing files, unknown formats and unsupported tiles are reported or disabled explicitly.

试玩数据只能提供原版明确允许试玩的内容，不能仅凭安装包中包含地图开放关卡。当前可解析两版 1999 发行版、v1.7 部分地图，以及 2.0、2003 和 2.21 资源。早期 CCIg11 画面仍较基础；v1.7 存在缺失 GIN 和未知格子的限制。来源模式的结束状态遵循框架约定，不是原版结束界面的等价认证。

Demos may expose only their verified native playable scope; bundled maps are not an access grant. Current format coverage includes two 1999 releases, partial v1.7 maps, and 2.0, 2003 and 2.21 resources. Early CCIg11 rendering remains basic; v1.7 has missing-GIN and unsupported-tile limitations. Source-mode completion screens follow framework behavior and are not certified reproductions of native end screens.

生成数据默认位于 `imports/runs`，被 Git 忽略。基准存档按输入内容隔离，不覆盖原游戏文件或已有玩家数据。音乐/MIDI 和视频转换是可选步骤；未提供转换音乐时不会请求不存在的文件。纯源码仓库不能提供用户输入中缺失的关卡。

Generated data defaults to `imports/runs` and is Git-ignored. Baseline saves are isolated by input content, preserving source files and existing player data. Music/MIDI and video conversion are optional; missing converted music is not requested. The source repository cannot provide levels absent from your own input.

## 操作与语言 / Controls and language

PC 单击目的地即可行动。手机先选中目的地，再点击同一格行动；拖动或重开会清除选择。“方向高亮”显示人物同行/同列的边框，PC 首次默认关闭，移动端首次默认开启，并保存选择。高亮不预测通行或推物结果。

On PC, click a destination once to move. On mobile, select a destination and tap the same tile again; dragging or restarting clears the selection. Direction highlights mark the player's row and column. They default to off on PC and on for mobile, with your choice saved locally. Highlights do not predict passability or pushes.

标题页、游戏控件和来源资源页面支持中文与 English。首次语言由浏览器语言决定，后续优先使用保存的选择；切换语言不重开关卡、不改变游戏状态。原始关卡名称保留数据中的名称。

The title screen, game controls and source-resource pages support Chinese and English. Browser language determines the initial default; your saved preference takes priority. Switching language does not reset a level or change game state. Original level names remain as supplied by the data.

匹配基准的输入支持本地存档与排行榜；原版试玩/授权范围未核实的来源暂不开放关卡。这是兼容性重实现，尚不保证所有发行版、每个关卡或原版画面与时序完全等价。不支持的输入会明确报错。

Matching baseline inputs support local saves and rankings. Sources whose native demo/licensed access scope is unverified are blocked. This compatibility reimplementation does not guarantee equivalence for every release, level, pixel or original timing. Unsupported inputs produce explicit errors.



## 来源动画 / Source animations

`python play.py "D:\games\RDDEMO.exe" --mode animation`

原始动作帧与位移、主题选择及限制见[来源动画](SOURCE_ANIMATIONS.md)。未知试玩范围的来源只开放素材动画查看。

See [source animations](SOURCE_ANIMATIONS.md) for frames, motion and themes. Unverified trial sources expose asset animations only.


First-five trial update (2026-10-23): see [source animations](SOURCE_ANIMATIONS.md).


First-five trial update (2026-10-23): see [source animations](SOURCE_ANIMATIONS.md).
