def crawl_page(page):
    """
    翻页函数：定位“下一页”按钮并点击。
    如果已经到最后一页或按钮不可点击，返回 False。
    """
    try:
        # 定位下一页按钮（根据 aria-label 或 data-ph-at-id）
        next_page_button = page.query_selector('[aria-label="Next"]')
        # 如果找不到按钮，说明可能已经是最后一页
        if not next_page_button:
            return False

        # 判断按钮是否可点击
        if next_page_button.is_enabled():
            next_page_button.click()
            return True
        else:
            # 按钮被禁用，说明已经到最后一页
            return False
    except Exception as e:
        print(f"翻页时出现错误: {e}")
        return False
