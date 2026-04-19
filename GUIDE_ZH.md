# Mobile Agent 中文详细教程

这份教程面向三类人：

- 想先把项目跑起来的人
- 想把项目整理后发布到 GitHub 的人
- 想在电脑端用一个界面输入文字任务再执行的人

本文默认你在 Windows 上使用 Android Studio Emulator，并且项目目录是：

```text
F:\mobile agents
```

## 1. 项目现在能做什么

当前这个项目不是“无限制的全自动手机代理”，而是一个有边界、可测试、可调试的 Android GUI Agent。

它现在主要支持这些能力：

- 通过 ADB 驱动模拟器
- 读取当前前台页面的 UI 信息
- 按任务类型走不同的 bounded flow
- 在 `guided_ui_task` 模式下做有限步交互
- 使用 SQLite memory 记录成功轨迹、失败模式和稳定 UI shortcut
- 使用“本地 text + 云端读屏 + rule/shortcut fallback”混合策略

最近已经补上的重点能力包括：

- 本地 `Qwen3.5-0.8B` 作为轻量 text reasoner
- 云端 Qwen API 负责截图理解
- 本地 text 超时后，本轮后续步骤自动跳过本地推理
- 常见稳定动作会被写入 memory，后续直接走 `memory_rule`

## 2. 建议的目录理解

项目里最重要的目录和文件如下：

```text
app/
  main.py                 统一 CLI 入口
  desktop_ui.py           新增的电脑端图形界面入口
  executor.py             执行器
  page_reasoner.py        页面推理层
  reasoning_orchestrator.py
  memory.py               SQLite memory 与 UI shortcut
tests/
  各模块单元测试
data/
  logs/                   运行日志
  screenshots/            截图
  memory.db               运行后生成的记忆库
GUIDE_ZH.md               本中文教程
```

## 3. 环境准备

### 3.1 Python

建议使用 Python 3.10 或以上。

创建虚拟环境并安装依赖：

```powershell
cd F:\mobile agents
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 3.2 Android Studio 与 Emulator

你需要：

- 已安装 Android Studio
- 已创建一个 AVD
- 模拟器可以正常启动
- `adb devices` 能看到设备

如果命令行里 `adb` 不可用，优先检查这两个目录：

```text
C:\Users\zhufe\AppData\Local\Android\Sdk\platform-tools
C:\Users\zhufe\AppData\Local\Android\Sdk\emulator
```

### 3.3 ADB 连通性检查

先不要急着跑 agent，先单独确认设备：

```powershell
& "C:\Users\zhufe\AppData\Local\Android\Sdk\platform-tools\adb.exe" devices -l
```

理想输出类似：

```text
List of devices attached
emulator-5554 device product:sdk_gphone64_x86_64 ...
```

如果这里是空的，说明问题还在模拟器层，不在 agent 层。

## 4. 模型与推理建议

你现在这套项目更推荐的运行方式是：

- 本地：`Qwen/Qwen3.5-0.8B`
- 云端：Qwen API 负责 screenshot / screen understanding
- 本地 VL：关闭

推荐环境变量：

```powershell
$env:LOCAL_TEXT_REASONER_BASE_URL="http://127.0.0.1:9000/v1"
$env:LOCAL_TEXT_REASONER_MODEL="Qwen/Qwen3.5-0.8B"
$env:DASHSCOPE_API_KEY="你的云端 Key"
$env:REASONING_ENABLE_LOCAL_VL="0"
$env:REASONING_DISABLE_LOCAL_TEXT_AFTER_FAILURE="1"
$env:REASONING_REQUEST_TIMEOUT_SECONDS="30"
```

这组配置的含义是：

- 先尝试本地小模型
- 如果本地首轮就超时，本轮后续直接跳过本地 text
- 让云端 Qwen 接管读屏
- 避免本地 VL 再拖慢速度

## 5. 最常用的 CLI 跑法

### 5.1 读当前页面

```powershell
python -m app.main --task "read the current screen and summarize it" --task-type read_current_screen --reasoner-backend stack --agent-mode interactive --max-steps 1 --auto-confirm
```

### 5.2 打开 Keep 并创建 note

```powershell
python -m app.main --task "open keep and create a note" --task-type guided_ui_task --reasoner-backend stack --agent-mode interactive --max-steps 3 --auto-confirm
```

### 5.3 打开 Keep、创建 note、输入文字

```powershell
python -m app.main --task "open keep and create a note, then type 'hello from desktop ui'" --task-type guided_ui_task --reasoner-backend stack --agent-mode interactive --max-steps 5 --auto-confirm
```

### 5.4 只看 route 和 plan，不真正执行

```powershell
python -m app.main --task "open keep and create a note" --task-type guided_ui_task --reasoner-backend stack --dry-run
```

## 6. 新增电脑端界面怎么用

现在已经加了一个桌面端界面，入口是：

```powershell
python -m app.desktop_ui
```

### 6.1 界面能做什么

界面支持你直接在电脑上输入自然语言任务，然后点击按钮执行。

主要字段包括：

- `Task`
  输入自然语言任务，例如：
  `open keep and create a note, then type 'hello from desktop ui'`
- `Device ID`
  可选。如果你只有一个模拟器，可以留空
- `Task Type`
  可选。不会时留空，让系统自动判断；如果你很确定，也可以手动选
- `Planner Backend`
  一般保持 `rule`
- `Reasoner Backend`
  推荐 `stack`
- `Agent Mode`
  一般留空，让系统自动选；`guided_ui_task` 推荐 interactive
- `Max Steps`
  限制交互轮数，避免一直循环
- `Dry Run`
  只规划，不执行
- `Auto Confirm`
  自动跳过某些确认

### 6.2 推荐的界面使用姿势

第一次使用时，建议按这个顺序：

1. 先打开模拟器，确认 `adb devices -l` 能看到设备。
2. 先在界面里勾选 `Dry Run` 跑一遍。
3. 看输出 JSON 是否合理。
4. 再取消 `Dry Run` 跑真实动作。

### 6.3 执行结果在哪里看

界面下方会显示完整 JSON 输出。

同时，项目也会继续写这些文件：

- 日志：`data/logs/agent.log`
- 截图：`data/screenshots/...`
- memory：`data/memory.db`

## 7. memory 和 shortcut 是怎么加速的

这是当前项目里最实用的一层优化。

### 7.1 以前为什么慢

以前每轮都要：

1. `read_screen`
2. 本地 `0.8B` 尝试推理
3. 本地超时
4. 云端读屏
5. 再决定下一步

所以简单动作也会花掉很多时间。

### 7.2 现在 shortcut 的工作方式

如果某个动作满足下面条件：

- 出现在稳定页面上
- 是有限技能里的动作
- 之前已经被成功执行过
- 当前页还能看到对应目标

那么系统会把它写进 `ui_shortcuts`。

下次再遇到同样的：

- `goal`
- `page`
- `task_type`

就优先直接命中 `memory_rule`，不先走模型。

### 7.3 这类动作最适合做 shortcut

例如：

- `keep_home -> Create a note`
- `messages_home -> Search`
- `keep_fab_menu -> Text`

### 7.4 哪类动作不应该完全 shortcut 化

例如：

- 当前页面变化很大
- 输入内容强依赖上下文
- 风险高
- 任务跨多个 app，且中间容易被干扰

这种还是更适合保留云端读屏或重新推理。

## 8. 如果中间被打扰怎么办

真实执行时，最怕这些干扰：

- 你手动点了模拟器
- 弹窗把前台页面盖住
- 系统通知把焦点抢走
- app 没在预期页面

建议：

1. 跑任务时不要手动碰模拟器。
2. 先做短任务，不要一口气做太长链路。
3. 每次任务尽量从 app 的稳定首页开始。
4. 对频繁使用的任务，多跑几次，让 memory 累积 shortcut。

## 9. 发布到 GitHub 前，建议你先做这些整理

虽然你现在目录还不是 git 仓库，但发布前可以先按这个 checklist 走。

### 9.1 确认不要上传的内容

不要把这些推上去：

- 真实 API key
- `data/logs/`
- `data/screenshots/`
- `data/tmp/`
- `tmp/`
- 本地数据库里的私人数据

当前 `.gitignore` 已经忽略了大部分运行产物，但你还是要手动确认：

- 没把 key 写死进源码
- 没把个人截图、私人联系人、真实日志混进去

### 9.2 建议保留的内容

建议上传：

- `app/`
- `tests/`
- `requirements.txt`
- `README.md`
- `GUIDE_ZH.md`

### 9.3 如果你现在还是裸目录

先初始化 git：

```powershell
cd F:\mobile agents
git init
git add .
git commit -m "Initial mobile agent MVP with desktop UI and Chinese guide"
```

### 9.4 如果你想直接建 GitHub 仓库

如果你已经装了 GitHub CLI：

```powershell
gh auth login
gh repo create mobile-agents --private --source . --remote origin --push
```

如果你不用 `gh`，也可以手动在 GitHub 网页建仓库，然后：

```powershell
git remote add origin https://github.com/<your-name>/<repo-name>.git
git branch -M main
git push -u origin main
```

### 9.5 推送前最后自检

建议最后跑：

```powershell
python -m unittest discover -s tests -v
python -m compileall app tests
```

## 10. 你现在最推荐的对外展示方式

如果你准备把这个项目放到 GitHub，我建议你对外这样描述：

- 它是一个 emulator-first 的 Android GUI Agent MVP
- 重点是 bounded execution，不是无限制 autonomous agent
- 有 memory shortcut、hybrid reasoning、desktop UI
- 强调可测试、可调试、可维护

这个定位会比“万能手机智能体”更真实，也更容易获得正反馈。

## 11. 常见故障排查

### 11.1 `No ready adb device was found within 30s`

说明设备没连上，不是 agent 本身崩了。

先查：

```powershell
& "C:\Users\zhufe\AppData\Local\Android\Sdk\platform-tools\adb.exe" devices -l
```

### 11.2 模拟器打不开

你之前这个 AVD 已经抓到过一类真实错误：

- Vulkan / SwiftShader 图形设备创建失败

推荐试法：

```powershell
& "C:\Users\zhufe\AppData\Local\Android\Sdk\emulator\emulator.exe" -avd Pixel_10_Pro -gpu host -no-snapshot-load
```

如果不行，再试：

```powershell
& "C:\Users\zhufe\AppData\Local\Android\Sdk\emulator\emulator.exe" -avd Pixel_10_Pro -gpu angle_indirect -no-snapshot-load
```

并建议在 `config.ini` 里把：

```ini
fastboot.forceFastBoot=no
fastboot.forceColdBoot=yes
hw.gpu.mode=host
```

### 11.3 本地 0.8B 很慢

这是正常现象。

建议：

- 保留本地 0.8B 作为 first try
- 开启 `REASONING_DISABLE_LOCAL_TEXT_AFTER_FAILURE=1`
- 把真正看屏幕的工作交给云端
- 让 shortcut 接管稳定动作

### 11.4 界面点了没反应

先排查：

- 模拟器是否真的启动了
- ADB 是否能看到设备
- 是否忘了设置云端 key
- 输出面板里有没有 traceback

## 12. 推荐的日常工作流

如果你以后自己维护这个项目，我建议这个顺序最省心：

1. 开模拟器
2. 确认 `adb devices`
3. 开本地 0.8B 服务
4. 设置 DashScope/Qwen API key
5. 先用桌面界面 `Dry Run`
6. 再做真实执行
7. 跑稳定任务，积累 shortcut
8. 再逐步扩复杂任务

## 13. 一组你可以直接复制的命令

### 启动桌面界面

```powershell
cd F:\mobile agents
.venv\Scripts\activate
python -m app.desktop_ui
```

### 启动命令行任务

```powershell
python -m app.main --task "open keep and create a note, then type 'hello from desktop ui'" --task-type guided_ui_task --reasoner-backend stack --agent-mode interactive --max-steps 5 --auto-confirm
```

### 跑单元测试

```powershell
python -m unittest discover -s tests -v
```

---

如果你后面还要继续扩，我建议优先做这三件事：

- 同屏缓存 cloud decision
- 给 Keep / Messages / Settings 做更稳定的页面宏
- 做一个“任务开始前回到稳定首页”的 preflight
