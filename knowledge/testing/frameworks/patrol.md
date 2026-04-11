# Patrol 框架能力矩阵（Flutter）

> 本文档描述 Patrol 框架在 8 条脆弱层上的原生支持程度及对应 helper 实现。
> 在 Flutter 跨平台项目中使用此文档。

## 框架能力矩阵

| 层 | native | helper | 说明 |
|---|---|---|---|
| element_discovery | partial | supplement | Key/ValueKey 覆盖率通常不足；helper 补充多级降级链和 `SELECTOR_UNSTABLE` |
| button_trigger | partial | supplement | 无内置 enabled 状态检查；helper 补充 |
| gesture | partial | supplement | `tap`/`swipe` 有，但无稳定等待机制；helper 补充动画完成等待 |
| async_wait | partial | supplement | `pumpAndSettle()` 可用，但超时无业务语义；helper 补充 |
| system_dialog | covered | thin | `$.native.grantPermissionWhenInUse()` 原生支持 |
| keyboard_ime | uncovered | full | IME 组合态（中日文）无原生保护；helper 完整实现 |
| scroll_container | uncovered | full | 虚拟列表（ListView.builder）中元素未渲染时 `find` 失败；helper 完整实现 |
| cross_app | partial | supplement | `$.native` 支持跨 App，但状态验证需 helper 封装 |

## Helper 实现（Dart）

helper 文件路径：使用 `tech-profile.json` 中对应 module 的 `helper_file` 字段
（如 `integration_test/helpers/ui_helper.dart`）

```dart
import 'package:patrol/patrol.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class UIHelper {
  final PatrolIntegrationTester $;

  UIHelper(this.$);

  // element_discovery supplement
  Future<Finder> findElement(
    dynamic keyOrType, {
    Duration timeout = const Duration(seconds: 5),
  }) async {
    Finder finder;
    if (keyOrType is Key) {
      finder = find.byKey(keyOrType);
    } else if (keyOrType is Type) {
      finder = find.byType(keyOrType);
    } else {
      throw ArgumentError('[SELECTOR_UNSTABLE] Unsupported locator type');
    }

    final exists = await $.tester.pumpUntilFound(finder, timeout: timeout);
    if (!exists) {
      throw TestFailure('[SELECTOR_UNSTABLE] Element $keyOrType not found within $timeout');
    }
    return finder;
  }

  // keyboard_ime full
  Future<void> typeWithIME(Finder field, String text) async {
    await $.tester.tap(field);
    await $.tester.pump();
    await $.tester.enterText(field, text);
    await $.tester.pumpAndSettle(const Duration(milliseconds: 500));
    await $.tester.testTextInput.receiveAction(TextInputAction.done);
    await $.tester.pump();
  }

  // scroll_container full
  Future<void> scrollUntilVisible(
    Finder target,
    Finder scrollable, {
    double delta = 100,
    int maxScrolls = 10,
  }) async {
    var scrolls = 0;
    while (!$.tester.any(target) && scrolls < maxScrolls) {
      await $.tester.drag(scrollable, Offset(0, -delta));
      await $.tester.pump();
      scrolls++;
    }
    if (!$.tester.any(target)) {
      throw TestFailure('[SCROLL_CONTAINER] Target not found after $maxScrolls scrolls');
    }
  }

  // async_wait supplement
  Future<void> waitForLoading({
    Duration timeout = const Duration(seconds: 10),
  }) async {
    final loading = find.byType(CircularProgressIndicator);
    if ($.tester.any(loading)) {
      await $.tester.pumpUntilGone(loading, timeout: timeout);
    }
  }
}
```

## 代码节点生成规范

生成 Flutter UI 代码时，所有可交互 Widget 必须设置 `Key`：

```dart
// ✓ 正确
ElevatedButton(
  key: const Key('submit-button'),
  onPressed: handleSubmit,
  child: const Text('提交'),
)

// ✗ 错误
ElevatedButton(onPressed: handleSubmit, child: const Text('提交'))
```

## Widget 查找优先级

| 优先级 | 查找方式 | 示例 | 适用场景 |
|--------|---------|------|---------|
| 1 | Key | `find.byKey(Key('order_list'))` | Widget 有显式 Key（最稳定） |
| 2 | Type | `find.byType(OrderListPage)` | Widget 类型在页面内唯一 |
| 3 | Semantics | `find.bySemanticsLabel('订单')` | 有 Semantics 标签 |
| 4 | Text | `find.text('订单管理')` | 最后降级，多语言环境慎用 |
