def crawl_page(page):
    """
    点击下一页按钮，只翻一页
    """
    # 获取当前页码（通过获取当前页的类名）
    current_page_element = page.query_selector("li.ant-pagination-item.ant-pagination-item-active a")

    if not current_page_element:
        print("未能找到当前页元素")
        return False

    current_page = int(current_page_element.inner_text())

    # 获取总页数，这里需要根据页面中存在的其他元素（如“跳至”）来判断
    # 如果页面中有固定的总页数，可以直接获取总页数
    total_page = 70  # 假设页面总共有 70 页（你可以根据实际情况来调整）

    if current_page >= total_page:
        print(f"已到达最后一页：{current_page}")
        return False  # 表示无法再翻页

    # 点击“下一页”按钮
    next_btn = page.query_selector("li.ant-pagination-next[aria-disabled='false']")

    if next_btn:
        next_btn.click()
        page.wait_for_timeout(1000)  # 等待页面刷新
        print(f"翻到下一页：{current_page + 1}")
        return True  # 表示成功翻页
    else:
        print("下一页按钮不可点击")
        return False
