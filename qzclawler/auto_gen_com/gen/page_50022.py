def crawl_page(page) -> bool:
    """
    翻页函数，尝试点击“下一页”按钮。
    返回:
        True  - 成功翻到下一页
        False - 已经是最后一页或出错
    """
    try:
        # 查找“下一页”按钮（class 包含 next-next，并且没有 disabled）
        next_button = page.query_selector('button.next-next:not([disabled])')

        if next_button:
            next_button.click()
            page.wait_for_timeout(1500)  # 等待页面加载完成
            print("成功点击下一页")
            return True
        else:
            print("没有可用的下一页按钮，已经是最后一页")
            return False

    except Exception as e:
        print(f"翻页时出错: {e}")
        return False
