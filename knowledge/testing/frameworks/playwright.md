# Playwright 框架能力矩阵

> 本文档描述 Playwright 框架在 8 条脆弱层上的原生支持程度及对应 helper 实现。
> 在 Web（React / Vue / Next.js 等）项目中使用此文档。

## 框架能力矩阵

| 层 | native | helper | 说明 |
|---|---|---|---|
| element_discovery | partial | supplement | `locator()` 可靠，但无覆盖率检查；helper 补充 `SELECTOR_UNSTABLE` 标记 |
| button_trigger | partial | supplement | 无内置 enabled 状态前置检查；helper 在点击前验证可见且可交互 |
| gesture | covered | thin | `page.mouse`、`dragAndDrop()` 完善；helper 仅薄封装 |
| async_wait | partial | supplement | `waitForSelector` 可用但超时报错无业务语义；helper 补充有意义的错误信息 |
| system_dialog | covered | thin | `page.on('dialog')` 原生支持；helper 仅做注册封装 |
| keyboard_ime | covered | thin | `fill()` 处理 Unicode，桌面端无 IME 复杂性 |
| scroll_container | covered | thin | `scrollIntoViewIfNeeded()` 可靠 |
| cross_app | n/a | skip | Web 端无跨 App 场景 |

## Helper 实现（TypeScript）

helper 文件路径：使用 `tech-profile.json` 中对应 module 的 `helper_file` 字段
（如 `src/tests/helpers/ui_helper.ts`）

```typescript
import { Page, Locator } from '@playwright/test';

// element_discovery supplement
export async function findElement(page: Page, testId: string): Promise<Locator> {
  const el = page.getByTestId(testId);
  if (!await el.isVisible()) {
    throw new Error(`[SELECTOR_UNSTABLE] data-testid="${testId}" not found or not visible`);
  }
  return el;
}

// button_trigger supplement
export async function clickButton(page: Page, testId: string): Promise<void> {
  const el = page.getByTestId(testId);
  await el.waitFor({ state: 'visible' });
  const isDisabled = await el.isDisabled();
  if (isDisabled) {
    throw new Error(`[BUTTON_DISABLED] data-testid="${testId}" is disabled`);
  }
  await el.click();
}

// async_wait supplement
export async function waitForData(
  page: Page,
  testId: string,
  timeout = 5000
): Promise<void> {
  await page.waitForSelector(`[data-testid="${testId}"]`, {
    state: 'visible',
    timeout,
  }).catch(() => {
    throw new Error(
      `[ASYNC_WAIT] data-testid="${testId}" did not appear within ${timeout}ms. ` +
      `Check loading state or API response.`
    );
  });
}

// gesture thin
export async function dragTo(
  page: Page,
  sourceTestId: string,
  targetTestId: string
): Promise<void> {
  const source = page.getByTestId(sourceTestId);
  const target = page.getByTestId(targetTestId);
  await source.dragTo(target);
}

// system_dialog thin
export function setupDialogHandler(page: Page): void {
  page.on('dialog', async (dialog) => {
    await dialog.accept();
  });
}
```

## 代码节点生成规范

生成 UI 代码时，所有可交互元素（`<button>`、`<input>`、`<a>`、`<select>`、可点击 `<div>`）
必须加 `data-testid` 属性：

```tsx
// ✓ 正确：有稳定 data-testid
<button data-testid="submit-button" onClick={handleSubmit}>提交</button>
<input data-testid="email-input" type="email" value={email} />

// ✗ 错误：无稳定标识符
<button className="btn-primary" onClick={handleSubmit}>提交</button>
```
