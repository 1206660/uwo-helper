# UWO Helper

UWO Helper 是 UWO 中文私服的本地跑商辅助工具：手动 / OCR 录入价格观察 → SQLite → 单件利润最大的路线推荐。后续里程碑会加入截图 OCR 半自动录入和可独立测试的输入原语库。

## 当前能力（M1 已交付）

- PySide6 桌面主界面：工作台 / 价格簿 / 推荐路线 三页
- 价格簿手录：港口、商品、买价、卖价、库存、备注 → SQLite
- 推荐路线：按数据有效期、最少利润、Top N 过滤；按单件利润排序
- 工作台：观察总数、最近观察时间、Top 3 推荐预览
- SQLite 自动迁移、append-only 价格历史

## 风险声明

本工具会在后续里程碑（M3）提供"模拟点击 / 模拟键盘"原语并允许投递到任意窗口（包括游戏客户端）。

- 自动化操作可能违反游戏运营方的用户协议，并存在被检测、封号的风险
- 输入原语层会与"游戏业务逻辑"在代码层面隔离（`ui/pages/input_debug.py` 不得 `import core`），调试面板仅用于功能验证
- 工具不会读取或修改游戏进程内存、不抓包、不修改游戏文件
- 使用本工具的责任由用户自行承担

## 安装与运行

需要 Python 3.10+。

```powershell
cd E:\Home\uwo-helper
pip install -e ".[dev]"
python -m uwo_helper
```

数据库默认放在 `data/uwo_helper.sqlite3`。`data/` 已在 `.gitignore`。

## 模块结构

```
src/uwo_helper/
├── core/         # 纯业务: db, models, recommend, parse(M2)
├── infra/        # M2/M3 引入: screenshot, ocr_engine, input_lib, window
├── ui/           # PySide6
└── app.py        # 入口
```

详细设计：`docs/superpowers/specs/2026-05-06-uwo-trade-bot-design.md`。

## 里程碑

| 里程碑 | 范围 | 状态 |
|---|---|---|
| M0 | PostMessage 可行性 spike | 已完成（见 `docs/superpowers/specs/2026-05-06-uwo-trade-bot-postmessage-spike.md`） |
| M1 | PySide6 + SQLite + 手录 + 推荐 | 已完成 |
| M2 | mss 截图 + PaddleOCR + 校对入库 | 待开始 |
| M3 | input_lib 三种后端 + 调试面板 | 待开始（依赖 M0 结果） |

## 测试

```powershell
pytest -v
```

仅核心层（`core/db`, `core/recommend`）有单测；UI 与平台相关代码靠手测。
