def crawl_page(page, target_page_num):
    """
    Playwright 翻页到指定页码
    """
    locator = page.locator(f"ul.pagination li a[title='Page {target_page_num}']")
    if locator.count() > 0:
        locator.first.click()
        page.wait_for_timeout(1000)  # 等待页面刷新
        print(f"已跳转到第 {target_page_num} 页")
        return True
    else:
        print(f"没有找到第 {target_page_num} 页按钮")
        return False
