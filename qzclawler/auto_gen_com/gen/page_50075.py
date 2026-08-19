def crawl_page(page):
    try:
        # 定位下一页按钮（支持 a 或 button 标签）
        next_btn = page.locator('a[title="Go to next page"], button[data-testid="next-button"], button:has-text("下一页")')

        if next_btn.count() == 0:
            print("未找到下一页按钮")
            return False

        # 判断按钮是否不可用
        is_disabled = next_btn.get_attribute("disabled")
        aria_disabled = next_btn.get_attribute("aria-disabled")
        class_disabled = "disabled" in (next_btn.get_attribute("class") or "")

        if is_disabled is not None or aria_disabled == "true" or class_disabled:
            print("下一页按钮不可用，已到最后一页")
            return False

        # 点击下一页
        next_btn.click()
        print("点击下一页按钮成功，正在翻页...")

        # 等待新内容加载（更稳健）
        page.wait_for_load_state("networkidle")
        return True

    except Exception as e:
        print(f"翻页异常: {e}")
        return False
