# VR-New 模块概览（WebRTC 版）

```
├── __init__.py                # 暴露 run_vr_controller_stream 入口
├── controller_state.py        # 单手柄状态结构，记录握持/扳机/姿态等信息
├── controller_stream.py       # WebRTC 信令入口，封装姿态处理管线与 CLI
├── webrtc_endpoint.py         # WebSocket 信令 + aiortc DataChannel 服务端
└── web-ui/                    # 浏览器侧 A-Frame 客户端
    ├── index.html             # 信令地址输入、状态显示、A-Frame 场景
    ├── interface.js           # UI 交互与日志面板
    ├── styles.css             # 深色主题样式
    └── vr_app.js              # WebRTCBridge 与手柄数据采集
```

## 数据流

```
  浏览器 / 头显 (web-ui/vr_app.js)
        │ 信令：WebSocket (offer/answer/ICE)
        │ 数据：WebRTC DataChannel(JSON，姿态 50 Hz)
        ▼
  controller_stream.py + webrtc_endpoint.py
        │ ControllerPipeline 解析 -> 更新 ControllerState
        ▼
      标准输出 / 后续机器人控制模块
```

- `ControllerPipeline` 将左/右手柄的位移、四元数转换为目标字典（位置、腕部角度、夹爪状态），方便单元测试复用。
- `VRWebRTCServer` 单客户端模式：保留现有 WebSocket 端口，仅承担信令交换；姿态数据通过名为 `controller` 的 DataChannel 传输。
- `web-ui/vr_app.js` 中的 `WebRTCBridge` 负责创建 `RTCPeerConnection`、管理 DataChannel 并以 20 ms（≈50 Hz）节奏发送手柄姿态。

## 局域网快速上手

1. **安装依赖**（仅需一次）：
   ```bash
   pip install aiortc websockets numpy
   ```
   若使用 Conda 环境，请先激活目标环境。

2. **启动信令 + DataChannel 服务**（局域网可关闭 STUN）：
   ```bash
   PYTHONPATH=. python -m controller_stream \
     --host 0.0.0.0 \
     --port 8442 \
     --no-stun \
     --log-level info
   ```
   - 默认同时追踪双手柄，可用 `--hands left` 或 `--hands right` 仅启用单侧。
   - 如遇到 NAT 导致协商失败，再追加 `--stun stun:stun.l.google.com:19302`。

3. **启动前端界面**（本地文件即可）：
   ```bash
   python -m http.server 8080 --directory web-ui
   ```

4. **在浏览器 / 头显中操作**：
   - 访问 `http://<服务器IP>:8080`。
   - 在输入框填写 `ws://<服务器IP>:8442`，点击「连接」。
   - 成功建立 DataChannel 后点击「开启手柄追踪」，允许浏览器进入 VR/AR 模式。
   - 手柄长按侧键或页面按钮可随时停止追踪；终端会实时打印目标字典。



![image-20250928145800282](https://raw.githubusercontent.com/robot1lyj/image_typora/main/image-20250928145800282.png)

## CLI 选项速查

| 参数 | 说明 |
| ---- | ---- |
| `--host` / `--port` | WebSocket 信令监听地址与端口（默认 `0.0.0.0:8442`）。 |
| `--hands` | `both` / `left` / `right`，限制 ControllerPipeline 处理的手柄。 |
| `--scale` | 位移缩放系数，影响 `target_position`。 |
| `--channel-name` | DataChannel 名称，需与前端 `WebRTCBridge` 中一致。 |
| `--no-stun` | 只使用局域网 host-candidate（默认行为）。 |
| `--stun URL` | 追加可选 STUN 服务器；可重复指定多个 URL。 |
| `--log-level` | Python 日志等级，如 `debug` / `info`。 |

## 调试建议（局域网）

- **观察终端输出**：每条 DataChannel 消息触发的目标字典会打印到标准输出，可直接验证姿态解算是否正确。
- **浏览器日志**：`web-ui` 页面左侧日志实时显示信令协商、DataChannel 状态和错误信息。
- **断线重连**：若连接状态变为 `disconnected`/`failed`，前端会自动重新协商；必要时刷新页面即可恢复。
- **纯脚本测试**：可以通过 `python - <<'PY'` 直接构造 `ControllerPipeline` 并注入样例 payload，便于单元级验证。

> 当前方案专为局域网场景设计，默认不启用 TLS/证书，也不提供多客户端抢占逻辑。如需互联网部署或并发接入，可在此基础上扩展。 
