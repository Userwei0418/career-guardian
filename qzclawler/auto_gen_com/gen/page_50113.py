def crawl_page(page):
    try:
        next_a = page.locator("li[jp-role='next'] > a")

        if next_a.count() == 0:
            print("没有找到下一页")
            return False

        # 判断父 li 是否被禁用
        parent_li = next_a.first.locator("xpath=..")
        cls = parent_li.get_attribute("class") or ""

        if "disabled" in cls:
            print("已经是最后一页")
            return False

        next_a.first.wait_for(state="visible")
        next_a.first.click()
        return True

    except Exception as e:
        print(f"翻页时出错: {e}")
        return False
