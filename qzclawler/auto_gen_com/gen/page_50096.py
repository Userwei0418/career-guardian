def crawl_page(page):
    try:
        # 定位分页容器
        pagination = page.query_selector("ul.pagination")
        if not pagination:
            print("未找到分页容器")
            return False

        # 找到最后一个 li（通常是 '»'）
        next_li = pagination.query_selector("li:last-child")
        if not next_li:
            print("未找到下一页按钮")
            return False

        # 判断是否禁用
        class_attr = next_li.get_attribute("class") or ""
        if "disabled" in class_attr:
            print("已经是最后一页")
            return False

        # 获取 a 标签并点击
        next_a = next_li.query_selector("a")
        if next_a:
            href = next_a.get_attribute("href")
            page.goto(page.url.rsplit("/", 1)[0] + "/" + href.split("/")[-1])  # 直接跳转到下一页
            page.wait_for_load_state("networkidle")
            return True
        else:
            print("下一页链接不存在")
            return False

    except Exception as e:
        print(f"翻页出现异常: {e}")
        return False
