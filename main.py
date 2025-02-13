import os
import time
import urllib.parse
from datetime import datetime
from typing import List, Optional

import requests
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# Create FastAPI app instance
app = FastAPI(
    title="Web Scraper API with PDF",
    description="API for scraping web content and exporting results as JSON or PDF",
    version="1.2.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure "pdfs" directory exists
PDF_DIR = "./pdfs"
os.makedirs(PDF_DIR, exist_ok=True)


class SearchResult(BaseModel):
    title: str
    url: str
    description: Optional[str] = None


class SearchResponse(BaseModel):
    query: str
    results: List[SearchResult]
    total_results: int


class FastWebScraper:
    def __init__(self):
        """
        Initialize the scraper with headless Chrome settings for Render
        """
        self.chrome_options = Options()
        self.chrome_options.add_argument("--headless")
        self.chrome_options.add_argument("--disable-gpu")
        self.chrome_options.add_argument("--no-sandbox")
        self.chrome_options.add_argument("--disable-dev-shm-usage")

        # Set correct paths for Chrome and Chromedriver in Render
        self.chrome_options.binary_location = "/opt/render/project/.render/chrome"
        self.driver_path = "/opt/render/project/.render/chromedriver"

    def search_topic(self, topic: str, num_pages: int = 10) -> List[dict]:
        """
        Scrapes search results from DuckDuckGo
        """
        search_results = []
        driver = webdriver.Chrome(executable_path=self.driver_path, options=self.chrome_options)

        try:
            search_query = urllib.parse.quote(topic)

            for page in range(num_pages):
                search_url = f"https://duckduckgo.com/html/?q={search_query}&s={page * 30}"
                driver.get(search_url)

                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "result__body"))
                )

                results = driver.find_elements(By.CLASS_NAME, "result__body")

                for result in results:
                    try:
                        title_elem = result.find_element(By.CLASS_NAME, "result__title")
                        url_elem = result.find_element(By.CLASS_NAME, "result__url")
                        snippet_elem = result.find_element(By.CLASS_NAME, "result__snippet")

                        title = title_elem.text.strip()
                        url = url_elem.get_attribute("href")
                        snippet = snippet_elem.text.strip()

                        if url and self.is_valid_url(url):
                            search_results.append({
                                'title': title,
                                'url': url,
                                'description': snippet
                            })
                    except Exception:
                        continue

                time.sleep(0.5)

                if len(search_results) >= 50:
                    break

        finally:
            driver.quit()

        return search_results[:50]

    def is_valid_url(self, url: str) -> bool:
        """
        Quick validation of URLs
        """
        allowed_domains = ['.com', '.org', '.net', '.edu', '.gov', '.io']
        return any(domain in url.lower() for domain in allowed_domains)

    def generate_pdf(self, query: str, results: List[dict]) -> str:
        """
        Generates and stores a PDF file with search results
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_filename = f"search_results_{query.replace(' ', '_')}_{timestamp}.pdf"
        pdf_path = os.path.join(PDF_DIR, pdf_filename)

        c = canvas.Canvas(pdf_path, pagesize=letter)
        c.setFont("Helvetica", 12)

        y = 750
        c.drawString(100, y, f"Search Results for: {query}")
        y -= 30

        for result in results:
            if y < 50:
                c.showPage()
                c.setFont("Helvetica", 12)
                y = 750

            c.drawString(100, y, f"Title: {result['title']}")
            y -= 20
            c.drawString(100, y, f"URL: {result['url']}")
            y -= 20
            c.drawString(100, y, f"Description: {result.get('description', 'N/A')}")
            y -= 40

        c.save()
        return pdf_path  # Return stored PDF path


# Create a single instance of the scraper to be reused
scraper = FastWebScraper()


@app.get("/")
async def root():
    """
    Root endpoint
    """
    return {
        "message": "Welcome to the Web Scraper API",
        "version": "1.2.0",
    }


@app.get("/webscrape")
async def webscrape(query: str, max_results: Optional[int] = 50, output_format: Optional[str] = "json"):
    """
    Web scraping endpoint
    """
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    results = scraper.search_topic(query)[:max_results]

    if output_format.lower() == "pdf":
        pdf_path = scraper.generate_pdf(query, results)
        return {"message": "PDF generated", "pdf_path": pdf_path}

    return JSONResponse(content={"query": query, "results": results, "total_results": len(results)})


@app.get("/list_pdfs")
async def list_pdfs():
    """
    Lists stored PDFs
    """
    try:
        pdf_files = [f for f in os.listdir(PDF_DIR) if f.endswith(".pdf")]
        return {"pdf_files": pdf_files} if pdf_files else {"message": "No PDFs found."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing PDFs: {str(e)}")


# Run the API server with dynamic port binding for Render
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))  # Render assigns a dynamic port
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
