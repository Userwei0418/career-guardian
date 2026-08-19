def crawl_page(page):
    try:
        # 定位“下一页”按钮
        next_page_button = page.locator("li.atsx-pagination-next")

        if next_page_button.count() > 0:
            # 检查是否禁用
            aria_disabled = next_page_button.get_attribute("aria-disabled")
            if aria_disabled != "true":
                next_page_button.click()
                page.wait_for_timeout(500)  # 等待页面刷新
                return True
    except Exception as e:
        print(f"翻页时出现错误: {e}")
    return False
