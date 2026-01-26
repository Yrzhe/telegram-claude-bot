---
name: pdf-to-markdown
description: 将 PDF 文件转换为 Markdown 格式，使用 OCR 技术提取文字和图片。
---

# PDF to Markdown Skill

将 PDF 文档转换为 Markdown 格式，同时提取并保存所有图片。

## 使用场景

- 用户上传了 PDF 文件需要转换为可编辑的 Markdown
- 用户需要提取 PDF 中的文字和图片
- 用户需要将 PDF 内容整理成文档
- 用户需要将扫描版 PDF 进行 OCR 识别

## 执行步骤

1. 确认 PDF 文件位置（通常在 uploads/ 目录）
2. 使用 `pdf_to_markdown` 工具进行转换：
   - pdf_path: PDF 文件的相对路径（相对于工作目录）
   - output_dir: 输出目录（可选，默认为 documents/[PDF文件名]/）
3. 转换完成后，检查输出：
   - Markdown 文件：包含所有文字内容
   - images/ 子文件夹：包含提取的所有图片
4. 将结果告知用户，发送 Markdown 文件

## 工具使用

```
pdf_to_markdown(
    pdf_path="uploads/example.pdf",
    output_dir="documents/example"  # 可选
)
```

## 输出结构

```
documents/[文件名]/
├── [文件名].md      # Markdown 文件
└── images/          # 提取的图片
    ├── [文件名]_img_1.png
    ├── [文件名]_img_2.png
    └── ...
```

## 注意事项

- 仅支持 PDF 格式文件
- 大型 PDF 可能需要较长处理时间
- 图片以相对路径嵌入 Markdown，便于本地查看
- 如果 PDF 是扫描版，会自动进行 OCR 识别
