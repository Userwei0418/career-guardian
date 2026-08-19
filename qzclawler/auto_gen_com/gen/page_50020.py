def crawl_page(page, timeout=2000):
    """
    翻到下一页（只翻一页）。

    :param page: Playwright 页面对象
    :param timeout: 点击后等待时间（毫秒）
    :return: True 表示成功翻页，False 表示已经是最后一页或按钮不可用
    """
    # 定位下一页按钮
    next_btn = page.locator("nav.pagination .next")

    if next_btn.count() > 0 and next_btn.is_visible():
        # 检查 class 是否包含 disabled
        class_attr = next_btn.get_attribute("class") or ""
        if "disabled" not in class_attr:
            next_btn.click()
            page.wait_for_timeout(timeout)
            return True

    return False
