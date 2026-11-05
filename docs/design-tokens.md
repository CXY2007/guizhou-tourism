# 设计 Tokens

- 版本：v1.0（D1 冻结）
- 方向：沉浸式大图叙事 · 山水留白 · 克制的东方感
- 原则：**图优先、字克制、动效轻**。任何装饰不得压过照片；任何动效不得影响阅读。

---

## 1. 色彩

| Token | 值 | 用途 |
|---|---|---|
| `ink` | `#0E2A24` | 主文字、深色底、导航 |
| `teal` | `#1F4E5A` | 次主色、链接、按钮悬停、AI 小球 |
| `cinnabar` | `#B83A2D` | 强调色、主按钮、评分星、当前态 |
| `paper` | `#F4EFE6` | 页面底色、浅色卡片 |
| `gold` | `#C9A227` | 分隔线、徽标、少量点缀（≤5% 面积） |
| `mist` | `#8FA6A0` | 次要文字、占位、禁用 |
| `white` | `#FFFFFF` | 卡片、浮层 |
| `success` | `#2E7D5B` | 成功提示 |
| `warning` | `#B7791F` | 警告 |
| `danger` | `#B83A2D` | 错误（与朱砂同值，语义区分） |

**用法约束**
- 页面 80% 面积由照片/留白构成，深色块不超过 30%。
- 朱砂只用于“可点击/当前/重要”，不用于大面积背景。
- 深色底上的文字对比度 ≥ 4.5:1；标题需加 0–40% 黑色渐变遮罩。

## 2. 字体

| 角色 | 字体栈 | 字号 / 行高 |
|---|---|---|
| Display | `"Noto Serif SC", "Songti SC", "STSong", serif` | 64/72 · 48/56 · 38/46 |
| Heading | 同 Display | 30/38 · 24/32 |
| Body | `Inter, "PingFang SC", "Microsoft YaHei", system-ui, sans-serif` | 18/30 · 16/28 · 14/24 |
| Caption | 同 Body | 12/18，字距 0.04em |
| Numeric | `Inter`，`font-variant-numeric: tabular-nums` | 票价、评分、计数 |

- 中文标题不加字距；英文全大写标题加 `0.08em`。
- 正文最大宽度 68ch；移动端 100%。

## 3. 间距与栅格

- 基准：4px。序列：`4 8 12 16 24 32 48 64 96 128`
- 容器：`max-width 1280px`，左右 `24px`（移动）/ `48px`（桌面）
- 栅格：12 列， gutter 24px；卡片桌面 4 列 / 平板 3 列 / 手机 1 列
- 区块垂直节奏：移动 `64px`，桌面 `96–128px`

## 4. 圆角 / 阴影 / 描边

| Token | 值 | 用途 |
|---|---|---|
| `radius-sm` | 4px | 标签、输入 |
| `radius-md` | 8px | 按钮、小卡片 |
| `radius-lg` | 16px | 卡片、面板 |
| `radius-xl` | 24px | 大图容器、抽屉 |
| `radius-full` | 999px | 胶囊、AI 小球 |
| `shadow-sm` | `0 1px 2px rgba(14,42,36,.08)` | 浮起 |
| `shadow-md` | `0 8px 24px rgba(14,42,36,.12)` | 卡片悬停 |
| `shadow-lg` | `0 24px 64px rgba(14,42,36,.18)` | 弹层 |
| `border` | `1px solid rgba(14,42,36,.12)` | 分隔 |

## 5. 动效

| 场景 | 时长 | 缓动 |
|---|---|---|
| 悬停/按压 | 150–200ms | `cubic-bezier(.22,1,.36,1)` |
| 出现/离场 | 250–400ms | 同上 |
| 滚动 reveal | 600ms | 位移 12–24px + 透明度 0→1，`once` |
| 首屏 Ken Burns | 18–24s | `ease-in-out`，scale 1→1.06 |
| 页面转场 | 300ms | 淡入 + 轻微上移 |

- 全部动效在 `prefers-reduced-motion: reduce` 下关闭位移与缩放，只保留透明度。
- 不在滚动中触发重排；用 `transform` / `opacity`。

## 6. 组件规范

| 组件 | 规范 |
|---|---|
| 主按钮 | 朱砂底 + 白字，高 44px，圆角 8px，hover 加深 8% |
| 次按钮 | 透明底 + ink 描边，hover 填充 ink/5 |
| 景点卡 | 图 4:3，底部渐变遮罩，标题 Display 24，副信息 14 |
| 标签 | 胶囊，`rgba(255,255,255,.14)` 底 + 白字，12px |
| 导航 | 首屏透明白字；滚动 80px 后变 `paper/90` + 毛玻璃 |
| 搜索框 | 高 40px，圆角 full，聚焦 2px teal ring |
| AI 小球 | 60px，teal→ink 渐变，hover 放大 1.05，展开面板 360×520 |
| 评分星 | 20px，朱砂填充，未选中 `mist` |
| 表单 | 输入高 44px，1px 描边，聚焦 teal ring，错误态 danger 文案 |

## 7. 图片规范

| 用途 | 比例 | 最小宽度 | 格式 |
|---|---|---|---|
| 首屏 Hero | 16:9 | 2400px | WebP q80 + JPEG 兜底 |
| 详情图集 | 4:3 / 3:2 | 1600px | WebP |
| 卡片封面 | 4:3 | 1200px | WebP |
| 缩略图 | 1:1 | 320px | WebP |

- `srcset`：480 / 960 / 1440 / 1920；`loading="lazy"`（首屏除外）、`decoding="async"`。
- 首屏 LQIP：20px 模糊占位，加载完淡入。
- 所有图片必须有 `alt`；纯装饰图 `alt=""`。

## 8. 可访问性

- 正文对比度 ≥ 4.5:1，大字号 ≥ 3:1。
- 键盘可达：焦点环 `2px teal`，`outline-offset: 2px`。
- 语义标签：`header/nav/main/section/footer`，标题层级不跳级。
- AI 回复区 `aria-live="polite"`；加载态 `aria-busy="true"`。
- 表单错误用文字 + `aria-invalid`，不只靠颜色。

## 9. Tailwind 映射（v3 示例）

```js
// tailwind.config.js
module.exports = {
  content: ['./app/templates/**/*.html', './app/static/js/**/*.js'],
  theme: {
    extend: {
      colors: {
        ink: '#0E2A24', teal: '#1F4E5A', cinnabar: '#B83A2D',
        paper: '#F4EFE6', gold: '#C9A227', mist: '#8FA6A0',
      },
      fontFamily: {
        display: ['"Noto Serif SC"', '"Songti SC"', 'serif'],
        body: ['Inter', '"PingFang SC"', '"Microsoft YaHei"', 'system-ui', 'sans-serif'],
      },
      borderRadius: { sm: '4px', md: '8px', lg: '16px', xl: '24px' },
      boxShadow: {
        sm: '0 1px 2px rgba(14,42,36,.08)',
        md: '0 8px 24px rgba(14,42,36,.12)',
        lg: '0 24px 64px rgba(14,42,36,.18)',
      },
      transitionTimingFunction: { smooth: 'cubic-bezier(.22,1,.36,1)' },
    },
  },
};
```

> 若使用 Tailwind v4（CSS-first），把上述 token 写进 `@theme { --color-ink: #0E2A24; ... }`，语义不变。
