import logging
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from job_discovery import setup_driver # Re-use the driver setup
from typing import Union # Import Union

logger = logging.getLogger(__name__)

def get_job_description(url: str) -> Union[str, None]:
    """Scrape the job description text from a given job URL."""
    logger.info(f"Attempting to scrape job description from: {url}")
    driver = None  # Initialize driver to None
    try:
        driver = setup_driver()
        driver.get(url)
        logger.info("Job page loaded successfully")

        # --- Selector Strategy (Updated based on user feedback) ---
        # Target the main container div that holds the description parts.
        description_container_xpath = "//div[contains(@class, 'job-description__overview')]"

        wait = WebDriverWait(driver, 15) # Increased wait time for potentially heavier pages
        
        try:
             # Wait specifically for the description container
            description_element = wait.until(
                EC.presence_of_element_located((By.XPATH, description_container_xpath))
            )
            logger.info("Job description container found.")
            # Get all text within the container, including sub-elements
            description_text = description_element.text 
            
            # Basic cleanup (remove excessive blank lines)
            description_text = '\n'.join([line.strip() for line in description_text.split('\n') if line.strip()])
            
            logger.info(f"Successfully extracted description text (length: {len(description_text)} chars).")
            return description_text
        except TimeoutException:
            logger.warning(f"Timeout waiting for description element using XPath: {description_container_xpath}. The page structure might have changed or the element is not present.")
            return None
        except NoSuchElementException:
             logger.warning(f"Could not find description element using XPath: {description_container_xpath}. The selector might be incorrect.")
             return None

    except Exception as e:
        logger.error(f"An unexpected error occurred while scraping job description from {url}: {str(e)}")
        return None
    finally:
        if driver:
            logger.info("Closing WebDriver for job description scraping.")
            driver.quit()

# Example usage (for testing this script directly)
if __name__ == '__main__':
    # Configure logging for standalone testing
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Use a sample job URL (replace with a real one for actual testing)
    # test_url = "https://careers.walmart.com/us/jobs/WD1866909-principal-data-scientist" 
    test_url = "https://careers.walmart.com/us/jobs/WD2098898-staff-technical-program-manager" # A known URL from previous context
    
    if test_url:
        description = get_job_description(test_url)
        if description:
            print("\n--- Job Description ---")
            print(description[:1000] + "..." if len(description) > 1000 else description) # Print first 1000 chars
            print("\n----------------------")
        else:
            print(f"Could not retrieve description from {test_url}")
    else:
        print("Please provide a test URL in the script for standalone testing.") 