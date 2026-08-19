def crawl_page(page) -> bool:
    """
    翻页函数，尝试点击“下一页”按钮。
    返回:
        True  - 成功翻到下一页
        False - 已经是最后一页或出错
    """
    try:
        # 定位分页容器
        pagination = page.query_selector("div.CareerList_CareerListPagination__zxrPp")
        if not pagination:
            print("未找到分页容器，可能是单页或页面结构变化")
            return False

        # 查找“下一页”箭头（第 2 个 i 标签为下一页）
        arrows = pagination.query_selector_all("i")
        if len(arrows) < 2:
            print("分页箭头数量异常")
            return False

        next_arrow = arrows[1]
        # 判断按钮是否被禁用
        next_class = next_arrow.get_attribute("class") or ""
        if "ArrowDisabled" in next_class:
            print("下一页按钮不可用，已经是最后一页")
            return False

        # 点击下一页
        next_arrow.click()
        page.wait_for_timeout(1500)  # 等待页面加载
        print("成功点击下一页")
        return True

    except Exception as e:
        print(f"翻页时出错: {e}")
        return False
