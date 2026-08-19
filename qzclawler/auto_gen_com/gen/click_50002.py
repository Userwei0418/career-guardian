def crawl_page(page):
    """
    点击“实习生”标签
    """
    print("[翻页] 尝试点击实习生")

    try:
        # 直接匹配 label 文本
        locator = page.locator("label:has-text('实习生')")
        if locator.count() > 0:
            locator.first.click()
            print("成功点击实习生")
            return True

        # 兜底匹配 span 或其他结构
        locator = page.locator("span:has-text('实习生')")
        if locator.count() > 0:
            locator.first.click()
            print("成功点击实习生（span 匹配）")
            return True

        print("未找到实习生按钮")
        return False

    except Exception as e:
        print("点击实习生异常:", e)
        return False
