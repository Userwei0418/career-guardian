def crawl_page(page):
    """
    点击“博士生招聘”标签
    """
    print("[翻页] 尝试点击博士生招聘")

    try:
        # 直接匹配 label 文本
        locator = page.locator("label:has-text('博士生招聘')")
        if locator.count() > 0:
            locator.first.click()
            print("成功点击博士生招聘")
            return True

        # 兜底匹配 span 或其他结构
        locator = page.locator("span:has-text('博士生招聘')")
        if locator.count() > 0:
            locator.first.click()
            print("成功点击博士生招聘（span 匹配）")
            return True

        print("未找到博士生招聘按钮")
        return False

    except Exception as e:
        print("点击博士生招聘异常:", e)
        return False
