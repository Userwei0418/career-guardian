def crawl_page(page) -> bool:
    """
    翻页函数：针对页面存在多个分页器（顶部+底部）的情况。
    默认点击最后一个分页器的“下一页”按钮。
    适配 ElementUI 结构。
    """
    try:
        # 1️⃣ 定位所有未禁用的下一页按钮
        next_buttons = page.locator('button.btn-next:not([disabled])')

        # 判断是否存在可点击按钮
        if next_buttons.count() == 0:
            print("[日志] 所有下一页按钮均禁用，爬取结束。")
            return False

        # 2️⃣ 点击最后一个分页器的按钮（最常见为底部分页）
        next_buttons.last.click()
        page.wait_for_timeout(1500)
        print("[日志] 成功点击底部分页器的下一页。")

        return True

    except Exception as e:
        print(f"[错误] 翻页时出现异常: {e}")
        return False