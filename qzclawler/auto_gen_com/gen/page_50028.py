def crawl_page(page):
    """
    点击下一页按钮
    """
    next_btn = page.locator("button[aria-label='Go to next page']")
    if next_btn.is_enabled():
        next_btn.click()
        page.wait_for_timeout(1500)  # 等待页面刷新
        print("已翻到下一页")
        return True
    else:
        print("下一页按钮不可用，可能到最后一页了")
        return False
