def crawl_page(page, timeout=2000):
    """
    翻页（只翻一页）针对 <span class="p_next p_fun"><a>下页</a></span> 结构。
    :param page: Playwright 页面对象
    :param timeout: 点击后等待时间（毫秒）
    :return: True 成功翻页，False 已到最后一页
    """
    try:
        # 定位下页 <a> 元素
        next_link = page.locator('span.p_next.p_fun > a')

        if next_link.count() == 0 or not next_link.is_visible():
            # 没有 a 标签说明已经到最后一页
            return False

        next_link.click()
        page.wait_for_timeout(timeout)
        return True

    except Exception as e:
        print(f"翻页异常: {e}")
        return False
