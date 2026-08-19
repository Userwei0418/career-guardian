def crawl_page(page) -> bool:
    """
    翻页函数，尝试点击“下一页”按钮。
    返回:
        True  - 成功翻到下一页
        False - 已经是最后一页或出错
    """
    try:
        # 定位下一页按钮
        next_a = page.query_selector("div.manu a.next")
        if not next_a:
            print("未找到下一页按钮")
            return False

        # 判断按钮是否禁用（这里用 class 或其他标记判断）
        if "disabled" in next_a.get_attribute("class") or next_a.get_attribute("aria-disabled") == "true":
            print("下一页按钮不可用，已经是最后一页")
            return False

        # 点击下一页
        next_a.click()
        page.wait_for_timeout(1500)  # 等待页面加载
        print("成功点击下一页")
        return True

    except Exception as e:
        print(f"翻页时出错: {e}")
        return False
