def crawl_page(page):
    try:
        # 定位“下一页”按钮
        next_page_button = page.locator('button.ihr_pagination_side_btn--next')

        # 判断按钮是否存在且未被禁用
        if next_page_button.count() > 0:
            class_name = next_page_button.get_attribute("class") or ""
            if "disabled" not in class_name:
                next_page_button.click()
                page.wait_for_timeout(500)  # 等待页面刷新
                return True
    except Exception as e:
        print(f"翻页时出现错误: {e}")
    return False
