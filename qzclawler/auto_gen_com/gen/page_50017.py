def crawl_page(page, timeout=2000):
    """
    翻到下一页（只翻一页）。

    :param page: Playwright 页面对象
    :param timeout: 点击后等待时间（毫秒）
    :return: True 表示成功翻页，False 表示已经是最后一页或按钮不可用
    """
    next_btn = page.query_selector("button.btn-next")
    if next_btn and not next_btn.is_disabled():
        next_btn.click()
        page.wait_for_timeout(timeout)
        return True
    return False
