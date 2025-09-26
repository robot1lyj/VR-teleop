# VR-New 模块架构概述

```
telegrip/vr_new/
├── __init__.py
├── controller_state.py        # 单手柄状态结构，记录握持/扳机/姿态等信息
├── controller_stream.py       # 独立 WebSocket 服务入口，解析手柄消息并打印目标指令
├── web-ui/                    # 面向 VR 的简洁前端，可独立打包
│   ├── index.html             # 极简页面：Ws 连接输入 + 状态日志 + A‑Frame 场景
│   ├── interface.js           # 负责 UI 交互、日志显示
│   ├── styles.css             # 深色主题样式
│   └── vr_app.js              # 注册 A‑Frame 组件、采集手柄数据
└── README.md                  # 本文档
```

## 数据流示意

```
  VR 头显 / 浏览器 (web-ui/vr_app.js)
        │  WebSocket(JSON, 含位置/四元数/握持状态)
        ▼
  controller_stream.py
        │  解析消息 → 更新 ControllerState → 生成控制目标字典
        ▼
      标准输出 / 自定义回调
```

- `controller_state.py`：
  - 为每个手柄维护一次握持的起点位置与四元数，并计算相对旋转（Z / X 轴）。
  - 提供 `reset_grip()` 用于断开或松开握持后的状态清理。

- `controller_stream.py`：
  - 启动一个基于 `websockets` 的 `ws://` 服务，直接打印解析后的控制指令。
  - 收到手柄数据后，调用 `_handle_controller()` 输出包含 `target_position`、`wrist_roll_deg`、`wrist_flex_deg` 等字段的控制指令，方便独立调试。
  - 可通过命令行参数调整监听地址、端口、缩放系数以及日志级别。

## 通信说明

- 默认使用明文 `ws://`，避免 TLS 开销以提升遥操作响应。当前目录不再附带证书文件。
- 如需在受限环境下切换 `wss://`，可以自行生成证书并在启动 `websockets.serve()` 时传入。
- 浏览器侧 `controller-stream` 组件默认 20ms（≈50Hz）发送一次握持状态，可在 HTML 中通过 `controller-stream="interval: 20"` 自定义。
- 页面上的「开启手柄追踪」按钮会在 VR 会话建立后变成「停止手柄追踪」，可随时退出。
- Quest 手柄长按 A/B（或 X/Y）键约 1 秒，也可以直接请求退出手柄追踪。

## 常用命令

```bash
# 启动 VR 调试服务器（明文 ws://，最精简）
python -m telegrip.vr_new.controller_stream --host 0.0.0.0 --port 8442

# 在另一终端启动静态页面服务（指向 vr_new/web-ui）
python -m http.server 8080 --directory telegrip/vr_new/web-ui
```

执行上述命令后，在浏览器或头显访问 `http://<主机IP>:8080/index.html`，
在页面输入框中填写 `ws://<主机IP>:8442` 并点击「连接」，再按「开启手柄追踪」
进入 VR/AR 会话。面板会实时展示 WebSocket 状态与最新日志，终端则输出解析后的控制目标。
