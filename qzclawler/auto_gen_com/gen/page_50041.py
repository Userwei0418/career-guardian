def crawl_page(page, action="next"):
    """
    爬取分页：支持 'next'、'prev' 或指定页码
    适配 kkpager 分页结构
    """
    # 等待分页区域出现
    page.wait_for_selector("span.pageBtnWrap")

    if action == "next":
        btn = page.locator("span.pageBtnWrap a[title='下一页']")
    elif action == "prev":
        btn = page.locator("span.pageBtnWrap span.disabled", has_text="&lt;")
    elif isinstance(action, int):
        # 如果传入页码数字
        btn = page.locator(f"span.pageBtnWrap a[title='第{action}页']")
    else:
        raise ValueError("action 必须是 'next'、'prev' 或 页码数字")

    # 检查按钮是否可点击
    if btn.count() == 0:
        print("没有找到分页按钮或已到边界页。")
        return False

    # 检查下一页是否禁用
    if action == "next":
        disabled = page.locator("span.pageBtnWrap span.disabled", has_text=">").count() > 0
        if disabled:
            print("已经是最后一页。")
            return False

    # 点击并等待页面加载
    btn.click()
    page.wait_for_load_state("networkidle")
    print(f"成功翻到 {action} 页。")
    return True
