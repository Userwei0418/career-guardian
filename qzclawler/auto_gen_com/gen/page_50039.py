def crawl_page(page, action="next"):
    """
    爬取分页：支持 'next' 和 'prev'
    """
    # 根据动作选择按钮
    if action == "next":
        btn = page.locator("li.next:not(.disabled)")  # 选择下一页按钮且未禁用
    elif action == "prev":
        btn = page.locator("li.prev:not(.disabled)")  # 选择上一页按钮且未禁用
    else:
        raise ValueError("action 必须是 'next' 或 'prev'")

    # 检查是否禁用
    classes = btn.get_attribute("class") or ""
    if "disabled" not in classes:
        btn.click()
        return True
    else:
        print("没有更多页了")
        return False
