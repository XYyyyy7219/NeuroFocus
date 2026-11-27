# 学习日志研究

阅读 ReText/editor.py，提交 3859e06698ab1c012ba6e2844eb2910c18191123，最近提交 2026-11-26，仓库未归档。该文件头指定 GPL-2.0-or-later。_convertHtmlToMarkdown 用 QTextDocument 转换后调用 _normalizeMarkdownListIndentation，其中用 fenced 状态区分代码和列表。完整编辑器还处理快捷键、富文本粘贴、行号和多种标记格式。[编辑器源码](https://github.com/retext-project/retext/blob/3859e06698ab1c012ba6e2844eb2910c18191123/ReText/editor.py)

日志按五个可空字段保存原文。原文 Markdown 导出可以保留缩进、围栏和链接，避免来回转换改变笔记。先写一句话即可关闭；深度字段按需展开。采用现有 PySide6，无上游实现或插件复用。公式原文可交给专用编辑器进一步排版。
