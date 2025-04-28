import requests
import fitz               # PyMuPDF
from io import BytesIO
import logging 

# ─── Logging Configuration ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,  # Use DEBUG for more detailed output
    format="%(asctime)s [%(levelname)s]  %(funcName)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger("pdf_extraction")
def extract_text_from_pdf(url: str) -> str:
    """
    Downloads a PDF from `url` into memory and returns the
    concatenated text of all pages in their true reading order.
    """

    logger.info(f"Starting download: {url}")
    resp = requests.get(url)


    try:
        resp.raise_for_status()
        if url.split(".")[-1].lower() == "pdf":
            filename = url.split("/")[-1].lower()
            logger.info(f"Working on the file name: {filename}")
    except Exception as e:
        logger.error(f"Failed to download PDF with URL {url}: {e}")
        raise
  

    logger.info("Download complete; loading into memory buffer")
    pdf_stream = BytesIO(resp.content)

    logger.info(f"Opening PDF document {filename}")
    doc = fitz.open(stream=pdf_stream, filetype="pdf")

    full_text = []
    total_pages = doc.page_count
    logger.info(f"Document opened, {total_pages} pages found")

    # 3. Loop over every page by index
    for page_number in range(total_pages):
        logger.debug(f"Processing page {page_number + 1}/{total_pages}")
        page = doc[page_number]

        # 4. Extract the page as a “dict” structure
        d = page.get_text("dict")
        spans = []

        # 5. Drill into blocks → lines → spans to collect every text span
        for block in d["blocks"]:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    spans.append((span["origin"], span["text"]))

        # 6. Sort spans by vertical (y) then horizontal (x) to restore reading order
        spans.sort(key=lambda s: (round(s[0][1], 1), round(s[0][0], 1)))

        # 7. Concatenate sorted spans into a single page‑level string
        page_text = "".join(s[1] for s in spans)
        full_text.append(page_text)

        logger.debug(f"Extracted text from page {page_number + 1}")

    # 8. Close the document to free resources
    doc.close()
    logger.info("PDF document closed")

    # 9. Join all pages with double‑newlines between them
    combined = "\n\n".join(full_text)
    logger.info("All pages concatenated into single string")
    return combined



if __name__ == "__main__":
    pdf_url = "https://www.promarket.org/wp-content/uploads/2018/04/Digital-Platforms-and-Concentration.pdf"
    pdf_url = "https://ai-infrastructure.org/wp-content/uploads/2024/03/The-State-of-AI-Infrastructure-at-Scale-2024.pdf"
    text = extract_text_from_pdf(pdf_url)

    # 6a. Print a snippet
    print(text[:1000] + "\n\n...")

    # 6b. (Optional) Save to .txt
    with open("full_document.txt", "w", encoding="utf-8") as f:
        f.write(text)
    print("Full text saved to full_document.txt")
