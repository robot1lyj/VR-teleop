(function () {
  const EVENT_STATUS = 'vrbridge-status';
  const EVENT_LOG = 'vrbridge-log';

  const VRBridge = {
    socket: null,
    url: '',
    ready: false,

    connect(url) {
      this.disconnect();
      this.url = url;
      this._status('连接中…', 'status--connecting');
      this._log(`🔌 尝试连接 ${url}`);

      try {
        const ws = new WebSocket(url);
        this.socket = ws;

        ws.addEventListener('open', () => {
          this.ready = true;
          this._status('已连接', 'status--connected');
          this._log('✅ WebSocket 已建立');
        });

        ws.addEventListener('close', (event) => {
          this.ready = false;
          const reason = event.reason || '连接已关闭';
          this._status('未连接');
          this._log(`⚠️  WebSocket 关闭：${reason}`);
          document.dispatchEvent(
            new CustomEvent('vrbridge-stop-request', {
              detail: { source: 'socket-close' },
            })
          );
        });

        ws.addEventListener('error', (error) => {
          this._log(`❌ WebSocket 错误：${error.message || error}`);
        });
      } catch (error) {
        this._log(`❌ 无法创建 WebSocket：${error.message}`);
        this._status('未连接');
      }
    },

    disconnect() {
      if (this.socket) {
        try {
          this.socket.close();
        } catch (_) {
          /* noop */
        }
      }
      this.socket = null;
      this.ready = false;
    },

    send(payload) {
      if (!this.ready || !this.socket || this.socket.readyState !== WebSocket.OPEN) {
        return;
      }
      try {
        this.socket.send(JSON.stringify(payload));
      } catch (error) {
        this._log(`❌ 发送失败：${error.message}`);
      }
    },

    _status(text, tone) {
      document.dispatchEvent(
        new CustomEvent(EVENT_STATUS, {
          detail: { status: text, tone },
        })
      );
    },

    _log(message) {
      document.dispatchEvent(
        new CustomEvent(EVENT_LOG, {
          detail: { message },
        })
      );
    },
  };

  window.VRBridge = VRBridge;

  function captureGamepadState(controllerEl) {
    const tracked = controllerEl.components['tracked-controls']?.controller;
    const gamepad = tracked?.gamepad;
    if (!gamepad) {
      return { gripActive: false, trigger: 0, menuPressed: false };
    }

    const triggerButton = gamepad.buttons?.[0];
    const gripButton = gamepad.buttons?.[1];
    const extraButtons = Array.isArray(gamepad.buttons) ? gamepad.buttons.slice(3) : [];

    const triggerValue = triggerButton ? triggerButton.value || (triggerButton.pressed ? 1 : 0) : 0;
    const gripValue = gripButton ? gripButton.value || (gripButton.pressed ? 1 : 0) : 0;
    const menuPressed = extraButtons.some((button) => {
      if (!button) return false;
      if (typeof button.pressed === 'boolean' && button.pressed) {
        return true;
      }
      return typeof button.value === 'number' && button.value > 0.5;
    });

    return {
      gripActive: gripValue > 0.5,
      trigger: triggerValue,
      menuPressed,
    };
  }

  AFRAME.registerComponent('controller-stream', {
    schema: {
      interval: { type: 'number', default: 20 }, // ≈50Hz，满足遥操作刷新率
      scale: { type: 'number', default: 1.0 },
    },

    init() {
      this.left = document.getElementById('leftController');
      this.right = document.getElementById('rightController');
      this.lastSent = 0;
      this.scene = this.el.sceneEl || this.el;
      this.menuHoldMs = 0;
      this.menuTriggered = false;
    },

    tick(time, delta) {
      if (!window.VRBridge || !window.VRBridge.ready) {
        return;
      }

      if (!this.scene) {
        return;
      }

      if (typeof this.scene.is === 'function' && !this.scene.is('vr-mode')) {
        return;
      }

      this.lastSent += delta;
      if (this.lastSent < this.data.interval) {
        return;
      }
      this.lastSent = Math.max(0, this.lastSent - this.data.interval);

      const payload = { timestamp: Date.now() };
      let hasData = false;
      let exitIntent = false;

      const processController = (controllerEl, handKey) => {
        if (!controllerEl || !controllerEl.object3D.visible) {
          return null;
        }

        const pos = controllerEl.object3D.position;
        const quat = controllerEl.object3D.quaternion;
        const buttons = captureGamepadState(controllerEl);

        if (buttons.menuPressed) {
          exitIntent = true;
        }

        return {
          hand: handKey,
          position: { x: pos.x, y: pos.y, z: pos.z },
          quaternion: { x: quat.x, y: quat.y, z: quat.z, w: quat.w },
          gripActive: buttons.gripActive,
          trigger: buttons.trigger,
          menuPressed: buttons.menuPressed,
        };
      };

      const leftState = processController(this.left, 'left');
      const rightState = processController(this.right, 'right');

      if (leftState) {
        payload.leftController = leftState;
        hasData = true;
      }
      if (rightState) {
        payload.rightController = rightState;
        hasData = true;
      }

      if (hasData) {
        window.VRBridge.send(payload);
      }

      if (exitIntent) {
        this.menuHoldMs += delta;
        if (this.menuHoldMs >= 800 && !this.menuTriggered) {
          this.menuTriggered = true;
          document.dispatchEvent(
            new CustomEvent(EVENT_LOG, {
              detail: { message: '🛑 手柄请求停止手柄追踪（长按侧键）' },
            })
          );
          document.dispatchEvent(
            new CustomEvent('vrbridge-stop-request', {
              detail: { source: 'controller' },
            })
          );
        }
      } else {
        this.menuHoldMs = 0;
        this.menuTriggered = false;
      }
    },
  });
})();
