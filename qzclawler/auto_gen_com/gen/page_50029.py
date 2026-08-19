def crawl_page(page):
    try:
        # 根据文本定位“下一页”
        next_page_button = page.get_by_text("下一页", exact=True)

        if next_page_button and next_page_button.is_visible():
            class_name = next_page_button.get_attribute("class") or ""

            # 检查是否有禁用状态
            if "disabled" not in class_name and "mtd-pagination-item-disabled" not in class_name:
                next_page_button.click()
                page.wait_for_timeout(500)  # 等待页面刷新
                return True
    except Exception as e:
        print(f"翻页时出现错误: {e}")
    return False
