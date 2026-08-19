def crawl_page(page):
    try:
        # 定位“下一页”按钮（匹配 data-testid 或文本内容）
        next_btn = page.locator('button[data-testid="next-button"], button:has-text("下一页")')

        if next_btn.count() == 0:
            print("未找到下一页按钮")
            return False

        # 检查按钮是否禁用
        is_disabled = next_btn.get_attribute("disabled")
        aria_disabled = next_btn.get_attribute("aria-disabled")

        if is_disabled is not None or aria_disabled == "true":
            print("下一页按钮不可用，已到最后一页")
            return False

        # 可点击则执行翻页
        next_btn.click()
        print("点击下一页按钮成功，正在翻页...")
        page.wait_for_timeout(1500)  # 等待新内容加载
        return True

    except Exception as e:
        print(f"翻页异常: {e}")
        return False
