def crawl_page(page) -> bool:
    """
    翻页函数，返回 True 表示翻到下一页成功，
    False 表示已经是最后一页或出错
    """
    try:
        # 查找可用的"下一页"按钮
        next_button = page.query_selector('button.sd-Pagination-forward-3z80f:not([disabled])')

        if next_button:
            next_button.click()
            page.wait_for_timeout(1500)  # 等待页面加载完成
            print("成功点击下一页按钮")
            return True
        else:
            print("没有可用的下一页按钮，已经是最后一页")
            return False

    except Exception as e:
        print(f"翻页时出错: {e}")
        return False
