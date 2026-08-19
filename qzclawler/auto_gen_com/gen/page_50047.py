def crawl_page(page) -> bool:
    """
    翻页函数，尝试点击“下一页”按钮。
    返回:
        True  - 成功翻到下一页
        False - 已经是最后一页或出错
    """
    try:
        # 定位下一页按钮 li
        next_li = page.query_selector("ul.ant-pagination li.ant-pagination-next")
        if not next_li:
            print("未找到下一页按钮")
            return False

        # 判断按钮是否被禁用
        disabled = next_li.get_attribute("aria-disabled")
        if disabled == "true":
            print("下一页按钮不可用，已经是最后一页")
            return False

        # 点击按钮
        button = next_li.query_selector("button")
        if button:
            button.click()
            page.wait_for_timeout(1500)  # 等待页面加载
            print("成功点击下一页")
            return True
        else:
            print("下一页按钮内没有找到 button 元素")
            return False

    except Exception as e:
        print(f"翻页时出错: {e}")
        return False
