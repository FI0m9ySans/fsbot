/**
 * FSBot Gamepad Controller Engine v1.0
 * Xbox 360 Wired Game Controller (QT1688) 完整支持
 * 功能：导航、震动、虚拟键盘触发、设置持久化
 */

// ─── 按钮索引（Xbox 360 标准布局）─────────────────────────────────────────────
const XBOX_BUTTONS = {
    A: 0, B: 1, X: 2, Y: 3,
    LB: 4, RB: 5, LT: 6, RT: 7,
    BACK: 8, START: 9,
    LS: 10, RS: 11,       // 摇杆按下
    DPAD_UP: 12, DPAD_DOWN: 13, DPAD_LEFT: 14, DPAD_RIGHT: 15,
    XBOX: 16
};

// ─── 轴索引 ────────────────────────────────────────────────────────────────────
const XBOX_AXES = { LS_X: 0, LS_Y: 1, RS_X: 2, RS_Y: 3 };

// ─── 默认设置 ─────────────────────────────────────────────────────────────────
const DEFAULT_SETTINGS = {
    vibration: { left: 0.5, right: 0.5, enabled: true },
    sensitivity: { stick: 0.25, navRepeatDelay: 500, navRepeatRate: 150 },
    keymap: {
        A:     'confirm',
        B:     'back',
        X:     'action1',
        Y:     'action2',
        LB:    'prevTab',
        RB:    'nextTab',
        START: 'settings',
        BACK:  'home',
        DPAD_UP:    'up',
        DPAD_DOWN:  'down',
        DPAD_LEFT:  'left',
        DPAD_RIGHT: 'right',
    }
};

// ─── 手柄控制器主类 ────────────────────────────────────────────────────────────
class GamepadController {
    constructor() {
        this.gamepad = null;
        this.settings = this._loadSettings();
        this.prevButtons = {};
        this.heldButtons = {};       // { btnIndex: holdStartTime }
        this.lastNavTime = {};       // 导航重复控制
        this.listeners = {};         // 事件监听
        this.animFrame = null;
        this.connected = false;

        // 可聚焦元素缓存
        this._focusableSelector = 'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
        this._currentFocusIdx = 0;

        this._bindEvents();
        this._showOverlay(false);
    }

    // ─── 事件绑定 ──────────────────────────────────────────────────────────────
    _bindEvents() {
        window.addEventListener('gamepadconnected', (e) => {
            if (e.gamepad.index === 0 || !this.connected) {
                this.gamepad = e.gamepad;
                this.connected = true;
                this._showOverlay(true);
                this._updateStatusBar(true, e.gamepad.id);
                this._vibrate(0.3, 0.3, 200);
                this._startLoop();
                this._emit('connected', { gamepad: e.gamepad });
                console.log('[Gamepad] 已连接:', e.gamepad.id);
            }
        });

        window.addEventListener('gamepaddisconnected', (e) => {
            if (this.gamepad && this.gamepad.index === e.gamepad.index) {
                this.connected = false;
                this.gamepad = null;
                this._showOverlay(false);
                this._updateStatusBar(false, '');
                if (this.animFrame) cancelAnimationFrame(this.animFrame);
                this._emit('disconnected', {});
                console.log('[Gamepad] 已断开');
            }
        });
    }

    // ─── 主轮询循环 ────────────────────────────────────────────────────────────
    _startLoop() {
        const loop = () => {
            this._poll();
            this.animFrame = requestAnimationFrame(loop);
        };
        this.animFrame = requestAnimationFrame(loop);
    }

    _poll() {
        const gamepads = navigator.getGamepads ? navigator.getGamepads() : [];
        const gp = gamepads[this.gamepad ? this.gamepad.index : 0];
        if (!gp) return;
        this.gamepad = gp;

        const now = performance.now();

        // 遍历所有按钮
        gp.buttons.forEach((btn, idx) => {
            const pressed = btn.pressed || btn.value > 0.5;
            const wasPrev = !!this.prevButtons[idx];

            if (pressed && !wasPrev) {
                // 按下瞬间
                this._onButtonDown(idx, now);
                this.heldButtons[idx] = now;
            } else if (!pressed && wasPrev) {
                // 松开
                this._onButtonUp(idx);
                delete this.heldButtons[idx];
                delete this.lastNavTime[idx];
            } else if (pressed && wasPrev) {
                // 持续按住（导航重复）
                this._onButtonHeld(idx, now);
            }

            this.prevButtons[idx] = pressed;
        });

        // 摇杆导航
        this._handleStickNav(gp.axes, now);

        // 更新震动条 UI（如果设置页面打开）
        this._updateVibrationUI();
    }

    // ─── 按键处理 ─────────────────────────────────────────────────────────────
    _onButtonDown(idx, now) {
        const action = this._getAction(idx);
        this._emit('button', { index: idx, action, type: 'down' });
        this._handleAction(action, 'down');

        // 按下震动反馈
        if (this.settings.vibration.enabled) {
            if (idx === XBOX_BUTTONS.A) this._vibrate(0, 0.4, 80);
            else if (idx === XBOX_BUTTONS.B) this._vibrate(0.2, 0, 60);
            else if (idx === XBOX_BUTTONS.X || idx === XBOX_BUTTONS.Y) this._vibrate(0.1, 0.1, 50);
            else if (idx === XBOX_BUTTONS.LB || idx === XBOX_BUTTONS.RB) this._vibrate(0.3, 0.3, 100);
            else if (idx === XBOX_BUTTONS.START) this._vibrate(0.4, 0.4, 150);
        }
    }

    _onButtonUp(idx) {
        const action = this._getAction(idx);
        this._emit('button', { index: idx, action, type: 'up' });
        this._handleAction(action, 'up');
    }

    _onButtonHeld(idx, now) {
        // 导航类按键支持长按重复
        const navActions = ['up', 'down', 'left', 'right'];
        const action = this._getAction(idx);
        if (!navActions.includes(action)) return;

        const holdStart = this.heldButtons[idx] || now;
        const holdDuration = now - holdStart;
        const delay = this.settings.sensitivity.navRepeatDelay;
        const rate = this.settings.sensitivity.navRepeatRate;

        if (holdDuration < delay) return;

        const last = this.lastNavTime[idx] || 0;
        if (now - last >= rate) {
            this._handleAction(action, 'repeat');
            this.lastNavTime[idx] = now;
        }
    }

    // ─── 摇杆导航 ─────────────────────────────────────────────────────────────
    _handleStickNav(axes, now) {
        const dead = this.settings.sensitivity.stick;
        const lx = axes[XBOX_AXES.LS_X] || 0;
        const ly = axes[XBOX_AXES.LS_Y] || 0;

        const STICK_NAV = 900; // 摇杆虚拟按键ID（不与真实按钮冲突）
        const actions = [];
        if (ly < -dead) actions.push({ id: STICK_NAV + 0, action: 'up' });
        if (ly > dead)  actions.push({ id: STICK_NAV + 1, action: 'down' });
        if (lx < -dead) actions.push({ id: STICK_NAV + 2, action: 'left' });
        if (lx > dead)  actions.push({ id: STICK_NAV + 3, action: 'right' });

        // 清理不再活跃的摇杆方向
        [0,1,2,3].forEach(i => {
            const id = STICK_NAV + i;
            if (!actions.find(a => a.id === id) && this.heldButtons[id]) {
                delete this.heldButtons[id];
                delete this.lastNavTime[id];
            }
        });

        actions.forEach(({ id, action }) => {
            if (!this.heldButtons[id]) {
                this.heldButtons[id] = now;
                this._handleAction(action, 'down');
                return;
            }
            const holdStart = this.heldButtons[id];
            const delay = this.settings.sensitivity.navRepeatDelay;
            const rate = this.settings.sensitivity.navRepeatRate;
            if (now - holdStart >= delay) {
                const last = this.lastNavTime[id] || 0;
                if (now - last >= rate) {
                    this._handleAction(action, 'repeat');
                    this.lastNavTime[id] = now;
                }
            }
        });
    }

    // ─── 动作分发 ─────────────────────────────────────────────────────────────
    _handleAction(action, type) {
        if (!action) return;
        if (type !== 'down' && type !== 'repeat') return;

        // 如果虚拟键盘打开，把输入转发给键盘
        if (window.GamepadKeyboard && window.GamepadKeyboard.isOpen()) {
            window.GamepadKeyboard.handleAction(action);
            return;
        }

        switch (action) {
            case 'up':    this._moveFocus(-1, 'v'); break;
            case 'down':  this._moveFocus(1, 'v');  break;
            case 'left':  this._moveFocus(-1, 'h'); break;
            case 'right': this._moveFocus(1, 'h');  break;
            case 'confirm':
                const focused = document.activeElement;
                if (focused && focused !== document.body) {
                    focused.click();
                    // 如果聚焦到输入框，弹出虚拟键盘
                    if ((focused.tagName === 'INPUT' || focused.tagName === 'TEXTAREA') && window.GamepadKeyboard) {
                        window.GamepadKeyboard.open(focused);
                    }
                }
                break;
            case 'back':
                if (window.GamepadKeyboard && window.GamepadKeyboard.isOpen()) {
                    window.GamepadKeyboard.close();
                }
                break;
            case 'prevTab': this._switchTab(-1); break;
            case 'nextTab': this._switchTab(1);  break;
            case 'settings':
                if (window.GamepadSettings) window.GamepadSettings.toggle();
                break;
            case 'home':
                const homeTab = document.querySelector('.tab[data-tab="overview"], .tab[data-tab]');
                if (homeTab) homeTab.click();
                break;
            case 'action1':
            case 'action2':
                this._emit('action', { name: action, type });
                break;
        }
    }

    // ─── 焦点导航 ─────────────────────────────────────────────────────────────
    _moveFocus(dir, axis) {
        const all = Array.from(document.querySelectorAll(this._focusableSelector))
            .filter(el => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0 && !el.closest('[hidden]') && !el.closest('.gamepad-keyboard:not(.open)');
            });

        if (!all.length) return;

        const current = document.activeElement;
        let idx = all.indexOf(current);

        if (idx === -1) {
            // 没有当前焦点，选第一个
            all[0].focus();
            return;
        }

        // 简单线性导航（上下/左右均按DOM顺序）
        const next = (idx + dir + all.length) % all.length;
        all[next].focus();
        all[next].scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }

    _switchTab(dir) {
        const tabs = Array.from(document.querySelectorAll('.tab'));
        if (!tabs.length) return;
        const active = tabs.findIndex(t => t.classList.contains('active'));
        const next = (active + dir + tabs.length) % tabs.length;
        tabs[next].click();
        // Tab切换震动
        if (this.settings.vibration.enabled) this._vibrate(0.2, 0.2, 80);
    }

    // ─── 震动 API ─────────────────────────────────────────────────────────────
    _vibrate(leftIntensity, rightIntensity, durationMs) {
        if (!this.settings.vibration.enabled) return;
        if (!this.gamepad) return;

        const left = leftIntensity * this.settings.vibration.left;
        const right = rightIntensity * this.settings.vibration.right;

        try {
            if (this.gamepad.vibrationActuator) {
                // 标准 API（Chrome/Edge）
                if (this.gamepad.vibrationActuator.playEffect) {
                    this.gamepad.vibrationActuator.playEffect('dual-rumble', {
                        startDelay: 0,
                        duration: durationMs,
                        weakMagnitude: right,
                        strongMagnitude: left
                    });
                } else if (this.gamepad.vibrationActuator.pulse) {
                    this.gamepad.vibrationActuator.pulse(Math.max(left, right), durationMs);
                }
            }
        } catch (e) {
            // 震动不支持，静默忽略
        }
    }

    // 公开的震动方法（给设置页测试用）
    vibrate(left, right, duration) {
        const origLeft = this.settings.vibration.left;
        const origRight = this.settings.vibration.right;
        this.settings.vibration.left = left;
        this.settings.vibration.right = right;
        this._vibrate(1.0, 1.0, duration);
        this.settings.vibration.left = origLeft;
        this.settings.vibration.right = origRight;
    }

    // ─── 按键映射 ─────────────────────────────────────────────────────────────
    _getAction(btnIdx) {
        const name = Object.keys(XBOX_BUTTONS).find(k => XBOX_BUTTONS[k] === btnIdx);
        if (!name) return null;
        return this.settings.keymap[name] || null;
    }

    // ─── 设置持久化 ───────────────────────────────────────────────────────────
    _loadSettings() {
        try {
            const saved = localStorage.getItem('fsbot_gamepad_settings');
            if (saved) return Object.assign({}, JSON.parse(JSON.stringify(DEFAULT_SETTINGS)), JSON.parse(saved));
        } catch (e) {}
        return JSON.parse(JSON.stringify(DEFAULT_SETTINGS));
    }

    saveSettings() {
        localStorage.setItem('fsbot_gamepad_settings', JSON.stringify(this.settings));
    }

    resetSettings() {
        this.settings = JSON.parse(JSON.stringify(DEFAULT_SETTINGS));
        this.saveSettings();
    }

    // ─── UI 辅助 ──────────────────────────────────────────────────────────────
    _showOverlay(show) {
        let bar = document.getElementById('gamepad-status-bar');
        if (!bar) {
            bar = document.createElement('div');
            bar.id = 'gamepad-status-bar';
            bar.innerHTML = `
                <span id="gp-icon">🎮</span>
                <span id="gp-name">Xbox 360 Controller</span>
                <span id="gp-battery" style="margin-left:8px;opacity:0.7;font-size:0.85em;"></span>
                <button id="gp-settings-btn" title="手柄设置" style="margin-left:10px;background:none;border:1px solid rgba(255,255,255,0.3);color:#fff;border-radius:4px;padding:2px 8px;cursor:pointer;font-size:0.8em;">⚙️ 设置</button>
            `;
            bar.style.cssText = `
                position:fixed;bottom:0;left:0;right:0;
                background:rgba(16,16,32,0.92);backdrop-filter:blur(8px);
                color:#fff;padding:6px 16px;
                display:flex;align-items:center;gap:8px;
                font-size:0.85em;z-index:9000;
                border-top:1px solid rgba(255,255,255,0.1);
                transition:transform 0.3s ease;
            `;
            document.body.appendChild(bar);

            document.getElementById('gp-settings-btn').addEventListener('click', () => {
                if (window.GamepadSettings) window.GamepadSettings.toggle();
                else window.open('/gamepad-settings', '_blank');
            });
        }
        bar.style.transform = show ? 'translateY(0)' : 'translateY(100%)';
    }

    _updateStatusBar(connected, id) {
        const nameEl = document.getElementById('gp-name');
        if (nameEl) {
            if (connected) {
                // 截取手柄型号中可读部分
                const shortName = id.replace(/\s*\(.*?\)\s*/g, '').trim() || 'Xbox 360 Controller';
                nameEl.textContent = shortName;
            } else {
                nameEl.textContent = '未连接';
            }
        }
    }

    _updateVibrationUI() {
        // 只在设置页面存在时更新
        if (!window.GamepadSettings || !window.GamepadSettings.isOpen()) return;
        if (!this.gamepad) return;

        const ltEl = document.getElementById('gp-lt-value');
        const rtEl = document.getElementById('gp-rt-value');
        if (ltEl) ltEl.textContent = (this.gamepad.buttons[XBOX_BUTTONS.LT]?.value || 0).toFixed(2);
        if (rtEl) rtEl.textContent = (this.gamepad.buttons[XBOX_BUTTONS.RT]?.value || 0).toFixed(2);
    }

    // ─── 事件系统 ─────────────────────────────────────────────────────────────
    on(event, callback) {
        if (!this.listeners[event]) this.listeners[event] = [];
        this.listeners[event].push(callback);
        return this;
    }

    off(event, callback) {
        if (this.listeners[event]) {
            this.listeners[event] = this.listeners[event].filter(cb => cb !== callback);
        }
    }

    _emit(event, data) {
        (this.listeners[event] || []).forEach(cb => cb(data));
    }

    // ─── 获取实时状态 ─────────────────────────────────────────────────────────
    getState() {
        if (!this.gamepad) return null;
        return {
            connected: true,
            id: this.gamepad.id,
            buttons: this.gamepad.buttons.map(b => ({ pressed: b.pressed, value: b.value })),
            axes: Array.from(this.gamepad.axes),
            timestamp: this.gamepad.timestamp
        };
    }
}

// ─── 全局单例 ─────────────────────────────────────────────────────────────────
window.GamepadController = new GamepadController();
window.XBOX_BUTTONS = XBOX_BUTTONS;
window.XBOX_AXES = XBOX_AXES;
