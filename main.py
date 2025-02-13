from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
import uvicorn
from typing import List, Optional
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

from selenium.webdriver.support import expected_conditions as EC
import time
import urllib.parse
import os
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from datetime import datetime

# Create FastAPI app instance
app = FastAPI(
    title="Web Scraper API with PDF",
    description="API for scraping web content and exporting results as JSON or PDF",
    version="1.2.0"
)

# Add CORS middleware to allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure "pdfs" directory exists for storing PDF files
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
        self.chrome_options = Options()
        self.chrome_options.add_argument("--headless")  # Run in headless mode (no UI)
        self.chrome_options.add_argument("--disable-gpu")
        self.chrome_options.add_argument("--no-sandbox")
        self.chrome_options.add_argument("--disable-dev-shm-usage")

        # Explicitly specify the Chrome binary location
        self.chrome_options.binary_location = "/usr/bin/google-chrome-stable"

        # Automatically install the correct ChromeDriver
        self.service = Service(ChromeDriverManager().install())

    def search_topic(self, topic: str, num_pages: int = 10):
        search_results = []
        driver = webdriver.Chrome(service=self.service, options=self.chrome_options)

        try:
            search_query = urllib.parse.quote(topic)
            search_url = f"https://duckduckgo.com/html/?q={search_query}"
            driver.get(search_url)

            results = driver.find_elements(By.CLASS_NAME, "result__body")
            for result in results:
                try:
                    title = result.find_element(By.CLASS_NAME, "result__title").text.strip()
                    url = result.find_element(By.CLASS_NAME, "result__url").get_attribute("href")
                    snippet = result.find_element(By.CLASS_NAME, "result__snippet").text.strip()

                    search_results.append({"title": title, "url": url, "description": snippet})
                except Exception:
                    continue
        finally:
            driver.quit()
        
        return search_results

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
    Root endpoint that returns API information
    """
    return {
        "message": "Welcome to the Web Scraper API",
        "version": "1.2.0",
        "endpoints": {
            "/webscrape": "GET endpoint for web scraping (use with ?query parameter)",
            "/list_pdfs": "Lists all stored PDFs",
            "/docs": "API documentation"
        }
    }

@app.get("/webscrape")
async def webscrape(query: str, max_results: Optional[int] = 50, output_format: Optional[str] = "json"):
    """
    Endpoint for web scraping based on a search query

    Parameters:
    - query: The search topic to scrape
    - max_results: Maximum number of results to return (default: 50)
    - output_format: "json" (default) or "pdf"

    Returns:
    - JSON object or a downloadable PDF file
    """
    try:
        if not query or len(query.strip()) == 0:
            raise HTTPException(status_code=400, detail="Query parameter cannot be empty")
        
        if max_results < 1 or max_results > 50:
            raise HTTPException(status_code=400, detail="max_results must be between 1 and 50")
        
        results = scraper.search_topic(query)[:max_results]
        
        if output_format.lower() == "pdf":
            pdf_path = scraper.generate_pdf(query, results)
            return {"message": "PDF generated", "pdf_path": pdf_path}

        return JSONResponse(content={
            "query": query,
            "results": results,
            "total_results": len(results)
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")

@app.get("/list_pdfs")
async def list_pdfs():
    """
    Lists all stored PDFs in the 'pdfs' directory
    """
    try:
        pdf_files = [f for f in os.listdir(PDF_DIR) if f.endswith(".pdf")]
        if not pdf_files:
            return {"message": "No PDFs found."}
        
        return {"pdf_files": pdf_files}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing PDFs: {str(e)}")

# Run the API server
if __name__ == "__main__":
    port = int(os.environ["PORT"])  # Render sets the PORT environment variable
    uvicorn.run("main:app", host="0.0.0.0", port=port)
