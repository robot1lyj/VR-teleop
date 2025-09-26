"""独立的 VR 手柄 WebSocket 转换入口，用于快速实验。

与主程序分离，便于单独启动一个 WebSocket 服务来验证
浏览器端发送的手柄数据是否正确。脚本会把解析后的目标
指令打印到终端，供调试参考。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import signal
from typing import Any, Dict

import numpy as np
import websockets

from .controller_state import ControllerState, LEFT_CONTROLLER, RIGHT_CONTROLLER

logger = logging.getLogger(__name__)

# 数值运算的极小值阈，用于避免除 0 或不稳定的归一化。
_EPSILON = 1e-8


def _compute_relative_position(current: Dict[str, float], origin: np.ndarray, scale: float) -> np.ndarray:
    """计算当前位置相对握持起点的位移，并乘以缩放系数。"""

    delta = np.array([current["x"], current["y"], current["z"]]) - origin
    return delta * scale


def _normalize_quaternion(quat: np.ndarray) -> np.ndarray:
    """返回单位化后的四元数，避免数值噪声扩大。"""

    norm = np.linalg.norm(quat)
    if norm < _EPSILON:
        return quat
    return quat / norm


def _quaternion_conjugate(quat: np.ndarray) -> np.ndarray:
    """求四元数的共轭，用于计算相对旋转。"""

    x, y, z, w = quat
    return np.array([-x, -y, -z, w])


def _quaternion_multiply(q1: np.ndarray, q2: np.ndarray) -> np.ndarray:
    """按数学定义相乘两个四元数（均为 x/y/z/w 顺序）。"""

    x1, y1, z1, w1 = q1
    x2, y2, z2, w2 = q2
    return np.array(
        [
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        ]
    )


def _quaternion_to_rotvec(quat: np.ndarray) -> np.ndarray:
    """将单位四元数转换为 Rodrigues 旋转向量（弧度）。"""

    quat = _normalize_quaternion(quat)
    w = float(np.clip(quat[3], -1.0, 1.0))
    angle = 2.0 * math.acos(w)
    sin_half = math.sqrt(max(0.0, 1.0 - w * w))
    if sin_half < _EPSILON:
        return np.zeros(3)
    axis = quat[:3] / sin_half
    return axis * angle


def _extract_axis_angles(current_quat: np.ndarray, origin_quat: np.ndarray) -> tuple[float, float]:
    """从当前/初始四元数中解析 Z 轴和 X 轴的相对旋转角度。"""

    if current_quat is None or origin_quat is None:
        return 0.0, 0.0

    try:
        relative_quat = _quaternion_multiply(_normalize_quaternion(current_quat), _quaternion_conjugate(_normalize_quaternion(origin_quat)))
        rotvec = _quaternion_to_rotvec(relative_quat)
        z_rotation_deg = -math.degrees(rotvec[2])
        x_rotation_deg = math.degrees(rotvec[0])
        return z_rotation_deg, x_rotation_deg
    except Exception as exc:  # pragma: no cover - 数值边界情况
        logger.warning("Failed to extract axis angles: %s", exc)
        return 0.0, 0.0


def _to_goal(controller: ControllerState, relative: np.ndarray, z_rot: float, x_rot: float) -> Dict[str, Any]:
    """将当前状态转换为控制目标。"""

    return {
        "arm": controller.hand,
        "mode": "position",
        "target_position": relative.tolist(),
        "wrist_roll_deg": -z_rot,
        "wrist_flex_deg": -x_rot,
        "gripper_closed": not controller.trigger_active,
    }


async def _handle_controller(controller: ControllerState, payload: Dict[str, Any], scale: float) -> Dict[str, Any] | None:
    """根据单个手柄的数据更新状态并返回控制目标。"""

    position = payload.get("position")
    quaternion = payload.get("quaternion")
    grip_active = payload.get("gripActive", False)
    trigger = payload.get("trigger", 0)

    if position is None:
        return None

    trigger_active = trigger > 0.5
    if trigger_active != controller.trigger_active:
        controller.trigger_active = trigger_active
        logger.info("%s trigger %s", controller.hand, "ON" if trigger_active else "OFF")

    if not grip_active:
        if controller.grip_active:
            controller.reset_grip()
            logger.info("%s grip released", controller.hand)
        return None

    if not controller.grip_active:
        controller.grip_active = True
        controller.origin_position = np.array([position["x"], position["y"], position["z"]])
        if quaternion:
            controller.origin_quaternion = np.array([quaternion["x"], quaternion["y"], quaternion["z"], quaternion["w"]])
            controller.accumulated_quaternion = controller.origin_quaternion
        logger.info("%s grip engaged; origin locked", controller.hand)
        return None

    if quaternion:
        controller.accumulated_quaternion = np.array([quaternion["x"], quaternion["y"], quaternion["z"], quaternion["w"]])

    relative = _compute_relative_position(position, controller.origin_position, scale)
    z_rot, x_rot = _extract_axis_angles(controller.accumulated_quaternion, controller.origin_quaternion)
    return _to_goal(controller, relative, z_rot, x_rot)


async def _process_message(message: str, scale: float) -> None:
    """解析 WebSocket 收到的 JSON 字符串，并打印控制目标。"""

    data = json.loads(message)

    if "leftController" in data or "rightController" in data:
        if left := data.get("leftController"):
            goal = await _handle_controller(LEFT_CONTROLLER, left, scale)
            if goal:
                print(goal)
        if right := data.get("rightController"):
            goal = await _handle_controller(RIGHT_CONTROLLER, right, scale)
            if goal:
                print(goal)
        return

    hand = data.get("hand")
    if hand == "left":
        controller = LEFT_CONTROLLER
    elif hand == "right":
        controller = RIGHT_CONTROLLER
    else:
        return

    goal = await _handle_controller(controller, data, scale)
    if goal:
        print(goal)


async def run_server(host: str, port: int, scale: float) -> None:
    """启动异步 WebSocket 服务并等待终止信号。"""

    async def handler(websocket, _path=None):
        # websockets>=12 只传递 websocket；保留 _path 兼容旧版本。
        logger.info("Client connected: %s", websocket.remote_address)
        try:
            async for message in websocket:
                await _process_message(message, scale)
        except websockets.exceptions.ConnectionClosed:
            logger.info("Client disconnected: %s", websocket.remote_address)
        finally:
            LEFT_CONTROLLER.reset_grip()
            RIGHT_CONTROLLER.reset_grip()

    server = await websockets.serve(handler, host, port)
    logger.info("VR debug server listening on ws://%s:%s", host, port)

    stop_event = asyncio.Event()

    def _stop(*_args):
        stop_event.set()

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, _stop)
    loop.add_signal_handler(signal.SIGTERM, _stop)

    await stop_event.wait()
    server.close()
    await server.wait_closed()


def run_vr_controller_stream() -> None:
    """命令行入口：解析参数并运行异步服务器。"""

    parser = argparse.ArgumentParser(description="Standalone VR controller stream logger")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8442)
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--log-level", default="info")

    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()))

    asyncio.run(run_server(args.host, args.port, args.scale))


if __name__ == "__main__":
    run_vr_controller_stream()
