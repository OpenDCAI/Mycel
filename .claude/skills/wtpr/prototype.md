# wtpr 流程原型图

完整状态机，用于理解 wtpr 的逻辑结构。

```mermaid
flowchart TD
    START(["wtpr"]) --> W{"WORKTREE 已知？\n（当前目录 / 参数 / 上下文）"}
    W -- 已知 --> D
    W -- 未知 --> WASK[/"列出所有 worktree\n选哪个？"/] --> D

    D{"DIRTY？"}
    D -- 干净 --> FETCH
    D -- 有改动 --> ANALYZE["分析 diff，自动生成 commit message"]
    ANALYZE --> DASK[/"展示 message\ncommit 还是 stash？"/]
    DASK -- commit 确认 --> COMMIT["git add -A && git commit"] --> D
    DASK -- commit 不满意 --> ANALYZE
    DASK -- stash --> STASH["git stash"] --> D

    FETCH["git fetch origin"] --> REBASE["git rebase origin/main\n（patch-id 自动跳过已合并内容）"]

    REBASE --> RC{"有冲突？"}
    RC -- 无 --> PUSH
    RC -- 有 --> WAIT[/"显示冲突文件\n解决完了吗？"/]
    WAIT -- 解决了 --> CONT["git rebase --continue"] --> RC

    PUSH["git push --force-with-lease"] --> PRDET{"上下文有 PR URL？"}

    PRDET -- 有 --> UPDATE
    PRDET -- 没有 --> GHVIEW["gh pr view"]
    GHVIEW --> PR{"PR_STATE？"}

    PR -- none --> CREATE["自动生成 title/body\ngh pr create"] --> DONE
    PR -- open --> UPDATE["显示 PR URL\n已追加新 commit"] --> DONE
    PR -- merged/closed --> WARN["PR 已关闭\n建议执行 wtrm"] --> DONE
    PR -- 不确定 --> ASK[/"询问：新建 还是 已有 PR？"/] --> PR

    DONE(["✅ 完成"])
```

## 设计原则

- **单一出口**：所有路径收敛到 `✅ 完成`，Ctrl+C 是唯一退出方式
- **只问"怎么做"**：交互节点不问"要不要做"，只问"怎么继续"
- **所有循环有终点**：DIRTY 循环、冲突循环、message 确认循环均在用户操作后收敛
- **无条件 rebase**：`git rebase origin/main` 内部通过 patch-id 处理所有情况，无需预判
