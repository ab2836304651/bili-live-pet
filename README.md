# 🐰 B站直播弹幕桌宠插件（bili-live-pet）

监听你的直播间弹幕/礼物/SC/大航海，由 **DeepSeek AI** 以可自定义的提示词风格实时回复，
回复显示在桌面上的透明桌宠气泡里（内置动画兔团子，支持替换透明 GIF）。

> 适合搭配 **哔哩哔哩直播姬** 使用：直播时开着桌宠，观众弹幕会被 AI 兔团子逐一回应。

---

## ✨ 功能

- **弹幕接入（双后端，模块化）**
  - `open_live`（推荐）：哔哩哔哩**直播开放平台官方** WebSocket 接口，稳定合规；
  - `community`（备选）：社区协议接口。**2026-08 起 B站已封禁匿名查看弹幕**（匿名连接
    只回 LOG_IN_NOTICE，收不到任何弹幕），需在 config.yaml 填登录 Cookie（SESSDATA）后使用；
    冷清房间几分钟才有一条弹幕属正常。
- **AI 回复**
  - 接入 **DeepSeek 官方 API**（`api.deepseek.com`），API Key 在设置面板里自填；
  - 提示词在设置面板「提示词」页自由编辑，定义**回复方式与风格**；
  - 支持 全部回复 / 触发词 / 概率 三种策略，带冷却防刷屏、上下文记忆。
- **桌宠展示**
  - 透明无边框、置顶、可拖动；内置矢量圆耳兔头（呼吸/眨眼/圆耳抖动/说话张嘴），可选 CC0 GIF；
  - 回复时切到蹦跳动画，气泡显示弹幕/礼物/SC；
  - 弹幕/礼物/SC 会以对话气泡形式显示。
  - **外观可调**：兔团子大小、气泡字体大小、**脸大小**（头缩小、五官不变，Q版萌感；设置面板「外观」页，保存即生效）；
  - **回复开关**：弹幕 / 礼物 / SC / 大航海可单独开关（设置面板「AI 回复」页）。
- **桌宠互动（纯本地，不耗 AI）**
  - 单击戳一下（脸红竖耳），双击蹦跳 + 卖萌气泡；
  - 右键菜单「🤚 摸摸头」：撒娇气泡 + 轻蹦；
  - 没人在的时候会自己偶尔蹦一下、冒个泡（每 20~40 秒随机）。

---

## 🚀 快速开始

**普通用户（exe 版，推荐送人）：**
1. 到 [Releases](https://github.com/ab2836304651/bili-live-pet/releases) 下载最新版压缩包，解压；
2. 双击里面的 `兔团子桌宠.exe`；
3. 首次启动自动弹出【设置面板】：
   - 填**直播间房间号**（直播间网址后面的数字）
   - 填 **API Key**（https://platform.deepseek.com 注册 → API Keys → 创建）
   - 点 **📱 扫码登录**，手机 B 站 App 扫码确认（不登录收不到弹幕）
4. 点保存，兔团子出现在屏幕右下角，开播即用。

> 之后右键兔团子 →「⚙️ 设置」可随时改房间号 / API / 提示词 / **兔团子大小** / **气泡字体大小** /
> **脸大小** / **回复哪些事件**（弹幕/礼物/SC/大航海，勾选即可）；B站登录态约 30 天过期，重新扫码即可。
> 闲时还可以戳戳兔团子：单击、双击、右键摸头都有反应。
> 不需要安装 Python。

**开发者（源码版）：**
```bash
git clone https://github.com/ab2836304651/bili-live-pet.git
cd bili-live-pet
python -m venv .venv
.venv/Scripts/pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
copy config\config.example.yaml config\config.yaml   # 复制配置模板并填写
./start.sh            # Windows 双击 start.bat
```

> 仓库不含任何凭据：`config/config.yaml` 已被 `.gitignore` 排除，模板见 `config/config.example.yaml`。

**可选自检：**
```bash
.venv/Scripts/python tools/test_ai.py                          # 验证 AI 连接
.venv/Scripts/python tools/test_danmaku.py --room 房间号       # 验证弹幕
```

启动后：兔团子出现在屏幕右下角，可左键拖动；右键菜单可「🐾 测试回复一句」「🎯 设置直播间号…」「⚙️ 设置」「退出」。

---

## 🎁 作为礼物送给别的主播

把 `dist\兔团子桌宠\` 整个文件夹（或压缩包）发给对方即可，**无需安装任何东西**：

1. 对方双击 `兔团子桌宠.exe`，首次自动弹出设置面板；
2. 填自己的**房间号**和 **DeepSeek API Key**（对方自备）；
3. 点**扫码登录**（手机 B 站 App 扫码，自动填好 B站登录态，必做）；
4. 想改桌宠性格就在面板「提示词」页改，保存即生效。

> 项目不内置任何人的 API Key / 登录凭据，天然适合分发。

## 🔑 第一步：申请 Open Live 开放平台凭据（一次性）

社区协议 2026 年起已被官方封禁匿名弹幕，因此**建议走官方通道**：

1. 打开 https://open-live.bilibili.com 并用你的 B 站账号登录；
2. **创建应用**（类型选「消息接收服务」），记录下：
   - 应用 ID（`app_id`）
   - `AccessKeyId`
   - `AccessKeySecret`
3. 在应用设置里**绑定你的直播间房间号**（主播授权）；
4. 在应用管理页获取**连接码**（`code`）；
5. 把这四项填进 `config/config.yaml` → `danmaku.open_live`。

> 每次开播前，直播姬正常开播即可；桌宠通过官方接口接收弹幕，
> 无需额外登录 Cookie，也不会与直播姬冲突。

---

## ⚙️ 配置说明（config/config.yaml）

| 字段 | 说明 |
|---|---|
| `room_id` | 你的直播间房间号（设置面板填写，必填） |
| `danmaku.backend` | `open_live` / `community`（默认；community 需 SESSDATA 登录） |
| `danmaku.community.sessdata` | B站登录态（设置面板扫码自动写入，约 30 天有效） |
| `ai.api_key` | DeepSeek API Key（已预填你的 Key，实测可用） |
| `ai.model` | `deepseek-chat` / `deepseek-v4-flash` / `deepseek-v4-pro` |
| `ai.reply_mode` | `all` / `trigger` / `probability` |
| `ai.trigger_words` | trigger 模式下的触发词 |
| `ai.cooldown_seconds` | 回复冷却（防刷屏） |
| `ai.max_history` | AI 上下文记忆条数 |
| `pet.gif` | 留空=内置猫；填 `assets/xxx.gif` 用透明 GIF |
| `pet.position` | 窗口坐标，留空=屏幕右下角 |

**风格定制**：直接编辑 `config/prompt.md`（人设、语气、称呼、示例全在这里），改完重启生效。

---

## 🎨 关于贴图与资源（需求原则 3 落实）

**当前默认形象：内置矢量圆耳兔头**（`pet/builtin_bunny.py`，纯 Qt 自绘，无版权问题、离线可用）

- 只画圆圆的兔头 + 两只圆耳朵（圆耳短萌风），不依赖任何外部图片；
- 动画：呼吸、眨眼、圆耳轻摆+偶尔抖动、说话时竖耳张嘴、腮红加深；
- 想微调外观（大小/颜色/耳朵位置）直接改 `pet/builtin_bunny.py` 顶部参数即可。

**可选 GIF 形象（CC0 素材）**：OGA「Mascot Bunny Character」by **Sashim**（CC0），
原始帧目录在 `assets/mascot_bunny/`，已生成的 `assets/pet_idle.gif` / `assets/pet_talk.gif`
可在 `config.yaml` 的 `pet.gif` / `pet.talk_gif` 填路径启用（平时待机、回复时跳跃）。

**自定义形象**：透明 GIF 放入 `assets/`，在 `pet.gif`（+可选 `pet.talk_gif`）填路径即可。
透明 GIF 可在以下 CC0/免费可商用渠道获取（国内一般可直连）：
- opengameart.org（CC0 精灵/动画）
- pixabay.com（筛选"免费商用/无需署名"的动图）
- kenney.nl（CC0 素材库）

> 备注：我们已对比过 OGA 上 20 款兔兔素材（预览总览图在 `docs/options/contact_sheet.png`），
> 最终选择了自绘方案；若想换素材随时可以从里面挑。

---

## 🗂️ 模块结构（便于按需删改）

```
bili-live-pet/
├── main.py                  # 入口：装配窗口 + 控制器 + 首启引导
├── build.bat                # PyInstaller 打包脚本（产出 dist\兔团子桌宠\）
├── config/
│   ├── config.yaml          # 配置（设置面板自动读写）
│   └── prompt.md            # AI 人设（设置面板「提示词」页编辑）
├── core/
│   ├── events.py            # 统一事件模型（弹幕/礼物/SC/进场…）
│   └── log.py               # 安全日志（打包无控制台时静默）
├── danmaku/
│   ├── packets.py           # B站二进制协议编解码（两后端共用）
│   ├── base.py              # 监听器抽象基类
│   ├── open_live.py         # 官方 Open Live 后端（推荐）
│   ├── community.py         # 社区协议后端（默认，需 SESSDATA 登录）
│   └── factory.py           # 按配置选择后端
├── ai/
│   ├── client.py            # DeepSeek 聊天客户端
│   └── responder.py         # 回复策略 + 提示词装配
├── pet/
│   ├── widget.py            # 透明置顶窗口 / 气泡 / 菜单
│   ├── settings_dialog.py   # 设置面板（房间/API/提示词）
│   ├── qrcode_login.py      # B站扫码登录弹窗
│   ├── sprite.py            # 贴图渲染器（GIF/内置兔）
│   ├── builtin_bunny.py     # 内置矢量圆耳兔头动画
│   └── controller.py        # 弹幕->AI->UI 编排（信号/线程）
├── tools/
│   ├── test_ai.py           # AI 连通性测试
│   ├── test_danmaku.py      # 弹幕后端独立测试
│   └── build_pet_gif.py     # 精灵表转 GIF 工具（可自行重生成贴图）
├── assets/                  # 贴图（rabbit_idle.gif 等，含 CC0 原始文件）
└── ...
```

---

## ❓ 常见问题

- **桌宠提示"30秒内没有收到弹幕"**：多半是房间冷清（冷清房间可能几分钟才一条弹幕），
  保持运行等待即可；若日志出现 `LOG_IN_NOTICE` 或"要求登录"提示，说明 B站登录态未填/失效，
  右键 → 设置 → 重新扫码登录。
- **AI 不回复**：先跑 `tools/test_ai.py` 看报错；检查 `api_key` 与网络；
  也确认 `cooldown_seconds` 没设太大、`reply_mode` 不是 `trigger` 而触发词不匹配。
- **桌宠显示为方块/不透明**：确认系统支持窗口透明（Windows 10/11 均可）；
  GIF 请使用透明背景。
- **直播姬与桌宠同开**：互不影响；桌宠只读弹幕，不发送任何内容到直播间。

> 免责声明：`community` 后端使用非官方接口，2026 年起 B 站已对相关开源项目
> 发出律师函并封禁匿名访问，仅供技术研究；正式直播请使用官方 `open_live` 后端。

---

## 📄 License

[MIT License](LICENSE) © 2026 [ab2836304651](https://github.com/ab2836304651)
