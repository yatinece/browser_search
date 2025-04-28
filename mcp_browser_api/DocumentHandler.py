import requests
from io import BytesIO
import logging
import fitz  # PyMuPDF
import aiohttp
from typing import Dict, Any
from datetime import datetime
from urllib.parse import urlparse

# Set up logger
logger = logging.getLogger("document_handler")

class DocumentHandler:
    """Class to handle extraction of content from various document formats."""
    
    def __init__(self):
        logger.info("DocumentHandler initialized")
    
    async def extract_content(self, url: str) -> Dict[str, Any]:
        """
        Main entry point for document extraction. Detects document type and routes
        to the appropriate extraction method.
        """
        parsed_url = urlparse(url)
        path = parsed_url.path.lower()
        file_extension = path.split('.')[-1] if '.' in path else None
        
        # Use filename as title
        filename = path.split('/')[-1] if '/' in path else "Document"
        
        if file_extension == 'pdf':
            logger.info(f"Detected PDF URL: {url}. Using PDF extraction.")
            try:
                content = await self.extract_text_from_pdf(url)
                metadata = {
                    "url": url,
                    "fetch_time": datetime.now().isoformat(),
                    "content_type": "application/pdf",
                    "file_extension": "pdf",
                    "extraction_method": "pdf_extractor"
                }
                return {
                    "content": content, 
                    "title": filename, 
                    "metadata": metadata
                }
            except Exception as e:
                logger.exception(f"Error extracting PDF content from {url}: {e}")
                return {
                    "content": f"Error extracting PDF content: {str(e)}",
                    "title": "PDF Extraction Error",
                    "metadata": {"error": True, "reason": str(e), "url": url}
                }
        
        elif file_extension in ['docx', 'doc']:
            return await self._placeholder_response(url, file_extension, "Word document")
        
        elif file_extension in ['pptx', 'ppt']:
            return await self._placeholder_response(url, file_extension, "PowerPoint presentation")
        
        elif file_extension in ['xlsx', 'xls']:
            return await self._placeholder_response(url, file_extension, "Excel spreadsheet")
            
        else:
            return {
                "content": f"Unsupported document type or not a document: {file_extension}",
                "title": "Unsupported Document Type",
                "metadata": {
                    "url": url,
                    "fetch_time": datetime.now().isoformat(),
                    "file_extension": file_extension,
                    "error": True,
                    "reason": "unsupported_document_type"
                }
            }
    
    async def extract_text_from_pdf(self, url: str) -> str:
        """
        Downloads a PDF from `url` into memory and returns the
        concatenated text of all pages in their true reading order.
        """
        logger.info(f"Starting PDF download: {url}")

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                try:
                    resp.raise_for_status()
                    if url.split(".")[-1].lower() == "pdf":
                        filename = url.split("/")[-1].lower()
                        logger.info(f"Working on the file name: {filename}")
                except Exception as e:
                    logger.error(f"Failed to download PDF with URL {url}: {e}")
                    raise
      
                logger.info("Download complete; loading into memory buffer")
                pdf_content = await resp.read()
                pdf_stream = BytesIO(pdf_content)

        logger.info(f"Opening PDF document {filename}")
        doc = fitz.open(stream=pdf_stream, filetype="pdf")

        full_text = []
        total_pages = doc.page_count
        logger.info(f"Document opened, {total_pages} pages found")

        # Loop over every page by index
        for page_number in range(total_pages):
            logger.debug(f"Processing page {page_number + 1}/{total_pages}")
            page = doc[page_number]

            # Extract the page as a "dict" structure
            d = page.get_text("dict")
            spans = []

            # Drill into blocks → lines → spans to collect every text span
            for block in d["blocks"]:
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        spans.append((span["origin"], span["text"]))

            # Sort spans by vertical (y) then horizontal (x) to restore reading order
            spans.sort(key=lambda s: (round(s[0][1], 1), round(s[0][0], 1)))

            # Concatenate sorted spans into a single page‑level string
            page_text = "".join(s[1] for s in spans)
            full_text.append(page_text)

            logger.debug(f"Extracted text from page {page_number + 1}")

        # Close the document to free resources
        doc.close()
        logger.info("PDF document closed")

        # Join all pages with double‑newlines between them
        combined = "\n\n".join(full_text)
        logger.info(f"All pages concatenated into single string ({len(combined)} chars)")
        return combined
    
    async def _placeholder_response(self, url: str, file_extension: str, doc_type: str) -> Dict[str, Any]:
        """Helper method to create placeholder responses for unsupported document types."""
        return {
            "content": f"This appears to be a {doc_type}. Support for {file_extension.upper()} format is in development.",
            "title": f"{file_extension.upper()} Document",
            "metadata": {
                "url": url,
                "fetch_time": datetime.now().isoformat(),
                "file_extension": file_extension,
                "message": f"Extraction for {file_extension} files not yet implemented"
            }
        }