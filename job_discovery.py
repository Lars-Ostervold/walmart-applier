from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException
import time
import logging
import sys


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def setup_driver():
    """Set up and return a configured Chrome WebDriver."""
    logger.info("Setting up Chrome WebDriver")
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run in headless mode
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    try:
        # Ensure webdriver-manager downloads the driver if needed
        driver_path = ChromeDriverManager().install()
        service = Service(driver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
        logger.info("Chrome WebDriver setup successful")
        return driver
    except Exception as e:
        logger.error(f"Failed to setup Chrome WebDriver: {str(e)}")
        raise

def get_job_listings(url):
    """Scrape job listings from a given URL."""
    logger.info(f"Starting job scraping for URL: {url}")
    driver = None # Initialize driver
    try:
        driver = setup_driver()
        driver.get(url)
        logger.info("Page loaded successfully")
        
        # Wait for job listings to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "job-listing__link"))
        )
        logger.info("Job listings loaded successfully")
        
        # Get all job listings
        job_links = driver.find_elements(By.CLASS_NAME, "job-listing__link")
        logger.info(f"Found {len(job_links)} job listings on page")
        
        # Extract job information
        jobs = []
        for link in job_links:
            try:
                job_title = link.text
                job_url = link.get_attribute("href")
                if job_title and job_url: # Basic validation
                    jobs.append({
                        "title": job_title,
                        "url": job_url
                    })
                    logger.debug(f"Processed job: {job_title}")
                else:
                    logger.warning("Found a link element with missing title or URL.")
            except Exception as e:
                logger.error(f"Error processing a job listing link: {str(e)}")
                continue # Skip this problematic link
            
        return jobs
    except TimeoutException:
        logger.warning(f"Timeout waiting for job listings on {url}. Page might be structured differently or empty.")
        return [] # Return empty list on timeout
    except Exception as e:
        logger.error(f"Error during job scraping for {url}: {str(e)}")
        # Decide if we should raise or return empty. Returning empty might be safer for batch processing.
        return [] 
    finally:
        if driver:
            logger.info(f"Closing WebDriver for {url}")
            driver.quit()

def discover_jobs_from_urls(urls_to_scrape: list):
    """Scrapes job listings from a list of URLs and returns a combined list."""
    all_found_jobs = []
    for url in urls_to_scrape:
        try:
            logger.info(f"\nScraping jobs from: {url}")
            jobs_on_page = get_job_listings(url)
            if jobs_on_page:
                all_found_jobs.extend(jobs_on_page)
                logger.info(f"Successfully scraped {len(jobs_on_page)} jobs from {url}")
                 # Log scraped job titles/URLs for verification
                for job in jobs_on_page:
                    logger.debug(f"  - Found: {job['title']} ({job['url']})")
            else:
                logger.warning(f"No jobs found or error scraping {url}")
            
            # Be nice to the server
            time.sleep(2) 
        except Exception as e:
            # Catch exceptions that might occur in the loop itself (less likely now with try/except in get_job_listings)
            logger.error(f"Unexpected error processing URL {url} in main loop: {str(e)}")
            continue
    
    logger.info(f"\nFinished discovery. Total jobs found across all URLs: {len(all_found_jobs)}")
    return all_found_jobs

# Keep the main block for potential standalone testing of discovery
if __name__ == "__main__":
    test_urls = [
        "https://careers.walmart.com/results?q=Data%20Scientist&page=1&sort=date&jobCity=Bentonville&jobState=AR&jobDepartmentCode=-872043147&expand=department,brand,type,rate&jobCareerArea=all",
        "https://careers.walmart.com/results?q=Data%20Analyst&page=1&sort=date&jobCity=Bentonville&jobState=AR&jobDepartmentCode=-872043147&expand=department,brand,type,rate&jobCareerArea=all",
        "https://careers.walmart.com/results?q=Big%20Data%20Engineer&page=1&sort=date&jobCity=Bentonville&jobState=AR&jobDepartmentCode=-872043147&expand=department,brand,type,rate&jobCareerArea=all"
    ]
    discovered_jobs = discover_jobs_from_urls(test_urls)
    print(f"\n--- Standalone Discovery Test Results ---")
    print(f"Total jobs discovered: {len(discovered_jobs)}")
    # Optional: Print details of discovered jobs
    # for i, job in enumerate(discovered_jobs):
    #     print(f"{i+1}. {job['title']} - {job['url']}")
    print("-----------------------------------------") 