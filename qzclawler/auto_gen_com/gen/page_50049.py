def crawl_page(page) -> bool:
    """
    翻页函数，适配 paginationjs 组件。
    返回:
        True  - 成功翻到下一页
        False - 已经是最后一页或出错
    """
    try:
        # ✅ 定位下一页 li 元素
        next_li = page.query_selector("li.paginationjs-next")

        if not next_li:
            print("[翻页] 未找到下一页按钮")
            return False

        # ✅ 判断是否禁用
        next_class = next_li.get_attribute("class") or ""
        if "disabled" in next_class:
            print("[翻页] 下一页按钮已禁用，可能是最后一页")
            return False

        # ✅ 点击 <a> 子元素
        next_a = next_li.query_selector("a")
        if not next_a:
            print("[翻页] 下一页按钮无 <a> 标签")
            return False

        # ✅ 点击并等待加载
        next_a.click()
        page.wait_for_timeout(1500)
        print("[翻页] 成功点击下一页")
        return True

    except Exception as e:
        print(f"[翻页] 出错: {e}")
        return False
