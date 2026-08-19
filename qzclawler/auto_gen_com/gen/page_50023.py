def crawl_page(page, timeout=2000):
    """
    翻到下一页（只翻一页）。

    :param page: Playwright 页面对象
    :param timeout: 点击后等待时间（毫秒）
    :return: True 表示成功翻页，False 表示已经是最后一页或按钮不可用
    """
    # 定位下一页按钮
    next_btn = page.locator("button.btn-next")

    # 检查按钮是否存在且可用
    if next_btn.count() > 0 and next_btn.is_visible():
        # 检查 disabled 属性
        disabled_attr = next_btn.get_attribute("disabled")
        if disabled_attr is None:  # 没有 disabled 表示可以点击
            next_btn.click()
            page.wait_for_timeout(timeout)
            return True

    return False
