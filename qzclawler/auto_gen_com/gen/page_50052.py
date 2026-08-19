def crawl_page(page) -> bool:
    """
    翻页函数，适配 Phoenix 自定义分页组件 (phoenix-pagination)
    返回:
        True  - 成功翻到下一页
        False - 已经是最后一页或出错
    """
    try:
        # ✅ 定位“下一页”按钮
        next_btn = page.query_selector("a.phoenix-pagination__pageButton--next")
        if not next_btn:
            print("[翻页] 未找到下一页按钮")
            return False

        # ✅ 判断是否被禁用（Phoenix 框架通常通过 class 控制禁用）
        is_disabled = "phoenix-pagination__pageButton--disabled" in next_btn.get_attribute("class")
        if is_disabled:
            print("[翻页] 下一页按钮已禁用，已到最后一页")
            return False

        # ✅ 获取当前页码（方便确认是否翻页成功）
        current_page_elem = page.query_selector("a.phoenix-pagination__numberButtonPure--clicked")
        current_page = current_page_elem.inner_text().strip() if current_page_elem else "未知"

        # ✅ 点击“下一页”
        next_btn.click()
        page.wait_for_timeout(2000)

        # ✅ 等待新页加载后确认页码是否变化
        new_page_elem = page.query_selector("a.phoenix-pagination__numberButtonPure--clicked")
        new_page = new_page_elem.inner_text().strip() if new_page_elem else "未知"

        if new_page == current_page:
            print(f"[翻页] 页码未变化，可能是最后一页（当前: {current_page}）")
            return False

        print(f"[翻页] 成功翻到第 {new_page} 页")
        return True

    except Exception as e:
        print(f"[翻页] 出错: {e}")
        return False
