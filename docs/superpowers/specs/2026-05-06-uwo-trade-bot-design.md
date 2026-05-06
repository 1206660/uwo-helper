# UWO 跑商助手 —— 设计文档

- 创建日期：2026-05-06
- 状态：已与用户对齐，进入实现计划阶段
- 上一阶段：本文档替代 `Readme.md` 中"本地笔记本"定位的项目方向

## 0. 背景与方向变更

`Readme.md` 当前把项目定位为"本地航海笔记 + OCR 录入 + 收益计算"，并明确写明若干安全边界，包括：

- 不连接游戏服务器
- 不模拟登录、交易、航行或任务请求
- 不抓包、不还原协议
- 不读取或修改游戏进程内存
- **不自动点击游戏窗口**
- 不修改游戏文件

本次需求是把项目转向"自动化贸易跑商助手"，与第 5 条原则直接冲突。
经与用户确认：

1. 接受方向变更，`Readme.md` 将随实现一起改写。
2. 用户接受游戏 ToS 风险（中文私服）。
3. 本期不做端到端自动跑商；本期只交付"路线推荐大脑 + 可独立测试的输入/截图原语"，输入层与游戏业务**断开**。

## 1. 整体目标

| 项 | 决策 |
|---|---|
| 客户端 | UWO 中文私服，简体中文界面 |
| 平台 | Windows 10/11 桌面 |
| UI 框架 | PySide6（替换现有 Tkinter） |
| OCR | PaddleOCR（中文识别准确率优先） |
| 输入模式 | 后台 PostMessage 优先，依 M0 结果可降级到 SendInput / Loopback |
| 推荐指标 | 单件利润最大（`sell_price - buy_price`） |
| 推荐输入 | 仅用户自采的 OCR + 手录价格观察，不依赖外部静态资料 |
| 输入层范围 | 完整原语库 + UI 调试面板；**不接** `core/` 业务逻辑 |

非目标（本期不做）：

- 自动出港、航行、补给、海盗/风暴事件响应
- 单位时间净利润 / 总利润等更高级指标
- 任务、船厂、舰队管理
- 多语言客户端支持（仅简中）
- 外部资料库 / wiki API 接入
- Web UI、Tauri、Electron

## 2. 模块架构与目录

```
src/uwo_helper/
├── core/                       # 纯 Python 业务，无 UI、无平台依赖
│   ├── db.py                  # SQLite 连接、迁移、查询
│   ├── models.py              # PriceObservation, Port, Good 等 dataclass
│   ├── recommend.py           # 推荐算法（纯函数）
│   └── parse.py               # OCR 文本 -> 结构化记录
├── infra/                      # 平台/外部依赖隔离
│   ├── window.py              # Win32 窗口枚举、句柄查找
│   ├── input_lib.py           # PostMessage / SendInput / Loopback 后端
│   ├── screenshot.py          # mss 截图（全屏/区域/窗口）
│   └── ocr_engine.py          # PaddleOCR 包装
├── ui/                         # PySide6
│   ├── main_window.py
│   ├── pages/
│   │   ├── workbench.py       # 工作台（首页）
│   │   ├── price_book.py      # 价格簿（手录 + 列表）
│   │   ├── recommend.py       # 推荐表
│   │   ├── ocr_review.py      # OCR 校对入库
│   │   └── input_debug.py     # 输入调试面板（**禁止 import core**）
│   └── widgets/...
├── app.py                      # PySide6 入口
└── __main__.py
tests/
├── core/                       # parse / recommend / db 单测
└── infra/                      # input_lib loopback 集成测
docs/superpowers/specs/...      # 本文档及后续 plan
scripts/
├── run.bat / run.ps1           # 已有
└── spike_postmessage.py        # M0 一次性可行性脚本
```

### 关键边界

- `core/` 是纯函数式的：没有 UI 引用、没有 IO 之外的副作用、没有 PaddleOCR 依赖。最容易单测。
- `infra/` 把所有平台相关代码隔离：Win32 API、PaddleOCR 模型加载、mss 截图。换平台 / 换引擎只动这一层。
- `ui/` 只做事件路由 + 调用 core/infra，不放业务逻辑。
- `ui/pages/input_debug.py` 不能 `import core.*`（约定 + 必要时 import linter 强制）。这是把"输入能力"与"游戏业务"硬隔离的关键。
- 旧的 `app.py`、`hotkeys.py`、`screenshot.py`、`storage.py`、`ocr.py` 随 PySide6 迁移整体重写；旧逻辑里"截图保存命名"、"全局热键失败回退到窗口热键"等细节复用。

## 3. 交付路线（M0 → M3）

| 里程碑 | 内容 | 验证标准 |
|---|---|---|
| **M0** | `scripts/spike_postmessage.py`：枚举窗口 → 选记事本 → 发 WM_KEYDOWN/UP；选 UWO → 同样发；记录哪些消息被接收 | 我们能确切知道：UWO 私服客户端是否吃 PostMessage |
| **M1** | PySide6 主窗口 + SQLite + 手录价格 + 单件利润推荐表 | 不接 OCR、不接输入层，能录、能看到推荐 |
| **M2** | 截图（mss）+ PaddleOCR + 解析 + 校对入库 | 半自动录入价格 |
| **M3** | `input_lib` 三种后端 + 调试面板 | 能选窗口、发点击/键盘/热键，与游戏业务断开 |

每个里程碑都是可交付的：M1 哪怕 M2、M3 全失败也能用；M0 不通过则 M3 走降级方案。

## 4. 数据模型

```sql
CREATE TABLE ports (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL UNIQUE,
  region      TEXT,
  note        TEXT,
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE goods (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL UNIQUE,
  category    TEXT,
  note        TEXT,
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE price_observations (
  id           INTEGER PRIMARY KEY,
  port_id      INTEGER NOT NULL REFERENCES ports(id),
  good_id      INTEGER NOT NULL REFERENCES goods(id),
  buy_price    INTEGER,
  sell_price   INTEGER,
  stock        INTEGER,
  observed_at  TEXT NOT NULL,
  source       TEXT NOT NULL CHECK (source IN ('manual','ocr','import')),
  screenshot   TEXT,
  note         TEXT,
  created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_obs_good_observed ON price_observations(good_id, observed_at DESC);
CREATE INDEX idx_obs_port_observed ON price_observations(port_id, observed_at DESC);
```

设计决策：

1. **`price_observations` 是 append-only**。每次截图/手录都新增。保留历史、画趋势、辨真假。
2. **`buy_price` / `sell_price` 都可空**。同一商品在某港只能买或只能卖时，对应字段 NULL；推荐 join 时按可用方向过滤。
3. **`source` 字段**区分 manual / ocr / import。便于"只看人工确认过的"等过滤。
4. **不在 schema 里放 `confidence` / `raw_text` 等 OCR 中间态**。校对面板内存中持有，确认后只把最终值落表。
5. **不引入 ship / route 表**。本期"单件利润最大"指标不需要容量、航行时间。
6. **迁移机制**：`db.py` 维护 `SCHEMA_VERSION` 常量 + `migrations: list[str]`，启动时按版本号顺序跑剩下的。第一版只有 v1。

`core/models.py` 对应 dataclass：

```python
@dataclass(frozen=True)
class Port: id: int; name: str; region: str | None
@dataclass(frozen=True)
class Good: id: int; name: str; category: str | None
@dataclass(frozen=True)
class PriceObservation:
    id: int
    port: Port
    good: Good
    buy_price: int | None
    sell_price: int | None
    stock: int | None
    observed_at: datetime
    source: Literal["manual", "ocr", "import"]
    screenshot: str | None
    note: str | None
```

## 5. 推荐算法

### 接口

```python
@dataclass(frozen=True)
class RouteRecommendation:
    good: Good
    buy_port: Port
    sell_port: Port
    buy_price: int
    sell_price: int
    profit_per_unit: int
    buy_observed_at: datetime
    sell_observed_at: datetime

def recommend(
    observations: list[PriceObservation],
    *,
    now: datetime,
    max_age_hours: int = 24,
    top_n: int = 50,
    min_profit: int = 1,
    port_whitelist: set[int] | None = None,
    port_blacklist: set[int] | None = None,
) -> list[RouteRecommendation]: ...
```

`recommend` 是纯函数：不碰数据库、不碰文件、不碰系统时间（`now` 注入）。

### 算法

1. **时效过滤**：丢弃 `observed_at < now - max_age_hours` 的观察。
2. **去重取最新**：每个 `(port_id, good_id)` 只保留最新一条。
3. **白/黑名单过滤**：按 `port_whitelist` / `port_blacklist` 筛掉无关港口。
4. **按 `good_id` 分组**。
5. 对每个商品：
   - `buyable = [o for o in obs if o.buy_price is not None]`
   - `sellable = [o for o in obs if o.sell_price is not None]`
   - 至少需要 1 个 buyable + 1 个 sellable 且不在同一港 → 否则跳过
   - 选 `min(buyable.buy_price)` 作为 buy_port；`max(sellable.sell_price)` 作为 sell_port
   - 若两者撞同一港：分别构造两个候选——(次小买价 + 原 max 卖) 和 (原 min 买 + 次大卖价)；过滤掉两港相同或缺次优值的候选；剩下里取 `profit` 较大者；若两个都不存在则跳过该商品
   - `profit = sell_price - buy_price`；`< min_profit` 则跳过
6. 收集所有推荐，按 `profit_per_unit` 降序，截 `top_n`。

### 边界

- 不引入容量、航行时间、税。
- 同一港跨商品不被"buy_port == sell_port"检查误伤——该检查针对**同一推荐项内**的两个港。
- 无数据时返回 `[]`，UI 显示提示文案。
- 历史观察可能彼此矛盾：取最新；UI 提供"查看该 (港, 商品) 历史观察"侧面板。

### UI（推荐页）

主表（按 `profit_per_unit` 降序，列头可改排序）：

| 商品 | 买入港 | 买价 | 卖出港 | 卖价 | 单件利润 | 数据年龄 |
|---|---|---|---|---|---|---|

筛选控件：`数据有效期（小时）`、`最少利润`、`港口白名单`、`港口黑名单`。

选中行 → 折叠面板列出该 (买港, 卖港, 商品) 的所有观察 + 来源 + 关联截图链接。

## 6. 输入层

### M0 可行性脚本 `scripts/spike_postmessage.py`

独立脚本，不进 `src/`，跑完保留代码作为参考。目的：在写一行 `input_lib` 之前确认后台 PostMessage 对 UWO 私服客户端是否生效。

```python
# 伪代码
def list_windows(): ...
def post_keypress(hwnd, vk_code):
    win32api.PostMessage(hwnd, win32con.WM_KEYDOWN, vk_code, 0)
    time.sleep(0.05)
    win32api.PostMessage(hwnd, win32con.WM_KEYUP, vk_code, 0xC0000000)
def post_click(hwnd, x, y):
    lParam = (y << 16) | x
    win32api.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lParam)
    time.sleep(0.05)
    win32api.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lParam)
```

测试流程：

1. 对记事本：post 一串 `'A'` → 看是否显示
2. 对 UWO 窗口：post Esc → 看是否打开 / 关闭菜单
3. 对 UWO 窗口：post 客户区中心点击 → 看是否有反应

输出报告写进 `docs/superpowers/specs/2026-05-06-uwo-trade-bot-postmessage-spike.md`：

- 记事本 KEYDOWN/KEYUP：✅ / ❌
- UWO KEYDOWN/KEYUP：✅ / ❌
- UWO LBUTTONDOWN/UP：✅ / ❌
- 结论 + 后续 M3 走哪条路

### 三种结果对应的 M3 走法

| M0 结果 | 走法 |
|---|---|
| UWO 吃 PostMessage | `input_lib` 默认 `PostMessageBackend` |
| UWO 不吃 PostMessage 但前台 SendInput 可用 | 默认 `SendInputBackend`，调试面板加显眼"会接管键鼠"警告 |
| 都不吃（防作弊拦截 / DirectInput） | 暂停输入层开发；M3 仅放 `Backend` 抽象基类 + `LoopbackBackend`，硬件 USB HID 留接口 |

### `input_lib` 接口

```python
# infra/input_lib.py
class InputBackend(Protocol):
    name: str
    def click(self, hwnd: int, x: int, y: int, button: Literal["left","right"]="left") -> None: ...
    def key_press(self, hwnd: int, vk: int, modifiers: int = 0) -> None: ...
    def type_text(self, hwnd: int, text: str) -> None: ...
    def hotkey(self, hwnd: int, combo: str) -> None: ...

class PostMessageBackend: ...
class SendInputBackend: ...
class LoopbackBackend: ...           # 不发系统调用，记动作日志，单测用

def get_backend(name: str) -> InputBackend: ...
```

每个动作内部 sleep 30~80ms 抖动，避免完美机械节奏。

### `infra/window.py`

```python
@dataclass(frozen=True)
class Window:
    hwnd: int
    title: str
    class_name: str
    pid: int

def find_windows(title_substring: str | None = None, class_name: str | None = None) -> list[Window]: ...
def get_client_rect(hwnd: int) -> tuple[int, int, int, int]: ...
```

热键 combo 字符串格式（`InputBackend.hotkey`）：

- 小写组件用 `+` 分隔，按 `modifier...+key` 顺序
- 允许 modifier：`ctrl` / `shift` / `alt` / `win`
- key 是单字符（`a`–`z` / `0`–`9`）或具名键（`f1`–`f12` / `esc` / `enter` / `space` / `tab`）
- 不合法字串抛 `ValueError`

### 调试面板 `ui/pages/input_debug.py`

- 顶部下拉：**目标窗口**（默认筛 "uwo" / "大航海"；可展开为任意窗口）
- 顶部下拉：**后端**（PostMessage / SendInput / Loopback）
- 三个交互区：
  - **点击**：输入 x、y → 「在客户区点击」按钮；下方画一个缩略截图，点缩略图反向定位坐标
  - **键盘**：输入文本 + 「输入文字」；输入虚拟键码 / 组合键 + 「按键」
  - **热键**：填 `ctrl+alt+o` 字串 → 「发送热键」
- 右侧动作日志：时间 + 后端 + 动作 + 结果
- **业务隔离硬约束**：本面板代码不准 `import core`

## 7. 截图 + OCR + 解析 + 校对入库

### `infra/screenshot.py`

```python
def capture_primary_screen(out_path: Path) -> Path: ...
def capture_region(left: int, top: int, right: int, bottom: int, out_path: Path) -> Path: ...
def capture_window(hwnd: int, out_path: Path) -> Path: ...
```

底层用 `mss`（轻、跨屏、快）替换现有 PowerShell .NET 路径。

### `infra/ocr_engine.py`

```python
@dataclass(frozen=True)
class OcrLine:
    text: str
    bbox: tuple[int, int, int, int]
    confidence: float

class PaddleOcrEngine:
    def __init__(self, lang: str = "ch", model_dir: Path | None = None): ...
    def recognize(self, image_path: Path) -> list[OcrLine]: ...
```

- 第一次实例化时自动下模型到 `~/.paddleocr`
- UI 启动时在后台线程预热；期间调用走排队
- OCR 调用统一在 `QThreadPool` 跑，不阻塞 UI
- 失败抛 `OcrError(reason)`；UI 捕获后在校对面板显示"OCR 失败：{reason}，可手动录入"

### `core/parse.py`

OCR 给的是带 bbox 的文字行。游戏交易所界面版式相对固定：表头（商品名、单价、库存、操作），下方多行商品。

```python
@dataclass(frozen=True)
class ParsedRow:
    good_name: str | None
    raw_good_name: str
    buy_price: int | None
    sell_price: int | None
    stock: int | None
    confidence: float
    raw_bbox: tuple[int, int, int, int]

@dataclass(frozen=True)
class ParsedScreen:
    port_name: str | None
    raw_port_name: str
    rows: list[ParsedRow]
    direction: Literal["buy", "sell", "unknown"]

def parse_exchange_screen(
    lines: list[OcrLine],
    known_goods: list[str],
    known_ports: list[str],
) -> ParsedScreen: ...
```

解析步骤：

1. **港口名识别**：`"当前港口"` / `"所在港"` 等关键字附近取 token
2. **方向识别**：根据界面关键字 `"购买"` / `"出售"` / `"买入"` / `"卖出"` 决定 `direction`，识别不出留 `"unknown"`
3. **行配对**：按 y 坐标聚簇成行；每行从左到右抽 (商品名, 单价, 库存)
4. **价格归位**：按 `direction` 把 OCR 出来的"单价"放到 `ParsedRow.buy_price` 或 `sell_price`；`direction == "unknown"` 时两个字段都留 `None`，让用户在校对面板手动选方向后回填
5. **商品名匹配**：优先匹配 `known_goods`；匹配失败留空让用户校对

### 校对入库流程

```
[截图按钮 / 热键]
  → 后台线程 capture → ocr.recognize → parse_exchange_screen
  → main thread 弹「校对面板」
       - 左：截图缩略 + 高亮 OCR bbox
       - 右：可编辑表
            港口   [中文港口名] (下拉 + 新建)
            方向   ○ 买入  ○ 卖出
            商品 / 价格 / 库存 / 置信度 / ✓
            [全部勾选] [全部取消]
            [取消]            [确认入库]
```

确认入库 = 把勾选的行批量 INSERT 为 `PriceObservation`，`source='ocr'`。新港口名 / 新商品名走"创建确认"小弹窗，避免 OCR 错别字直接污染字典表。

## 8. 错误处理与日志

### 分层

| 层 | 错误类型 | 策略 |
|---|---|---|
| `core/` | 业务参数错误 | 抛 `ValueError`（数据脏）或返回空（无数据）。**不**捕获 IO/系统异常。 |
| `infra/` | 系统异常 | 包成 `WindowNotFoundError` / `OcrError` / `ScreenshotError` 等领域异常 |
| `ui/` | 所有未捕获 | 全局 `sys.excepthook` + Qt `qInstallMessageHandler` → 弹错误对话框 + 写日志 |

### 日志

- `logging` 标准库，输出到 `data/logs/uwo_helper.log`
- 5MB 一档，保留 5 个
- 默认 INFO；`--debug` 启动 DEBUG
- `infra/` 入口加 INFO 埋点（"截图开始/结束/耗时"）

### 输入层

- `input_lib` 每个 send 调用前后打 INFO
- **紧急停止热键** `Ctrl+Alt+P`：触发 `InputBackend.kill_switch()`，标志位让所有循环 break。本期没循环，抽象先到位。

## 9. 测试策略

### 单元测试（必须）

- `tests/core/test_parse.py`：用一组录好的 "OCR 行 → 期望解析" 夹具
- `tests/core/test_recommend.py`：以下 9 条 case
  1. 空输入 → `[]`
  2. 单港单商品 → `[]`
  3. 同港 buy + sell（有次优可替代）→ 选次优组合
  4. 同港 buy + sell（无次优可替代）→ 跳过该商品
  5. 多商品按利润降序
  6. 时效过滤：超 `max_age_hours` 的观察被忽略
  7. 去重取最新：同 (港, 商品) 旧观察被忽略
  8. 白/黑名单组合
  9. `buy_price` / `sell_price` 为 NULL 的不参与对应方向
- `tests/core/test_db.py`：迁移、insert/query、append-only 行为
- `tests/infra/test_input_lib_loopback.py`：用 `LoopbackBackend` 验证动作序列正确

### 手测

- `tests/manual/m0_postmessage_spike.md`：M0 人工验证步骤
- `tests/manual/m2_ocr_smoke.md`：录好的截图扔进 OCR + 解析，校对面板表现

### 不测的部分

- `infra/screenshot.py` / `infra/window.py`：直接打 Win32 / mss，单测价值低，靠手测
- PaddleOCR 包装：依赖外部模型，CI 不跑；只测 `OcrError` 异常路径
- PySide6 UI：项目规模不值得 pytest-qt，靠手测

### CI

仅跑 `pytest tests/core tests/infra/test_input_lib_loopback.py`。M1 阶段前不开 GitHub Action，本地跑即可。

## 10. 依赖

新增：

- `PySide6`（UI）
- `mss`（截图）
- `pywin32`（Win32 API：窗口、PostMessage）
- `paddlepaddle` + `paddleocr`（OCR；M2 才装）
- `pytest`（dev）

`pyproject.toml` 用 optional-dependencies 分组：`ocr`、`dev`，让 M0/M1 阶段不必装大依赖。

## 11. README 改写

实现 M1 时同步改写 `Readme.md`：

- 删掉"安全边界"里的"不自动点击游戏窗口"条款，改为"输入层目前与游戏业务断开，仅作为可独立测试的能力层"
- 新增"风险声明"段：游戏 ToS 风险、检测风险、本工具仅供个人学习/资料整理用途
- 主要模块章节按本文档 §2 结构重写
- "推荐技术栈"段改为对齐本文档 §10
- 阶段计划替换为本文档 §3 的 M0–M3 表

## 12. 风险与已知未知

| 风险 | 缓解 |
|---|---|
| UWO 私服客户端不吃 PostMessage | M0 提前验证；不通过则 M3 降级 |
| PaddleOCR 在游戏字体上准确率不达预期 | 校对面板把 OCR 当建议而非真值；用户每次确认 |
| Windows 高 DPI 缩放导致截图坐标和窗口坐标不一致 | `infra/screenshot.py` 和 `infra/window.py` 显式按 client area 坐标系工作；早期手测验证 |
| PaddleOCR 模型下载失败 | 启动时检测，UI 提示"OCR 模型未就绪，本次仅手录可用" |
| SQLite 在 OneDrive 同步目录下并发被锁 | `db.py` 设置 `PRAGMA journal_mode=WAL`；文档说明默认放在 `data/` 而非云盘 |
| 输入层被误用接业务 | `ui/pages/input_debug.py` 文件头注释 + import linter（M3 阶段引入） |

## 13. 文档与决策记录

- 本文档 = `2026-05-06-uwo-trade-bot-design.md`
- M0 报告 = `2026-05-06-uwo-trade-bot-postmessage-spike.md`（M0 完成后写）
- 实现计划 = `2026-05-06-uwo-trade-bot-plan.md`（writing-plans 阶段产出）
