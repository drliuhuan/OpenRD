# 来源动画 / Source animations

已接入本地试玩数据的 GIN 动作状态、连续精灵与位移；新版主题动作使用该来源自己的 IMC 运动链。v1.7 安装包中的内嵌 GIN 也会自动提取。需要重新导入旧的 v1.7 输出目录。

Source animation playback now uses the input's own GIN states, sprite frames and offsets. Modern theme actions use that source's IMC motion chains. Embedded v1.7 GIN is extracted automatically; reimport old v1.7 outputs.

## 查看安装包中的动画 / Inspect source animations

```powershell
python play.py "D:\games\RDDEMO.exe" --mode animation
```

使用已有导入目录 / With an existing import:

```powershell
python tools/source_playtest.py "D:\imports\demo" --port 8770
```

选择动画对象、动作和资源主题，点击“播放动画”。新版默认选择真实主题；GIN 基础素材仅提供部分动作的静态回退。来源文件不会被执行或修改。解包使用 7-Zip；InstallShield 还需要 unshield，统一启动器可以按已有规则下载并验证工具。

Select an object, action and theme, then Play. Modern sources default to a real theme; base GIN graphics have static fallbacks for some actions. Source programs are never executed or modified. Extraction uses 7-Zip and, for InstallShield, unshield; the unified launcher can download and verify the required tool.

未知试玩范围的包只开放素材动画查看，关卡仍关闭；这个选项不会开放正式地图、注册功能或更多试玩关卡。已确认基准 ISO／正式目录／五关演示目录仍按原命令游玩。

Sources with unverified trial scope expose asset animations only; levels remain closed. This option does not unlock full-game maps, registration features or extra demo levels. Verified reference ISO, full-game folders and five-level demo folders use the usual play command.

## 已修复与边界 / Changes and limits

- 每个角色使用独立游标和动作状态，不再靠全局时间取模猜动作帧。GIN next/wait 与主题运动节点保留原始顺序、数量和有符号位移，不按另一版本的帧数插值。
- 来源点击处理已能生成完整播放批次，浏览器按时间显示中间帧；渲染接口不推进游戏逻辑，过期播放 ID 和越界帧被拒绝。
- 早期 PCX 使用实际精灵矩形、原点和整组绘制分量；不再只画首个分量。新版保留实际 RGB、效果表与主题命名空间。
- Each actor has its own cursor and action state. GIN next/wait and theme motion nodes preserve source order, count and signed offsets without cross-version interpolation.
- Source click processing produces intermediate playback frames. Rendering is read-only; stale playback IDs and out-of-range frames are rejected.
- Legacy PCX uses actual rectangles, origins and all draw components. Modern RGB, effect tables and theme namespaces are retained.

当前播放显示采用 40ms 间隔，可因绘制速度跳过显示帧；这不等于已证明每个原版的真实耗时。随机初始姿态采用确定分支，不代表原生随机数序列。旧版特殊阴影／设备调色、所有来源的自然死亡门控、完整背景过渡与最终窗口像素仍未全部认证。动画可运行不等于整个发行版原生等价。

Presentation currently uses 40ms ticks and may skip displayed frames when rendering falls behind. Native wall-clock timing for every release is not certified. Initial random poses use a deterministic branch rather than the original RNG sequence. Legacy special shadows/device palette behaviour, all source death gates, complete background transitions and final window pixels remain outside complete certification. Working animations do not establish full native-release equivalence.
