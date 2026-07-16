/**
 * FSBot Gamepad Virtual Keyboard v1.0
 * 手柄操作的虚拟键盘，聚焦到输入框时自动弹出
 * 支持：字母/数字/符号、大小写切换、退格、确认、取消
 */

class GamepadVirtualKeyboard {
    constructor() {
        this.targetInput = null;
        this.isVisible = false;
        this.caps = false;
        this.shift = false;
        this.currentLayout = 'alpha'; // 'alpha' | 'num' | 'sym'
        this.focusedKeyIdx = 0;

        this.layouts = {
            alpha: [
                ['q','w','e','r','t','y','u','i','o','p'],
                ['a','s','d','f','g','h','j','k','l'],
                ['⇧','z','x','c','v','b','n','m','⌫'],
                ['123','␣',' 中/英 ','↵']
            ],
            num: [
                ['1','2','3','4','5','6','7','8','9','0'],
                ['-','/',':', ';','(',')','$','&','@','"'],
                ['#','%','^','*','+','=','\\','|','~','`'],
                ['ABC','␣','⌫','↵']
            ],
            sym: [
                ['[',']','{','}','#','%','^','*','+','='],
                ['_','\\','|','~','<','>','€','£','¥','•'],
                ['.',',','?','!','\'','⌫'],
                ['ABC','␣','↵']
            ]
        };

        this._createDOM();
        this._bindInputFocus();
    }

    // ─── 创建DOM ──────────────────────────────────────────────────────────────
    _createDOM() {
        this.container = document.createElement('div');
        this.container.id = 'gamepad-keyboard';
        this.container.innerHTML = `
            <div class="gkb-header">
                <div class="gkb-preview-wrap">
                    <div class="gkb-label">输入中</div>
                    <div class="gkb-preview" id="gkb-preview"></div>
                </div>
                <div class="gkb-controls">
                    <span class="gkb-hint"><b>A</b> 确认  <b>B</b> 关闭  <b>↕</b> 移动  <b>LB/RB</b> 切换布局</span>
                </div>
            </div>
            <div class="gkb-keys" id="gkb-keys"></div>
        `;

        const style = document.createElement('style');
        style.textContent = `
            #gamepad-keyboard {
                position: fixed;
                bottom: 40px;
                left: 50%;
                transform: translateX(-50%) translateY(110%);
                width: min(700px, 96vw);
                background: #1a1a2e;
                border: 1px solid rgba(99,179,237,0.35);
                border-radius: 16px;
                padding: 14px 14px 10px;
                box-shadow: 0 -4px 32px rgba(0,0,0,0.7);
                z-index: 9500;
                transition: transform 0.28s cubic-bezier(.4,0,.2,1);
                user-select: none;
            }
            #gamepad-keyboard.open {
                transform: translateX(-50%) translateY(0);
            }
            .gkb-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 10px;
                gap: 10px;
            }
            .gkb-preview-wrap {
                flex: 1;
                min-width: 0;
            }
            .gkb-label {
                font-size: 0.7em;
                color: rgba(255,255,255,0.4);
                margin-bottom: 2px;
            }
            .gkb-preview {
                background: rgba(255,255,255,0.07);
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 6px;
                padding: 4px 10px;
                min-height: 28px;
                color: #fff;
                font-size: 1em;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .gkb-preview::after {
                content: '|';
                animation: gkb-blink 1s infinite;
                color: #63b3ed;
                margin-left: 1px;
            }
            @keyframes gkb-blink { 0%,100%{opacity:1} 50%{opacity:0} }
            .gkb-hint {
                font-size: 0.7em;
                color: rgba(255,255,255,0.4);
                white-space: nowrap;
            }
            .gkb-hint b {
                background: rgba(255,255,255,0.15);
                border-radius: 3px;
                padding: 1px 4px;
                color: #fff;
                font-size: 0.9em;
            }
            .gkb-keys {
                display: flex;
                flex-direction: column;
                gap: 6px;
            }
            .gkb-row {
                display: flex;
                justify-content: center;
                gap: 5px;
            }
            .gkb-key {
                background: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 7px;
                color: #e2e8f0;
                font-size: 0.95em;
                min-width: 40px;
                height: 38px;
                padding: 0 8px;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: background 0.1s, transform 0.1s, border-color 0.1s;
                flex: 1;
                max-width: 60px;
            }
            .gkb-key.wide { max-width: 100px; flex: 2; }
            .gkb-key.wider { max-width: 160px; flex: 4; }
            .gkb-key.special {
                background: rgba(99,179,237,0.12);
                color: #90cdf4;
            }
            .gkb-key.focused {
                background: #2b6cb0;
                border-color: #63b3ed;
                color: #fff;
                transform: scale(1.08);
                box-shadow: 0 0 10px rgba(99,179,237,0.4);
            }
            .gkb-key:active, .gkb-key.pressed {
                background: #3182ce;
                transform: scale(0.95);
            }
            .gkb-key.caps-active {
                background: rgba(154,230,180,0.2);
                border-color: #68d391;
                color: #9ae6b4;
            }
        `;
        document.head.appendChild(style);
        document.body.appendChild(this.container);
        this._renderKeys();
    }

    // ─── 渲染按键 ─────────────────────────────────────────────────────────────
    _renderKeys() {
        const container = document.getElementById('gkb-keys');
        if (!container) return;
        container.innerHTML = '';
        this.keyElements = [];

        const layout = this.layouts[this.currentLayout];
        layout.forEach((row, rowIdx) => {
            const rowEl = document.createElement('div');
            rowEl.className = 'gkb-row';
            row.forEach((key, colIdx) => {
                const btn = document.createElement('button');
                btn.className = 'gkb-key';

                // 特殊键样式
                const isSpecial = ['⇧','⌫','↵','␣','123','ABC','SYM',' 中/英 '].includes(key);
                if (isSpecial) btn.classList.add('special');
                if (key === '␣' || key === ' 中/英 ') btn.classList.add('wider');
                if (['⇧','⌫','↵','123','ABC','SYM'].includes(key)) btn.classList.add('wide');

                // 大小写显示
                let display = key;
                if (this.currentLayout === 'alpha' && key.length === 1 && /[a-z]/.test(key)) {
                    display = (this.caps || this.shift) ? key.toUpperCase() : key;
                }
                btn.textContent = display;
                btn.dataset.key = key;

                // 大写高亮
                if (key === '⇧' && this.caps) btn.classList.add('caps-active');

                btn.addEventListener('click', () => this._pressKey(key));
                rowEl.appendChild(btn);
                this.keyElements.push(btn);
            });
            container.appendChild(rowEl);
        });

        this._updateFocusHighlight();
    }

    _updateFocusHighlight() {
        this.keyElements.forEach((el, i) => {
            el.classList.toggle('focused', i === this.focusedKeyIdx);
        });
        if (this.keyElements[this.focusedKeyIdx]) {
            this.keyElements[this.focusedKeyIdx].scrollIntoView({ block: 'nearest' });
        }
    }

    // ─── 按键逻辑 ─────────────────────────────────────────────────────────────
    _pressKey(key) {
        if (!this.targetInput) return;

        // 震动反馈
        if (window.GamepadController && window.GamepadController.settings.vibration.enabled) {
            window.GamepadController._vibrate(0, 0.25, 40);
        }

        if (key === '⌫') {
            // 退格
            const start = this.targetInput.selectionStart;
            const end = this.targetInput.selectionEnd;
            if (start !== end) {
                // 删除选中
                const val = this.targetInput.value;
                this.targetInput.value = val.slice(0, start) + val.slice(end);
                this.targetInput.setSelectionRange(start, start);
            } else if (start > 0) {
                const val = this.targetInput.value;
                this.targetInput.value = val.slice(0, start - 1) + val.slice(start);
                this.targetInput.setSelectionRange(start - 1, start - 1);
            }
        } else if (key === '↵') {
            // 确认/换行
            if (this.targetInput.tagName === 'TEXTAREA') {
                this._insertText('\n');
            } else {
                this.close();
                this.targetInput.dispatchEvent(new Event('change', { bubbles: true }));
                // 触发表单提交（如果有）
                const form = this.targetInput.closest('form');
                if (form) form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
            }
        } else if (key === '⇧') {
            this.caps = !this.caps;
            this._renderKeys();
            return;
        } else if (key === '123') {
            this.currentLayout = 'num';
            this.focusedKeyIdx = 0;
            this._renderKeys();
            return;
        } else if (key === 'ABC') {
            this.currentLayout = 'alpha';
            this.focusedKeyIdx = 0;
            this._renderKeys();
            return;
        } else if (key === 'SYM') {
            this.currentLayout = 'sym';
            this.focusedKeyIdx = 0;
            this._renderKeys();
            return;
        } else if (key === '␣') {
            this._insertText(' ');
        } else if (key === ' 中/英 ') {
            // 中英切换（触发输入法，仅提示）
            this._insertText(' ');
        } else if (key.length === 1) {
            let char = key;
            if (this.currentLayout === 'alpha' && /[a-z]/.test(key)) {
                char = (this.caps || this.shift) ? key.toUpperCase() : key;
                if (this.shift) {
                    this.shift = false;
                    this._renderKeys();
                }
            }
            this._insertText(char);
        }

        this._updatePreview();
        this.targetInput.dispatchEvent(new Event('input', { bubbles: true }));
    }

    _insertText(text) {
        if (!this.targetInput) return;
        const start = this.targetInput.selectionStart;
        const end = this.targetInput.selectionEnd;
        const val = this.targetInput.value;
        this.targetInput.value = val.slice(0, start) + text + val.slice(end);
        this.targetInput.setSelectionRange(start + text.length, start + text.length);
    }

    _updatePreview() {
        const el = document.getElementById('gkb-preview');
        if (el && this.targetInput) {
            el.textContent = this.targetInput.value || '';
        }
    }

    // ─── 手柄动作处理 ─────────────────────────────────────────────────────────
    handleAction(action) {
        const totalKeys = this.keyElements.length;
        if (!totalKeys) return;

        // 计算当前行列
        const layout = this.layouts[this.currentLayout];
        let rowLengths = layout.map(r => r.length);
        let cumulative = 0;
        let currentRow = 0;
        let currentCol = 0;
        for (let r = 0; r < rowLengths.length; r++) {
            if (this.focusedKeyIdx < cumulative + rowLengths[r]) {
                currentRow = r;
                currentCol = this.focusedKeyIdx - cumulative;
                break;
            }
            cumulative += rowLengths[r];
        }

        let newRow = currentRow, newCol = currentCol;

        switch (action) {
            case 'right':
                newCol = (currentCol + 1) % rowLengths[currentRow];
                break;
            case 'left':
                newCol = (currentCol - 1 + rowLengths[currentRow]) % rowLengths[currentRow];
                break;
            case 'down':
                newRow = (currentRow + 1) % layout.length;
                newCol = Math.min(currentCol, rowLengths[newRow] - 1);
                break;
            case 'up':
                newRow = (currentRow - 1 + layout.length) % layout.length;
                newCol = Math.min(currentCol, rowLengths[newRow] - 1);
                break;
            case 'confirm':
                const key = layout[currentRow][currentCol];
                this._pressKey(key);
                // 按键动画
                const el = this.keyElements[this.focusedKeyIdx];
                if (el) {
                    el.classList.add('pressed');
                    setTimeout(() => el.classList.remove('pressed'), 100);
                }
                return;
            case 'back':
                this.close();
                return;
            case 'prevTab':
                // LB 切换键盘布局
                const layouts = ['alpha', 'num', 'sym'];
                const cur = layouts.indexOf(this.currentLayout);
                this.currentLayout = layouts[(cur - 1 + layouts.length) % layouts.length];
                this.focusedKeyIdx = 0;
                this._renderKeys();
                return;
            case 'nextTab':
                // RB 切换键盘布局
                const layoutsR = ['alpha', 'num', 'sym'];
                const curR = layoutsR.indexOf(this.currentLayout);
                this.currentLayout = layoutsR[(curR + 1) % layoutsR.length];
                this.focusedKeyIdx = 0;
                this._renderKeys();
                return;
        }

        // 计算新的扁平索引
        let newIdx = 0;
        for (let r = 0; r < newRow; r++) newIdx += rowLengths[r];
        newIdx += newCol;
        this.focusedKeyIdx = newIdx;
        this._updateFocusHighlight();
    }

    // ─── 开启/关闭 ────────────────────────────────────────────────────────────
    open(inputEl) {
        this.targetInput = inputEl;
        this.isVisible = true;
        this.focusedKeyIdx = 0;
        this.currentLayout = 'alpha';
        this.caps = false;
        this._renderKeys();
        this._updatePreview();
        this.container.classList.add('open');

        // 更新 label
        const label = this.container.querySelector('.gkb-label');
        if (label) label.textContent = inputEl.placeholder || inputEl.name || '输入中';
    }

    close() {
        if (!this.isVisible) return;
        this.isVisible = false;
        this.container.classList.remove('open');
        if (this.targetInput) {
            // 派发 change 事件，确保外部监听到输入完成
            this.targetInput.dispatchEvent(new Event('change', { bubbles: true }));
            this.targetInput.focus();
            this.targetInput = null;
        }
    }

    isOpen() { return this.isVisible; }

    // ─── 自动绑定输入框聚焦 ───────────────────────────────────────────────────
    _bindInputFocus() {
        document.addEventListener('focusin', (e) => {
            // 只在手柄已连接时自动弹出
            if (!window.GamepadController || !window.GamepadController.connected) return;
            const el = e.target;
            if ((el.tagName === 'INPUT' && el.type !== 'range' && el.type !== 'checkbox' && el.type !== 'radio')
                || el.tagName === 'TEXTAREA') {
                // 延迟一帧，避免与其他事件冲突
                setTimeout(() => {
                    if (document.activeElement === el) this.open(el);
                }, 50);
            }
        });

        document.addEventListener('focusout', (e) => {
            const el = e.target;
            if ((el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') && this.isVisible) {
                // 如果焦点移到键盘内部则不关闭
                setTimeout(() => {
                    if (!this.container.contains(document.activeElement)) {
                        // 不自动关闭，等用户按B或↵
                    }
                }, 100);
            }
        });
    }
}

// ─── 全局单例 ─────────────────────────────────────────────────────────────────
window.GamepadKeyboard = new GamepadVirtualKeyboard();
