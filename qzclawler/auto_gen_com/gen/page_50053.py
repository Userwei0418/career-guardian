def crawl_page(page) -> bool:
    """
    翻页函数，适配 Ant Design 和 Element UI 的分页组件
    返回:
        True  - 成功翻到下一页
        False - 已经是最后一页或出错
    """
    try:
        # 判断是 Ant Design 还是 Element UI 分页
        ant_pagination_next = page.query_selector("li.ant-pagination-next")
        el_pagination_next = page.query_selector("button.btn-next")

        if ant_pagination_next:
            # Ant Design 分页
            return crawl_page_ant(ant_pagination_next, page)
        elif el_pagination_next:
            # Element UI 分页
            return crawl_page_el(el_pagination_next, page)
        else:
            print("[翻页] 未找到分页组件")
            return False

    except Exception as e:
        print(f"[翻页] 出错: {e}")
        return False

def crawl_page_ant(next_li, page) -> bool:
    """
    翻页函数，适配 Ant Design 分页组件
    返回:
        True  - 成功翻到下一页
        False - 已经是最后一页或出错
    """
    try:
        # ✅ 判断是否禁用
        aria_disabled = next_li.get_attribute("aria-disabled")
        if aria_disabled == "true":
            print("[翻页] 下一页按钮已禁用，可能是最后一页")
            return False

        # ✅ 获取 <a> 标签
        next_a = next_li.query_selector("a.ant-pagination-item-link")
        if not next_a:
            print("[翻页] 未找到 <a> 标签")
            return False

        # ✅ 点击下一页按钮
        next_a.click()
        page.wait_for_timeout(2000)  # 等待加载新页面内容
        print("[翻页] 成功点击下一页")
        return True

    except Exception as e:
        print(f"[翻页] Ant Design 翻页出错: {e}")
        return False

def crawl_page_el(next_button, page) -> bool:
    """
    翻页函数，适配 Element UI 分页组件
    返回:
        True  - 成功翻到下一页
        False - 已经是最后一页或出错
    """
    try:
        # ✅ 判断按钮是否禁用
        if "is-disabled" in next_button.get_attribute("class"):
            print("[翻页] 下一页按钮已禁用，可能是最后一页")
            return False

        # ✅ 点击下一页按钮
        next_button.click()
        page.wait_for_timeout(2000)  # 等待加载新页面内容
        print("[翻页] 成功点击下一页")
        return True

    except Exception as e:
        print(f"[翻页] Element UI 翻页出错: {e}")
        return False
