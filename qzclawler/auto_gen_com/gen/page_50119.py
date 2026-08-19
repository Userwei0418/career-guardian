def crawl_page(page, timeout=2000):
    """
    翻页（只翻一页）针对 <div class="next left" name="nextPage">下一页</div> 结构。
    :param page: Playwright 页面对象
    :param timeout: 点击后等待时间（毫秒）
    :return: True 成功翻页，False 已到最后一页
    """
    try:
        # 定位下一页 <div> 元素
        next_link = page.locator('div.next.left[name="nextPage"]')

        # 检查下一页按钮是否存在且可见
        if next_link.count() == 0 or not next_link.is_visible():
            # 没有下一页元素说明已经到最后一页
            return False

        # 获取当前页码信息
        current_page_items = page.locator('ul[name="pageList"] li.cur')
        total_page_items = page.locator('ul[name="pageList"] li')

        # 如果能获取到页码信息，可以通过比较判断是否为最后一页
        if current_page_items.count() > 0 and total_page_items.count() > 0:
            # 获取当前页码
            current_text = current_page_items.first.text_content().strip()
            # 获取总页数
            total_pages = total_page_items.count()

            # 如果当前页是最后一页，则停止翻页
            if current_text.isdigit() and int(current_text) == total_pages:
                return False

        next_link.click()
        page.wait_for_timeout(timeout)
        return True

    except Exception as e:
        print(f"翻页异常: {e}")
        return False
