def crawl_page(page):
    try:
        # 定位下一页按钮，根据 class
        next_page_button = page.query_selector("a.page_a.page_next")
        if not next_page_button:
            print("找不到下一页按钮")
            return False

        # 判断按钮是否可点击
        class_name = next_page_button.get_attribute('class') or ""
        if 'disabled' in class_name or 'mtd-pagination-item-disabled' in class_name:
            print("已经是最后一页，停止翻页")
            return False

        # 点击下一页
        next_page_button.click()

        # 等待页面加载完成，视情况可以等待特定元素刷新
        page.wait_for_timeout(1000)  # 等待1秒，可改成 page.wait_for_selector(...)
        return True

    except Exception as e:
        print(f"翻页时出现错误: {e}")
        return False