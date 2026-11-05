# 玻璃拟态样张（独立）

不依赖 Flask、Tailwind、构建产物，直接双击 `index.html` 就能看。

- 背景：`bg.jpg`（西江千户苗寨夜景，取自站点图片，仅样张使用）
- 截图：`docs/shots/glass/`（1440 首屏 / 1440 整页 / 375 首屏 / 375 卡片）
- 生成：`node scripts/shot_glass.cjs`（Playwright，file:// 打开）

## 玻璃配方

| 项 | 值 |
|---|---|
| 背景 | `linear-gradient(135deg, rgba(255,255,255,.12), transparent 42%)` + `rgba(20,42,36,.58)` → `rgba(14,42,36,.34)` |
| 模糊 | `backdrop-filter: blur(20px) saturate(160%)`（含 `-webkit-` 前缀） |
| 描边 | `1px solid rgba(255,255,255,.16)` |
| 阴影 | `0 24px 64px rgba(0,0,0,.38)` + 内高光 `inset 0 1px 0 rgba(255,255,255,.16)` |
| 颗粒 | SVG `feTurbulence` 覆盖 5%，`mix-blend-mode: overlay` |
| 降级 | `@supports not (backdrop-filter...)` → 实色 `rgba(14,42,36,.88)` |
| 动效 | 仅 hover `translateY(-2px)`，`prefers-reduced-motion` 关闭 |

## 映射回站点（如果要做）

1. `input.css` 里新增 `.glass` / `.glass-soft` 组件类（配方同上）
2. 套用位置：`.ai-panel`、`.mobile-menu`、`.flash`
3. 重新构建并提交 `app/static/css/app.css`
4. 回归：1440 / 375 / 英文版截图，文字对比度 ≥ 4.5:1

后端零改动：纯 CSS，不涉及路由、模型、数据库。

## 实验 A：smoothscroll（隔离，尚未进正式站）

参考站 `https://paii.dpdns.org/` 是 WordPress + Sakurairo 主题，自带 `js/smoothscroll.js`（iamdustan smoothscroll，桌面 Chrome/Safari 劫持滚轮做惯性，移动端不动）。这里把同一份脚本放进样张做 A/B：

- `smoothscroll.js`：原版 7.4KB
- 启用条件：`pointer: fine` + 非移动 UA + 非 `prefers-reduced-motion` + 非 `?native=1`
- 排除：`.ai-msgs, input, textarea, select`（捕获阶段 `stopPropagation`，内部滚动不被劫持）
- 开关：`index.html`（平滑动效）↔ `index.html?native=1`（原生）
- 参数：`frameRate 144 / animationTime 600 / stepSize 100 / pulseAlgorithm`

### 自动探测

`node scripts/probe_smooth.cjs`（Playwright，file://），结果：

| 项 | smooth | native |
|---|---|---|
| 脚本加载 | ✅ | — |
| 锚点 `#cards` 落点 | 距顶 **96px**（不被导航挡） | 96px |
| PageDown 120ms 时位置 | **165**（渐进） | 517（瞬间跳） |
| PageDown 终点 | 804 | 703 |
| AI 面板内滚动 | 面板 200 / 页面 0 ✅ | 同左 |
| 滚动帧率（headless） | **35fps** | 49fps |
| reduced-motion | 不加载 ✅ | — |
| iPhone UA | 不加载 ✅ | — |

## 实验 A+：滚动入场（临界点主动滑上来）

滚轮惯性之外，补上“卡片到临界点自己滑上来”的入场动画：

- 初始：`opacity: 0; translateY(56px) scale(.985)`
- 触发：`IntersectionObserver`，元素进入视口**下缘 14%** 时
- 动画：`800ms cubic-bezier(.16,1,.3,1)`，只播一次
- 错峰：一排 3 张依次 `0 / 90 / 180ms`
- `prefers-reduced-motion`：直接显示，无位移无过渡

`docs/shots/glass/reveal-mid-1440.png` / `reveal-settled-1440.png` 是触发 120ms 与稳定后的对照。

### 结论

- 功能正确：锚点、键盘、内部滚动排除、两种开关都符合预期。
- **帧率是唯一风险**：headless 下平滑模式 35fps、原生 49fps（无 GPU，数字有噪声）。原因可能是劫持滚轮把滚动从合成器搬到主线程，而样张有固定模糊背景 + 玻璃面板。
- 需要你在**真机浏览器**滚一次：`docs/glass-demo/index.html` 对比 `index.html?native=1`；若明显掉帧，先试 `frameRate 60 / animationTime 500 / stepSize 80`，或只给首页启用。
- 正式站尚未接入，`app/` 零改动。
