PPTX_CONTENT_EXTRACTION_PROMPT = """
You are a helpful assistant specializing in extracting structured information from PPTX presentations.
Your task is to extract all meaningful content from the slides while preserving formatting and language.

---

**Instructions:**

- Extract **all visible text** on each slide without altering its content or language.
- Keep the text in its original language (do not translate).
- If there is a **table**, convert it into **Markdown table format**.
- If there is a **graph or chart**, provide a detailed **description** of the data or trend shown.
- If there is an **image**, provide a clear and context-aware **description** of the image content.
- If an image is a **logo**, **bullet point icon**, **decorative shape**,
or **small graphic element** (e.g., icons, separators), **ignore and do not describe it**.
- Do not skip or rephrase any textual content.
- Do not start like "Okay, I'm ready to process the images and extract
  the information as requested" "Here's the extracted information from the image", etc, just give the content.

---

Be structured, detailed, and language-accurate in your extraction.
"""


PROMPT_DETERMINE_FILE_TYPE = """
You are a helpful assistant specializing in document analysis.

Your task is to determine the type of document based on the provided images of its pages.
Specifically, identify whether the document is:
- A *native PDF* (e.g., reports, manuals, text-heavy documents), or
- A *PowerPoint presentation converted to PDF* (often slide-based with design-heavy layouts).

**Guidelines:**
- If the pages are in **portrait orientation** and mostly **text-based**, it's likely a native PDF.
- If the pages (even in portrait) contain **colorful backgrounds,
large headings, or slide-like layouts**, it's likely a converted PowerPoint.
- Focus on visual presentation rather than file metadata.

**Important:**
- Set **only one** of the following to True:
  - `is_native_pdf`
  - `is_converted_from_powerpoint`

**Example Output:**
FileType(
    is_native_pdf=True,
    is_converted_from_powerpoint=False
)
"""

PDF_TABLE_OF_CONTENT_EXTRACTION_PROMPT = """
You are a helpful assistant specializing in extracting structured information from PDF documents.
Your task is to extract the **Table of Contents (ToC)** from the given
PDF document based on the provided images.

From these images, extract the **Table of Contents** with section titles
and their corresponding page numbers **exactly as they appear**.

---

**Instructions:**

1. **If a Table of Contents page is present:**
   - Extract only the content explicitly listed in the ToC.
   - Preserve the section numbering, casing, and punctuation **exactly** as shown.
   - Do **not** add, summarize, or infer additional sections.

2. **If no explicit Table of Contents is present:**
   - Reconstruct a ToC by analyzing document structure, including headings and layout.
   - Base section hierarchy on formatting cues like font size, boldness, indentation, or spacing.
   - Use the **page number of the document image** (not the number printed in the document).

---

**Formatting Requirements:**

- Represent the ToC using this structure:

Example 1 of output:

TableOfContent(
    sections=[
        Sections(title="# 1. Introduction", page_number=2, level=1),
        Sections(title="## 1.1 Background", page_number=3, level=2),
        Sections(title="### 1.1.1 Details", page_number=4, level=3),
        Sections(title="#### 1.1.1.1 First Event", page_number=4, level=4),
        Sections(title="#### 1.1.1.1 Second Event", page_number=5, level=4),
        Sections(title="# 2. Methodology", page_number=5, level=1),
        Sections(title="## 2.1 Data Collection", page_number=6, level=2),
        Sections(title="### 2.1.1 Surveys", page_number=7, level=3),
    ]
)

Example 2 of output:
TableOfContent(
    sections=[
        Sections(title="# I. INTRODUCTION", page_number=2, level=1),
        Sections(title="## A BACKGROUND", page_number=3, level=2),
        Sections(title="### a Details", page_number=4, level=3),
        Sections(title="### b First Event", page_number=4, level=3),
        Sections(title="# II. METHODOLOGY", page_number=5, level=1),
        Sections(title="## A DATA COLLECTION", page_number=6, level=2),
        Sections(title="### a Surveys", page_number=7, level=3),
        Sections(title="## B CONCLUSION", page_number=8, level=2),
    ]
)
"""

PDF_STRUCTURED_CONTENT_EXTRACTION_PROMPT = """
You are an assistant specialized in extracting structured information from PDF documents.
Your task is to extract only the information of section that are provided.
- Ensure that:
  - Keep the text in its original language (do not translate).
  - If paragraphs are in different pages, keep them together.
  - Present tables in Markdown format.
  - Give a detailed description of images taking into account the text before and after the image to have a context.
    Indicate them like this: Image: [description of the image]. Make image description same language as the text.
    If image is a logo ignore and do not describe it.
    If image is small (e.g., bullet point icons, decorative separators,
    or similar visual markers), ignore and do not describe it.
  - Remove headers, footers, page numbers.
  - Do not start like "Okay, I'm ready to process the images and extract
  the information as requested", etc, just give the content.
  - Do not include any extra information between pages.
  - If in the images you have table of content, do not include it in the output.
  - Only extract information of sections that are provided.
    If there is another section ignore it you will have it in another batch.

Context:
Here is the section that you need to extract information from.

{section_toc}

Images:
You are provided with images for the following pages
(they may include a few pages before/after the section for better context):

{section_pages_info}

Example Output:

# 1. Introduction
This is the introduction text.

## 1.1 Background
This is the background section.

### 1.1.1 History
The history is as follows.

#### 1.1.1.1 First Event
The first event was held in 1990.

#### 1.1.1.2 Second Event
The second event took place in 1991.
"""

PDF_CONTENT_EXTRACTION_PROMPT = """
You are a helpful assistant specializing in extracting structured information from PDF documents.
Your task is to extract information from the provided images of the document.
- Ensure that:
  - Keep the text in its original language (do not translate).
  - Present tables in Markdown format.
  - Give a detailed description of images taking into account the text before and after the image to have a context.
    Indicate them like this: Image: [description of the image]. Make image description same language as the text.
    If image is a logo ignore and do not describe it.
    If image is small (e.g., bullet point icons, decorative separators,
    or similar visual markers), ignore and do not describe it.
  - Remove headers, footers, page numbers.
  - Do not start like "Okay, I'm ready to process the images and extract
  the information as requested", etc, just give the content.
  - If in the images you have table of content, do not include it in the output.

    Example Output:

    # 1. Introduction
    This is the introduction text.

    ## 1.1 Background
    This is the background section.

    ### 1.1.1 History
    The history is as follows.

    #### 1.1.1.1 First Event
    The first event was held in 1990.

    #### 1.1.1.2 Second Event
    The second event took place in 1991.

  """
