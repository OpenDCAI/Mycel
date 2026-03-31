# Mycel Design System Spec

> Single source of truth for UI conventions. All new components and pages must follow this spec.
> Token values are defined in code — this document specifies **when and how** to use them.

---

## 1. Color

### Semantic Tokens

All colors are CSS custom properties in HSL (no `hsl()` wrapper) for Tailwind alpha compositing.

| Token | HSL | Hex | Usage |
|-------|-----|-----|-------|
| `--background` | `0 0% 100%` | `#ffffff` | Page background |
| `--foreground` | `0 0% 9%` | `#171717` | Primary text |
| `--foreground-secondary` | `0 0% 32%` | `#525252` | Secondary text (descriptions, metadata) |
| `--muted` | `0 0% 96%` | `#f5f5f5` | Subtle backgrounds (input, card hover) |
| `--muted-foreground` | `0 0% 45%` | `#737373` | Placeholder, disabled text |
| `--card` | `0 0% 100%` | `#ffffff` | Card, popover surface |
| `--border` | `0 0% 91%` | `#e8e8e8` | Borders, dividers |
| `--primary` | `0 0% 9%` | `#171717` | Primary action (buttons, links) |
| `--accent` | `0 0% 96%` | `#f5f5f5` | Hover highlight |
| `--destructive` | `0 84% 60%` | `#ef4444` | Error, danger, delete |
| `--success` | `160 84% 39%` | `#10b981` | Success, online, healthy |
| `--warning` | `38 92% 50%` | `#f59e0b` | Warning, attention |
| `--info` | `199 89% 48%` | `#0ea5e9` | Informational, active, highlight |

### Neutral Palette

Hue `0` (pure gray). No blue-tinted Slate — all grays are neutral.

### Rules

- **Use semantic tokens only.** Write `text-foreground`, `bg-muted`, `text-success` — never raw hex, Tailwind palette colors (`gray-500`, `green-400`), or unnamed HSL values.
- **Alpha compositing.** `destructive`, `success`, `warning` support `<alpha-value>`: `bg-success/10`, `text-destructive/80`.
- **Status colors** have `-foreground` variants for text on colored backgrounds: `bg-success text-success-foreground`.

### Do / Don't

```
text-success              -- use semantic token
text-[#10b981]            -- never: raw hex

bg-destructive/10         -- use alpha compositing
bg-red-50                 -- never: Tailwind palette

border-success/20         -- use token + alpha
border-green-200          -- never: named palette
```

---

## 2. Typography

### Font Stack

```
Body: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Noto Sans SC", sans-serif
Code: "SF Mono", "Fira Code", "Fira Mono", "Roboto Mono", Menlo, Consolas, monospace
```

### Size Scale

| Class | Size | Line Height | Usage |
|-------|------|-------------|-------|
| `text-3xs` | 8px / 0.5rem | 12px | Micro labels (rare) |
| `text-2xs` | 10px / 0.625rem | 14px | Badges, status indicators, compact metadata |
| `text-xs` | 12px / 0.75rem | 16px | Secondary text, metadata, help text |
| `text-sm` | 14px / 0.875rem | 20px | **Default body text**, form inputs, list items |
| `text-base` | 16px / 1rem | 24px | Prominent body, textarea content |
| `text-lg` | 18px / 1.125rem | 28px | Section headings |
| `text-xl` | 20px / 1.25rem | 28px | Page sub-headings |
| `text-2xl` | 24px / 1.5rem | 32px | Page titles |

### Rules

- Default body size is `text-sm` (14px). Use `text-base` only for prominent input areas.
- Heading hierarchy: `text-2xl` page title > `text-xl`/`text-lg` section > `text-sm font-medium` sub-section.
- `font-mono` for: code blocks, file paths, version numbers, API keys, technical identifiers.
- Letter spacing: `-0.011em` on body (set globally), `-0.02em` on `.font-mono`.

---

## 3. Spacing

### Base Unit: 4px

| Value | px | Tailwind | Usage |
|-------|-----|---------|-------|
| 1 | 4px | `gap-1`, `p-1` | Tight internal (icon-text gap) |
| 2 | 8px | `gap-2`, `p-2` | Default inline spacing |
| 3 | 12px | `gap-3`, `p-3` | Card internal padding, form group gap |
| 4 | 16px | `gap-4`, `p-4` | Section gap, card padding |
| 6 | 24px | `gap-6`, `p-6` | Between sections |
| 8 | 32px | `gap-8`, `p-8` | Major page sections |

### Rules

- Stick to the allowed set: 4 / 8 / 12 / 16 / 24 / 32 / 40 / 48px.
- Tight within a group, loose between groups.
- Same component type keeps the same internal spacing everywhere.

### Border Radius

| Token | Value | Usage |
|-------|-------|-------|
| `rounded-xs` | 2px | Tiny elements |
| `rounded-sm` | 4px | Badges, inline chips |
| `rounded-md` | 6px | Input fields, small cards |
| `rounded-lg` | 8px (`--radius`) | Standard cards, buttons |
| `rounded-xl` | 12px | Large cards, panels |
| `rounded-2xl` | 16px | Hero cards, input boxes |
| `rounded-full` | 9999px | Avatars, circular buttons |

---

## 4. Motion

### Duration Tokens

| Token | CSS Var | Value | Tailwind | Usage |
|-------|---------|-------|----------|-------|
| instant | `--duration-instant` | 100ms | `duration-instant` | Micro-feedback (hover, focus ring) |
| fast | `--duration-fast` | 150ms | `duration-fast` | Button state, tooltip, page-in |
| normal | `--duration-normal` | 250ms | `duration-normal` | Fade, slide, standard transitions |
| slow | `--duration-slow` | 400ms | `duration-slow` | Slide-up, panel open/close |
| deliberate | `--duration-deliberate` | 600ms | `duration-deliberate` | Complex reveals, staggered lists |

### Easing Tokens

| Token | CSS Var | Tailwind | Usage |
|-------|---------|----------|-------|
| default | `--ease-default` | `ease-smooth` | Standard transitions |
| out | `--ease-out` | `ease-out-expo` | Enter animations |
| in | `--ease-in` | `ease-in-expo` | Exit animations |
| in-out | `--ease-in-out` | `ease-io` | Symmetric motions, pulse |
| spring | `--ease-spring` | `ease-spring` | Playful overshoot (popover, scale) |

### Transform Distance

| Token | Value | Usage |
|-------|-------|-------|
| `--move-xs` | 2px | Micro shifts |
| `--move-sm` | 4px | Fade-in offset |
| `--move-md` | 8px | Slide enter/exit |
| `--move-lg` | 16px | Large panel slide |
| `--scale-subtle` | 0.97 | Overlay scale-in |
| `--scale-sm` | 0.95 | Button press |

### Animation Presets

Use class names directly. Prefer `motion-*` names; `animate-*` aliases exist for backward compatibility.

| Class | Animation | Duration | Usage |
|-------|-----------|----------|-------|
| `motion-fade-in` | translateY(4px) + opacity | normal (250ms) | Default content enter |
| `motion-slide-in-left` | translateX(-8px) + opacity | normal (250ms) | Side panel enter |
| `motion-slide-up` | translateY(8px) + opacity | slow (400ms) | Message appear |
| `motion-scale-in` | scale(0.97) + opacity | fast (150ms) | Popover, overlay |
| `motion-page-in` | translateY(4px) + opacity | fast (150ms) | Page route enter |
| `motion-pulse` | opacity 1→0.4→1 | 2s loop | Loading skeleton |
| `motion-fade-in-up` | translateY(16px) + opacity | slow (400ms) | Hero content enter |

### Transition Pattern (inline)

For interactive state changes, use Tailwind utilities:

```
transition-colors duration-fast          -- hover color change
transition-[border-color,box-shadow] duration-fast  -- focus ring
transition-transform duration-fast ease-spring      -- press scale
transition-opacity duration-normal       -- visibility toggle
```

### Reduced Motion

All `motion-*` and `animate-*` classes collapse to `0.01ms` under `prefers-reduced-motion: reduce`.

### UX Timing Constants (JS)

These are **not** motion tokens. Import from `@/styles/ux-timing`.

| Constant | Value | Usage |
|----------|-------|-------|
| `FEEDBACK_BRIEF` | 1500ms | Copy confirmation, save flash |
| `FEEDBACK_NORMAL` | 2000ms | Toast display, status message |
| `BLUR_CLOSE_DELAY` | 150ms | Dropdown close delay on blur |

### Rules

- Every `transition-*` must have an explicit `duration-*`. No bare `transition` (browser default 0s is invisible; 150ms is too implicit).
- Enter = `ease-out` (decelerate). Exit = `ease-in` (accelerate). Symmetric = `ease-in-out`.
- Do not invent new keyframes. Use presets or compose with `transition-*` utilities.

---

## 5. Status Patterns

Four semantic statuses: `success`, `warning`, `destructive`, `info`.

### Visual Treatments

| Treatment | Example | When |
|-----------|---------|------|
| **Dot** | `w-2 h-2 rounded-full bg-success` | Inline status indicator (online, connected) |
| **Text** | `text-success` | Status labels, counts |
| **Badge** | `bg-success/10 text-success rounded-sm px-1.5 py-0.5 text-2xs` | Tag-style status |
| **Background tint** | `bg-destructive/10 border-destructive/20` | Section-level alert |
| **On colored bg** | `bg-success text-success-foreground` | Filled badge, button |

### Rules

- Use `text-destructive` for errors/danger, `text-success` for healthy/online, `text-warning` for caution, `text-info` for active/highlighted.
- For tinted backgrounds: `bg-{status}/10` with `border-{status}/20` and `text-{status}`.
- Never mix status colors for decoration. Status color = semantic meaning.

---

## 6. Component Conventions

### Buttons

Use shadcn `<Button>` from `@/components/ui/button` for all visible action buttons.

| Variant | Usage |
|---------|-------|
| `default` | Primary action (bg-primary) |
| `destructive` | Delete, remove, danger |
| `outline` | Secondary action |
| `ghost` | Tertiary, toolbar |
| `link` | Inline text link |

Sizes: `default` (h-9), `sm` (h-8), `lg` (h-10), `icon` (h-9 w-9), `icon-sm` (h-8 w-8).

Raw `<button>` is acceptable only for: custom toggle switches, inline text actions inside tight layouts, custom composite controls where shadcn Button doesn't fit.

### Toggle Switches

No standard switch component enforced yet. Existing hand-built toggles (w-8/w-9, small thumb) remain. When building new toggles, prefer shadcn `<Switch>` from `@/components/ui/switch`.

### Forms

- Use shadcn `<Input>`, `<Textarea>`, `<Select>`, `<Label>`.
- Show constraints before submit (format, required). Error messages inline, not toast-only.

### Empty / Loading / Error States

Write inline. No wrapper component required. Pattern:

```tsx
// Loading
<div className="flex-1 flex items-center justify-center">
  <Spinner size="md" />
</div>

// Empty
<div className="text-center py-8">
  <p className="text-sm text-muted-foreground">暂无数据</p>
</div>

// Error
<div className="text-center py-8">
  <p className="text-sm text-destructive">{error}</p>
</div>
```

---

## 7. Language

### Primary: Chinese (Simplified)

All user-facing UI copy is in Chinese: labels, placeholders, tooltips, toasts, empty states, error messages.

### English Exceptions

Keep these terms in English — they are domain vocabulary:

| Term | Reason |
|------|--------|
| Agent | Core domain concept |
| MCP | Protocol name |
| API / API Key | Technical standard |
| System Prompt | AI domain |
| Token | AI/auth domain |
| Docker / E2B / Daytona / AgentBay | Product names |
| Thread | Internal ID, not shown to users as label |

### Rules

- Button labels: Chinese verb (`发送`, `取消`, `确定`, `删除`, `保存`).
- Status: Chinese (`运行中`, `已暂停`, `已停止`, `已连接`, `未连接`).
- Placeholders: Chinese (`例如: ~/Projects`, `告诉 Mycel 你需要什么帮助...`).
- Error messages: Chinese, actionable (`发布失败，请重试`).
- Log/console messages: English is acceptable (developer-facing).

---

## 8. Do / Don't

### Color

```diff
+ text-muted-foreground
- text-gray-500

+ bg-success/10 text-success
- bg-green-100 text-green-600

+ border-border
- border-[#e5e7eb]
```

### Motion

```diff
+ transition-colors duration-fast
- transition duration-150

+ className="motion-fade-in"
- style={{ animation: "fadeIn 0.25s ease" }}

+ FEEDBACK_BRIEF (from ux-timing.ts)
- setTimeout(fn, 1500)  // magic number
```

### Typography

```diff
+ text-sm text-muted-foreground
- text-[13px] text-[#666]

+ font-mono (for paths, versions, code)
- font-mono (for body text)
```

### Spacing

```diff
+ gap-3 p-4         (12px, 16px — on scale)
- gap-[13px] p-[18px]  (off scale)

+ space-y-2         (consistent group spacing)
- mb-2 mt-3 mb-1    (ad-hoc, inconsistent)
```

### Language

```diff
+ 发送
- Send

+ 运行中
- RUNNING

+ System Prompt     (domain term, keep English)
- 系统提示词        (acceptable but not required for technical terms)
```
