from playwright.sync_api import Page

def crawl_page(page: Page) -> bool:
    """
    翻页函数，返回 True 表示翻到下一页成功，
    False 表示已经是最后一页或出错
    """
    try:
        # 查找下一页按钮，排除禁用状态
        next_button = page.query_selector('li.nextpage:not(.disabled) a')

        if next_button:
            next_button.click()
            # 等待页面刷新，可以换成等待新元素出现
            page.wait_for_timeout(1500)
            print("成功点击下一页按钮")
            return True
        else:
            print("没有可用的下一页按钮，已经是最后一页")
            return False

    except Exception as e:
        print(f"翻页时出错: {e}")
        return False
