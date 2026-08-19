def crawl_page(page):
    """
    翻页函数，判断下一页按钮是否可以点击，若可以则进行点击
    返回:
        True  - 成功翻到下一页
        False - 已经是最后一页或出错
    """
    try:
        # 定位下一页按钮（通过 id="down" 或页面元素等）
        next_page_button = page.query_selector("a#down[pageindex]")

        if next_page_button:
            # 检查按钮是否禁用
            aria_disabled = next_page_button.get_attribute('aria-disabled')
            if aria_disabled == 'true':
                print("[翻页] 下一页按钮已禁用，可能是最后一页")
                return False

            # 如果按钮可用，则点击下一页
            next_page_button.click()
            page.wait_for_timeout(2000)  # 等待页面加载

            print("[翻页] 成功点击下一页")
            return True
        else:
            print("[翻页] 未找到下一页按钮")
            return False

    except Exception as e:
        print(f"翻页时出现错误: {e}")
        return False
