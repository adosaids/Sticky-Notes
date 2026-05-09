"""
树形任务工具函数：扁平列表 <-> 嵌套树 转换、可见性过滤、AI 响应层级分配
"""

import time


def build_tree(tasks: list[dict]) -> list[dict]:
    """将扁平任务列表构建为嵌套树结构。
    返回顶级任务列表，每个顶级任务带 children 键。
    """
    by_id = {t["id"]: {**t, "children": []} for t in tasks}
    roots = []
    for t in tasks:
        node = by_id[t["id"]]
        pid = t.get("parentId")
        if pid is None or pid not in by_id:
            roots.append(node)
        else:
            by_id[pid]["children"].append(node)
    return roots


def flatten_tree(tree: list[dict]) -> list[dict]:
    """将嵌套树展平为扁平列表（深度优先遍历）。
    去除 children 键，保留 level/parentId。
    """
    result = []

    def _walk(nodes):
        for node in nodes:
            flat = {k: v for k, v in node.items() if k != "children"}
            result.append(flat)
            _walk(node.get("children", []))

    _walk(tree)
    return result


def visible_tasks(tasks: list[dict]) -> list[dict]:
    """过滤出当前应显示的任务（收起节点的子任务不返回）。"""
    tree = build_tree(tasks)
    result = []

    def _walk(nodes):
        for node in nodes:
            flat = {k: v for k, v in node.items() if k != "children"}
            result.append(flat)
            if not node.get("collapsed", False) and node.get("children"):
                _walk(node["children"])

    _walk(tree)
    return result


def has_children(task_id: int, tasks: list[dict]) -> bool:
    """判断某个任务是否有子任务。"""
    return any(t.get("parentId") == task_id for t in tasks)


def get_descendant_ids(task_id: int, tasks: list[dict]) -> list[int]:
    """获取某个任务的所有后代任务 ID（递归）。"""
    ids = []
    children = [t for t in tasks if t.get("parentId") == task_id]
    for c in children:
        ids.append(c["id"])
        ids.extend(get_descendant_ids(c["id"], tasks))
    return ids


def assign_levels_from_ai_response(ai_items: list[dict], focus_task_id: int | None = None) -> list[dict]:
    """将 AI 返回的扁平层级列表（带 text, level）转为带 id/parentId 的任务列表。
    AI 返回项按顺序排列，子项紧跟父项。
    """
    base_time = int(time.time() * 1000)
    parent_stack = []  # [(level, id), ...]
    result = []

    for i, item in enumerate(ai_items):
        level = min(max(item.get("level", 1), 1), 4)  # 限制 1-4
        task_id = base_time + i

        # 维护 parent stack：弹出所有 level >= 当前 level 的项
        while parent_stack and parent_stack[-1][0] >= level:
            parent_stack.pop()

        parent_id = parent_stack[-1][1] if parent_stack else None
        parent_stack.append((level, task_id))

        task = {
            "id": task_id,
            "text": item.get("text", "").strip(),
            "completed": False,
            "createdAt": task_id,
            "level": level,
            "parentId": parent_id,
            "collapsed": False,
        }
        result.append(task)

    return result


def orphan_children_to_roots(task_id: int, tasks: list[dict]) -> list[dict]:
    """删除某个任务时，将其子任务提升为顶级。"""
    descendant_ids = set(get_descendant_ids(task_id, tasks))
    updated = []
    for t in tasks:
        if t["id"] == task_id or t["id"] in descendant_ids:
            continue
        if t.get("parentId") == task_id:
            t = {**t, "parentId": None, "level": 1}
        updated.append(t)
    return updated


def move_subtree_with_parent(task_id: int, tasks: list[dict], target_pos: int) -> list[dict]:
    """拖拽排序时，移动任务及其所有子任务到新位置。"""
    descendant_ids = set(get_descendant_ids(task_id, tasks))
    subtree_ids = {task_id} | descendant_ids

    # 提取子树（保持原顺序）
    subtree = [t for t in tasks if t["id"] in subtree_ids]
    remaining = [t for t in tasks if t["id"] not in subtree_ids]

    # 计算插入位置
    insert_idx = target_pos
    for i, t in enumerate(remaining):
        original_idx = tasks.index(next(x for x in tasks if x["id"] == t["id"]))
        if original_idx >= target_pos:
            insert_idx = i
            break
    else:
        insert_idx = len(remaining)

    return remaining[:insert_idx] + subtree + remaining[insert_idx:]
