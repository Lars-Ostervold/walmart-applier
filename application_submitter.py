import logging
import os
import sys
import time # Using time.sleep for simplicity, explicit waits preferred for robustness
import random # <<< Add random for delays
from pathlib import Path
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from typing import Union # <<< Add Union
import json # <<< Add json
import google.generativeai as genai
import re # <<< Add import re

logger = logging.getLogger(__name__)

class ApplicationSubmitter:
    def __init__(self, cv_path: str = "cv.md"): # <<< Add cv_path
        self.driver = self._initialize_driver()
        self.email = os.getenv("WORKDAY_EMAIL")
        self.password = os.getenv("WORKDAY_PASSWORD")
        self.cv_content = self._load_file_content(Path(cv_path), "CV") # <<< Load CV
        self.model = self._configure_llm() # <<< Configure LLM

        if not self.email or not self.password:
            logger.error("Workday email or password not found in .env file. Cannot proceed with login.")
        if not self.cv_content:
             logger.error(f"CV content not loaded from {cv_path}. Cannot generate role descriptions.")
        if not self.model:
             logger.error(f"LLM not configured. Cannot generate role descriptions.")

    def _initialize_driver(self):
        """Initializes the Selenium WebDriver."""
        logger.info("Initializing Chrome WebDriver...")
        try:
            options = webdriver.ChromeOptions()
            # Add options if needed (e.g., headless)
            options.add_argument("--headless")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--no-sandbox") # Often needed in containerized environments
            options.add_argument("--disable-dev-shm-usage") # Overcome limited resource problems
            
            # Use webdriver-manager to automatically handle driver download/updates
            service = ChromeService(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            logger.info("WebDriver initialized successfully.")
            return driver
        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {e}")
            sys.exit(1)

    def navigate_to_job_page(self, job_url: str):
        """Navigates to the job description page."""
        logger.info(f"Navigating to job page: {job_url}")
        try:
            self.driver.get(job_url)
            # Wait briefly for the initial page load
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'a[data-gtm="click to apply"]' ))
            )
            logger.info("Job page loaded.")
            return True
        except TimeoutException:
            logger.error(f"Timeout waiting for Apply button on job page: {job_url}")
            return False
        except Exception as e:
            logger.error(f"Error navigating to job page {job_url}: {e}")
            return False

    def navigate_to_apply_page(self):
        """Finds the initial Apply button, extracts its href, and navigates there."""
        logger.info("Finding the initial 'Apply' button link...")
        apply_link_selector = (By.CSS_SELECTOR, 'a[data-gtm="click to apply"]')
        try:
            # Wait for the link element to be present
            apply_link_element = WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located(apply_link_selector)
            )
            
            apply_url = apply_link_element.get_attribute('href')
            if not apply_url:
                logger.error("Found the Apply link element, but it has no href attribute.")
                return False
                
            logger.info(f"Extracted Apply URL: {apply_url}")
            logger.info(f"Navigating directly to Apply URL...")
            self.driver.get(apply_url) # Navigate in the current tab
            
            # Add a wait after navigation to ensure the new page starts loading
            # Wait for a known element on the Workday sign-in/application page
            # Example: Wait for the "Sign In" span OR the "Use My Last Application" button
            WebDriverWait(self.driver, 20).until(
                EC.any_of(
                    EC.presence_of_element_located((By.XPATH, "//span[contains(text(), 'Sign In')]")),
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'a[data-automation-id="useMyLastApplication"]'))
                )
            )
            logger.info(f"Navigated to Workday page: {self.driver.current_url}")
            return True

        except TimeoutException:
            logger.error("Timeout waiting for the Apply link element or the subsequent Workday page element.")
            return False
        except Exception as e:
            logger.error(f"Error extracting Apply link or navigating: {e}")
            return False
            
    def _human_like_send_keys(self, element, text):
        """Sends keys to an element character by character with small random delays."""
        for char in text:
            delay = random.uniform(0.05, 0.15) # Adjust range as needed
            time.sleep(delay)
            element.send_keys(char)

    def check_and_sign_in(self) -> bool:
        """Checks if sign-in is needed and performs login if required."""
        if not self.email or not self.password:
             logger.error("Missing credentials, cannot attempt sign in.")
             return False
             
        logger.info("Checking if Sign In is required...")
        sign_in_prompt_locator = (By.XPATH, "//span[contains(text(), 'Sign In')]")

        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(sign_in_prompt_locator)
            )
            logger.info("'Sign In' prompt found. Proceeding with login.")
            
            try:
                sign_in_button = self.driver.find_element(*sign_in_prompt_locator)
                sign_in_button.click()
                logger.info("Clicked 'Sign In' span.")

                # Wait for email field and fill with human-like typing
                email_field = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, 'input[data-automation-id="email"]'))
                )
                logger.info("Typing email...")
                self._human_like_send_keys(email_field, self.email)
                logger.info("Entered email.")

                # Find password field and fill with human-like typing
                password_field = self.driver.find_element(By.CSS_SELECTOR, 'input[data-automation-id="password"]')
                logger.info("Typing password...")
                self._human_like_send_keys(password_field, self.password)
                logger.info("Entered password.")

                # Find and click the final Sign In button/overlay
                submit_overlay_selector = (By.CSS_SELECTOR, 'div[data-automation-id="click_filter"]')
                submit_button = WebDriverWait(self.driver, 15).until(
                    EC.element_to_be_clickable(submit_overlay_selector)
                )
                logger.info("Attempting to click the sign-in overlay/filter...")
                submit_button.click()
                logger.info("Clicked final sign-in overlay/filter.")
                time.sleep(5) # Wait for login process
                logger.info("Sign in process completed.")
                return True # Signed in successfully

            except TimeoutException as e:
                 logger.error(f"Timeout during sign in process: {e}")
                 return False
            except NoSuchElementException as e:
                 logger.error(f"Could not find element during sign in: {e}")
                 return False
            except Exception as e:
                 logger.error(f"An unexpected error occurred during sign in: {e}")
                 return False
            
        except TimeoutException:
            logger.info("'Sign In' prompt not found. Assuming already logged in.")
            return True 
        except Exception as e:
             logger.error(f"Error checking for Sign In prompt: {e}")
             return False

    def click_use_last_application(self) -> bool:
        """Clicks the 'Use My Last Application' button."""
        logger.info("Attempting to click 'Use My Last Application'...")
        button_locator = (By.CSS_SELECTOR, 'a[data-automation-id="useMyLastApplication"]')
        try:
            use_last_app_button = WebDriverWait(self.driver, 20).until(
                EC.element_to_be_clickable(button_locator)
            )
            use_last_app_button.click()
            logger.info("Clicked 'Use My Last Application'.")
            # Add a short wait for the next page/section to start loading
            time.sleep(3)
            return True
        except TimeoutException:
            logger.error("Timeout waiting for 'Use My Last Application' button.")
            return False
        except Exception as e:
            logger.error(f"Error clicking 'Use My Last Application': {e}")
            return False
            
    def handle_referral_source(self) -> bool:
        """Handles the 'How did you hear about us?' section if present, filling referral info using specific selectors."""
        logger.info("Checking for 'How did you hear about us?' source input...")
        search_container_selector = (By.CSS_SELECTOR, 'div[data-automation-id="multiselectInputContainer"]')
        referral_info = "Tony Woods, tony.woods0@walmart.com"
        referral_option_selector = (By.CSS_SELECTOR, "div[data-automation-id='promptOption'][data-automation-label='Referral']")
        i_know_someone_option_selector = (By.CSS_SELECTOR, "div[data-automation-id='promptOption'][data-automation-label='I know someone who works here']")
        referred_by_input_selector = (By.CSS_SELECTOR, 'input[name="referredBy"]')

        try:
            # Wait for the search container
            logger.info(f"Waiting for search container element: {search_container_selector}")
            search_container = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable(search_container_selector)
            )
            logger.info("Search container element FOUND and clickable.")
            
            logger.info("Attempting to CLICK search container...")
            search_container.click()
            logger.info("Search container CLICKED successfully.")
            
            time.sleep(1) # Pause for dropdown to open reliably

            # Click 'Referral' option
            logger.info("Attempting to click 'Referral' option...")
            referral_option = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable(referral_option_selector)
            )
            referral_option.click()
            logger.info("Clicked 'Referral' option.")
            time.sleep(0.5) # Short pause for next options

            # Click 'I know someone who works here' option
            logger.info("Attempting to click 'I know someone who works here' option...")
            i_know_someone_option = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable(i_know_someone_option_selector)
            )
            i_know_someone_option.click()
            logger.info("Clicked 'I know someone who works here'.")
            
            # Wait 1 second as requested, then find and fill input
            logger.info("Waiting 1 second for referral input field...")
            time.sleep(1)
            
            referred_by_input = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable(referred_by_input_selector)
            )
            logger.info("Typing referral information...")
            self._human_like_send_keys(referred_by_input, referral_info)
            logger.info("Entered referral information.")
            return True
            
        except TimeoutException:
            try:
                # Check if the *container* was ever visible 
                self.driver.find_element(*search_container_selector)
                logger.error("Timeout occurred. Search container found but wasn't clickable, or dropdown options failed.")
                screenshot_path = "referral_timeout_error.png"
                try:
                    self.driver.save_screenshot(screenshot_path)
                    logger.info(f"Saved screenshot to {screenshot_path}")
                except Exception as ss_err:
                    logger.error(f"Failed to save screenshot: {ss_err}")
                return False
            except NoSuchElementException:
                logger.info("'How did you hear about us?' container not found in DOM. Skipping referral step.")
                return True
        except Exception as e:
            logger.error(f"An error occurred while handling referral source: {e}", exc_info=True)
            screenshot_path = "referral_exception_error.png"
            try:
                self.driver.save_screenshot(screenshot_path)
                logger.info(f"Saved screenshot to {screenshot_path}")
            except Exception as ss_err:
                logger.error(f"Failed to save screenshot: {ss_err}")
            return False

    def run_application_start(self, job_url: str):
        """Orchestrates the initial steps of the application process."""
        if not self.navigate_to_job_page(job_url):
            logger.error("Failed to navigate to job page. Aborting.")
            return False

        if not self.navigate_to_apply_page():
             logger.error("Failed to navigate to the Workday apply page. Aborting.")
             return False
        
        if not self.check_and_sign_in():
            logger.error("Sign in check or process failed. Aborting.")
            return False

        if not self.click_use_last_application():
            logger.error("Failed to click 'Use My Last Application'. Aborting.")
            return False

        # --- Add call to handle referral --- 
        if not self.handle_referral_source():
             logger.error("Failed to handle the referral source section. Aborting.")
             return False
        # ------------------------------------

        logger.info("Successfully navigated, signed in, clicked 'Use My Last Application', and handled referral. Ready for next steps.")
        return True
        
    def close_driver(self):
        """Closes the WebDriver."""
        if self.driver:
            logger.info("Closing WebDriver.")
            self.driver.quit()
            self.driver = None

    # <<< Add _load_file_content method >>>
    def _load_file_content(self, file_path: Path, file_description: str) -> Union[str, None]:
        """Load text content from a file."""
        if not file_path.is_file():
            logger.error(f"{file_description} file not found at: {file_path}")
            return None
        try:
            try:
                content = file_path.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                logger.warning(f"UTF-8 decoding failed for {file_path}. Trying latin-1.")
                content = file_path.read_text(encoding='latin-1')
            logger.info(f"Successfully loaded {file_description} from {file_path}")
            return content
        except Exception as e:
            logger.error(f"Error reading {file_description} file {file_path}: {str(e)}")
            return None
            
    # <<< Add _configure_llm method >>>
    def _configure_llm(self) -> Union[genai.GenerativeModel, None]:
        """Configure and return the Google Generative AI client."""
        load_dotenv()
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logger.error("GOOGLE_API_KEY not found in .env file.")
            return None
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-1.5-flash-latest') 
            logger.info("Google Generative AI configured successfully for application submitter.")
            return model
        except Exception as e:
            logger.error(f"Failed to configure Google Generative AI: {str(e)}")
            return None
            
    # <<< Add _clean_llm_output method >>>
    def _clean_llm_output(self, raw_text: str) -> str:
        """Removes common LLM artifacts like surrounding code fences."""
        cleaned_text = raw_text.strip()
        # Basic fence removal
        if cleaned_text.startswith("```") and cleaned_text.endswith("```"):
             # Try removing optional language identifier first
             lines = cleaned_text.split('\n', 1)
             if len(lines) > 1 and lines[0].startswith("```") and not lines[0][3:].strip(): # Only ```
                 logger.debug("Removed simple surrounding fences.")
                 cleaned_text = lines[1].strip()
             elif len(lines) > 1 and lines[0].startswith("```"):
                 logger.debug("Removed surrounding fences with language identifier.")
                 cleaned_text = lines[1].strip() # Remove first line (```lang)
             else: # Single line fence?
                 cleaned_text = cleaned_text[3:-3].strip()
                 logger.debug("Removed simple surrounding fences (single line?).")
        # Handle potential JSON fences specifically
        pattern_json = r"^```(?:json)?\s*\n(.*?)\n```$"
        match_json = re.match(pattern_json, raw_text.strip(), re.DOTALL)
        if match_json:
             logger.debug("Cleaned JSON code block fences.")
             return match_json.group(1).strip()
             
        return cleaned_text # Return original cleaned text if no JSON block found

    def click_save_and_continue(self) -> bool:
        """Clicks the 'Save and Continue' button, typically found at the bottom of form pages."""
        logger.info("Attempting to click 'Save and Continue'...")
        button_selector = (By.CSS_SELECTOR, 'button[data-automation-id="pageFooterNextButton"]')
        try:
            save_button = WebDriverWait(self.driver, 15).until(
                EC.element_to_be_clickable(button_selector)
            )
            save_button.click()
            logger.info("Clicked 'Save and Continue'.")
            # Wait for the next section/page to start loading
            # This might need a more specific wait for an element on the *next* page
            time.sleep(3) 
            return True
        except TimeoutException:
            logger.error("Timeout waiting for 'Save and Continue' button.")
            return False
        except Exception as e:
            logger.error(f"Error clicking 'Save and Continue': {e}")
            return False

    def _generate_role_descriptions(self, job_description: str) -> Union[dict, None]:
        """Generates optimized role descriptions for predefined roles using LLM."""
        if not self.model or not self.cv_content:
            logger.error("LLM or CV content not available. Cannot generate role descriptions.")
            return None

        roles = [
            "Dow", # Senior Data Scientist & Engineer @ the Dow Chemical Company
            "Freelance", # Freelancing AI & Software Development
            "LION", # CTO @ LION
            "PennState", # PhD Researcher at Penn State
            "Arkansas", # Graduate Researcher at Arkansas
            "Garver" # Data Science Intern @ Garver
        ]
        role_list_str = "\n".join([f"- {role}" for role in roles])

        prompt = f"""
        **Task:** Based on the provided CV and the target Job Description, write concise, impactful, and ATS-optimized role descriptions (typically 2-4 bullet points each) for the following past roles. Focus on achievements and skills most relevant to the target job.

        **CV Content (Markdown):**
        ```markdown
        {self.cv_content}
        ```

        **Target Job Description:**
        ```
        {job_description}
        ```

        **Roles to Describe:**
        {role_list_str}
        (Note: 'Dow' refers to Senior Data Scientist at Dow Chemical, 'Freelance' refers to AI/Software Freelancing including project experience, 'LION' refers to CTO at LION, 'PennState' to PhD Researcher, 'Arkansas' to Graduate Researcher, 'Garver' to Data Science Intern.)

        **Instructions:**
        *   For each role, highlight accomplishments and responsibilities from the CV that directly align with the keywords and requirements in the Target Job Description.
        *   Use strong action verbs and quantify achievements where possible (e.g., 'Improved X by Y%', 'Managed Z projects').
        *   Keep each description focused and typically 2-4 bullet points long.
        *   Format the output as a single JSON object where keys are the role identifiers from the list above (e.g., "Dow", "Freelance", "LION", "PennState", "Arkansas", "Garver") and values are the generated Markdown strings for the role descriptions (use standard Markdown bullet points like `- ` or `* `).

        **Output (JSON Object ONLY):**
        """

        try:
            logger.info("Sending request to Gemini to generate role descriptions...")
            response = self.model.generate_content(prompt)
            raw_json_output = response.text.strip()
            cleaned_json_output = self._clean_llm_output(raw_json_output) # Clean potential fences
            
            logger.debug(f"Cleaned LLM JSON output: {cleaned_json_output}")
            descriptions = json.loads(cleaned_json_output)

            # Basic validation
            if not isinstance(descriptions, dict) or not all(role in descriptions for role in roles):
                logger.error(f"LLM output was not a valid JSON object with all expected keys. Output: {cleaned_json_output}")
                return None
                
            logger.info("Successfully received and parsed role descriptions from LLM.")
            return descriptions

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}. Raw response: {raw_json_output}")
            return None
        except Exception as e:
            logger.error(f"Error calling Gemini API for role descriptions: {str(e)}")
            return None

    def fill_role_descriptions(self, descriptions: dict) -> bool:
        """Fills the Workday role description textareas based on dynamically found company names and IDs."""
        if not descriptions:
            logger.error("No descriptions provided to fill.")
            return False

        logger.info("Finding company name inputs to map IDs...")
        company_input_selector = (By.CSS_SELECTOR, "input[id^='workExperience-'][id$='--companyName']")
        # Mapping from LLM key to expected company name value on the webpage
        llm_key_to_web_name = {
            "Dow": "The Dow Chemical Company",
            "Freelance": "Self", # Assuming 'Self' is used for freelance
            "LION": "LION Software",
            "PennState": "The Pennsylvania State University",
            "Arkansas": "The University of Arkansas",
            "Garver": "Garver"
        }
        company_name_to_suffix_map = {}
        
        try:
            # Wait for at least one company name input to be present
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located(company_input_selector)
            )
            company_inputs = self.driver.find_elements(*company_input_selector)
            logger.info(f"Found {len(company_inputs)} company name input fields.")

            # Build the dynamic map
            for input_element in company_inputs:
                try:
                    company_name = input_element.get_attribute('value').strip()
                    element_id = input_element.get_attribute('id')
                    # Extract suffix using regex
                    match = re.search(r'workExperience-(\d+)--companyName', element_id)
                    if company_name and match:
                        suffix = match.group(1)
                        company_name_to_suffix_map[company_name] = suffix
                        logger.debug(f"Mapped Company '{company_name}' to ID Suffix '{suffix}'")
                    else:
                         logger.warning(f"Could not extract info from company input with ID: {element_id} and value: {company_name}")
                except Exception as map_err:
                    logger.warning(f"Error processing company input element: {map_err}")
            
            logger.info(f"Built dynamic company name to ID map: {company_name_to_suffix_map}")

        except TimeoutException:
            logger.error("Timeout waiting for any company name input fields to appear on the page.")
            return False
        except Exception as e:
            logger.error(f"Error finding company name input fields: {e}")
            return False

        # Now fill the textareas using the map
        all_filled = True
        filled_count = 0
        for llm_key, description_text in descriptions.items():
            expected_web_name = llm_key_to_web_name.get(llm_key)
            if not expected_web_name:
                logger.warning(f"No mapping found for LLM key '{llm_key}'. Skipping.")
                continue
            
            id_suffix = company_name_to_suffix_map.get(expected_web_name)
            if id_suffix:
                textarea_id = f"workExperience-{id_suffix}--roleDescription"
                textarea_selector = (By.ID, textarea_id)
                logger.info(f"Attempting to fill description for '{expected_web_name}' (LLM Key: {llm_key}) into textarea '{textarea_id}'...")
                
                try:
                    textarea = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located(textarea_selector)
                    )
                    
                    # Scroll element into view
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", textarea)
                    logger.debug(f"Scrolled textarea {textarea_id} into view.")
                    time.sleep(0.5) 
                    
                    # Ensure clickable *after* scrolling
                    WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable(textarea_selector))
                    textarea.click() 
                    time.sleep(0.3)
                    textarea.clear() 
                    time.sleep(0.3)
                    # --- Revert to instant send_keys --- 
                    textarea.send_keys(description_text)
                    # self._human_like_send_keys(textarea, description_text) # <<< Previous human-like typing
                    # -----------------------------------
                    logger.info(f"Successfully filled description for '{expected_web_name}'.")
                    filled_count += 1
                    time.sleep(0.5) # Small pause after filling
                except TimeoutException:
                    logger.error(f"Timeout waiting for or interacting with textarea ID '{textarea_id}' for company '{expected_web_name}'.")
                    all_filled = False
                except Exception as e:
                    logger.error(f"Error filling textarea for company '{expected_web_name}' (ID: {textarea_id}): {e}")
                    all_filled = False
            else:
                logger.warning(f"Company '{expected_web_name}' (LLM Key: {llm_key}) not found on page or mapping failed. Skipping description fill.")
                # Decide if this should be a failure
                # all_filled = False 

        logger.info(f"Finished filling descriptions. Filled {filled_count} out of {len(descriptions)} generated descriptions.")
        return all_filled

    def handle_resume_upload(self, resume_pdf_path: Path) -> bool:
        """Deletes the existing resume (if found) and uploads a new one."""
        if not resume_pdf_path.is_file():
            logger.error(f"Resume PDF not found at: {resume_pdf_path}")
            return False
        
        # --- Delete existing resume --- 
        delete_button_selector = (By.CSS_SELECTOR, 'button[data-automation-id="delete-file"]')
        try:
            # Check if any delete buttons exist and click them all
            logger.info("Checking for existing resume delete buttons...")
            delete_buttons = self.driver.find_elements(*delete_button_selector)
            if delete_buttons:
                logger.info(f"Found {len(delete_buttons)} existing resume(s) to delete")
                for button in delete_buttons:
                    try:
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", button)
                        time.sleep(0.5)
                        button.click()
                        logger.info("Clicked delete button for existing resume")
                        time.sleep(1)  # Wait for deletion to process
                    except Exception as e:
                        logger.warning(f"Error clicking delete button: {e}")
            else:
                logger.info("No existing resumes found to delete")
        except Exception as e:
            logger.warning(f"Error checking for delete buttons: {e}")

        # --- Upload new resume --- 
        upload_input_selector = (By.CSS_SELECTOR, 'input[data-automation-id="file-upload-input-ref"][type="file"]')
        try:
            logger.info("Finding file upload input...")
            # File inputs might not be visible/clickable, so wait for presence
            upload_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(upload_input_selector)
            )
            logger.info(f"Sending file path to upload input: {str(resume_pdf_path.resolve())}")
            upload_input.send_keys(str(resume_pdf_path.resolve())) # Send absolute path
            
            # Add a wait for upload confirmation (e.g., new delete button appears with *new* filename)
            # This is crucial but hard to define without seeing the page after upload.
            # Let's wait for *a* delete button to appear again after a delay.
            logger.info("Waiting for upload to process (checking for delete button appearance)...")
            time.sleep(1) # Initial pause
            WebDriverWait(self.driver, 20).until( # Longer wait for upload processing
                 EC.element_to_be_clickable(delete_button_selector)
            )
            logger.info("New resume uploaded successfully (delete button reappeared).")
            return True
        except TimeoutException:
            logger.error("Timeout waiting for file upload input to appear, or for upload confirmation (delete button). Upload might have failed.")
            return False
        except Exception as e:
            logger.error(f"Error uploading resume: {e}")
            return False

    def handle_application_questions(self) -> bool:
        """Handles the application questionnaire section."""
        logger.info("Handling application questions...")
        
        # Define the question-answer pairs with their selectors
        questions = [
            {
                "button": (By.ID, "primaryQuestionnaire--6053fc57425a101d610d2b3da5e40001"),
                "answer": (By.ID, "d384a06c8043019f976faff18e06cdff")
            },
            {
                "button": (By.ID, "primaryQuestionnaire--6053fc57425a101d610d2b3da5e40004"),
                "answer": (By.ID, "cb11300682fc1001a26a869fe7a20000")
            },
            {
                "button": (By.ID, "primaryQuestionnaire--6053fc57425a101d610d2bd793200001"),
                "answer": (By.ID, "855ef6dee3b4011af60e5ed0f23b631f")
            },
            {
                "button": (By.ID, "primaryQuestionnaire--6053fc57425a101d610d2bd793200004"),
                "answer": (By.ID, "855ef6dee3b40180e9a45ed0f23b6d1f")
            },
            {
                "button": (By.ID, "primaryQuestionnaire--6053fc57425a101d610d2bd793200008"),
                "answer": (By.ID, "855ef6dee3b4015999df1ad1f23b4928")
            },
            {
                "button": (By.ID, "primaryQuestionnaire--6053fc57425a101d610d2c71804f0006"),
                "answer": (By.ID, "855ef6dee3b401657d515ed0f23b671f")
            },
            {
                "button": (By.ID, "primaryQuestionnaire--6053fc57425a101d610d2c71804f0009"),
                "answer": (By.ID, "855ef6dee3b401a926e5e6cff23b0f1a")
            },
            {
                "button": (By.ID, "primaryQuestionnaire--6053fc57425a101d610d2da55acd0003"),
                "answer": (By.ID, "855ef6dee3b401acd31fd0d1f23b4730")
            },
            {
                "button": (By.ID, "primaryQuestionnaire--6053fc57425a101d610d2ed909ba0003"),
                "answer": (By.ID, "855ef6dee3b401ccefcb5dd0f23b5f1f")
            },
            {
                "button": (By.ID, "primaryQuestionnaire--6053fc57425a101d610d2ed909ba0009"),
                "answer": (By.ID, "06016c4083e5101d610bb289ca300000")
            }
        ]

        try:
            for i, q in enumerate(questions, 1):
                logger.info(f"Handling question {i}...")
                
                # Click the question button to open dropdown
                button = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable(q["button"])
                )
                self.driver.execute_script("arguments[0].scrollIntoView(true);", button)
                time.sleep(0.5)
                button.click()
                logger.info(f"Clicked question button {i}")
                
                # Wait for and click the answer
                answer = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable(q["answer"])
                )
                answer.click()
                logger.info(f"Selected answer for question {i}")
                time.sleep(0.5)  # Small pause between questions
                
            logger.info("Successfully completed all application questions")
            return True
            
        except TimeoutException as e:
            logger.error(f"Timeout while handling application questions: {e}")
            return False
        except Exception as e:
            logger.error(f"Error handling application questions: {e}")
            return False

    def handle_voluntary_disclosures(self) -> bool:
        """Handles the voluntary disclosures section of the application."""
        logger.info("Handling voluntary disclosures...")
        
        try:
            # Handle ethnicity selection
            logger.info("Selecting ethnicity...")
            ethnicity_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.ID, "personalInfoUS--ethnicity"))
            )
            self.driver.execute_script("arguments[0].scrollIntoView(true);", ethnicity_button)
            time.sleep(0.5)
            ethnicity_button.click()
            
            ethnicity_option = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.ID, "3110e91abc9301bbc1f909b3b5e7596c"))
            )
            ethnicity_option.click()
            logger.info("Selected ethnicity")
            time.sleep(0.5)
            
            # Handle gender selection
            logger.info("Selecting gender...")
            gender_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.ID, "personalInfoUS--gender"))
            )
            self.driver.execute_script("arguments[0].scrollIntoView(true);", gender_button)
            time.sleep(0.5)
            gender_button.click()
            
            gender_option = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.ID, "3110e91abc9301f0fe4d3baab6e7666c"))
            )
            gender_option.click()
            logger.info("Selected gender")
            time.sleep(0.5)
            
            # Handle terms and conditions checkbox
            logger.info("Accepting terms and conditions...")
            checkbox_selector = (By.ID, "termsAndConditions--acceptTermsAndAgreements")
            
            # 1. Wait for presence first
            terms_checkbox = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(checkbox_selector)
            )
            logger.info("Terms checkbox found in DOM.")
            
            # 2. Scroll into center view
            logger.info("Scrolling terms checkbox into center view...")
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});", terms_checkbox)
            
            # 3. Pause slightly longer for animations/settling
            time.sleep(1.5)  

            # 5. Try JavaScript click first, then direct click as fallback
            logger.info("Attempting to click terms checkbox (JS first)...")
            try:
                # Use the element found by presence wait
                if not terms_checkbox.is_enabled():
                     logger.warning("Terms checkbox found but is disabled. Cannot click.")
                     return False # Can't click a disabled element
                     
                # Try JS click first
                self.driver.execute_script("arguments[0].click();", terms_checkbox)
                logger.info("JavaScript click executed on terms checkbox.")
                # Verify selection after a brief pause
                time.sleep(0.5)
                
                # Refresh element state before checking selection
                terms_checkbox = self.driver.find_element(*checkbox_selector) # Re-find to avoid staleness
                if not terms_checkbox.is_selected():
                    logger.warning("Checkbox not selected after JS click, attempting direct click...")
                    # Ensure it's interactable before direct click attempt
                    WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable(checkbox_selector)).click()
                    time.sleep(0.5)
                    # Re-check after direct click
                    terms_checkbox = self.driver.find_element(*checkbox_selector) # Re-find again
                
                # Final check
                if terms_checkbox.is_selected():
                     logger.info("Accepted terms and conditions successfully.")
                else:
                     logger.error("Failed to select the terms and conditions checkbox after JS and direct click attempts.")
                     # Optional: Add screenshot here
                     self.driver.save_screenshot("terms_checkbox_failure.png")
                     return False # Indicate failure
                     
            except TimeoutException:
                logger.error("Timeout waiting for checkbox to be clickable during fallback direct click.")
                self.driver.save_screenshot("terms_checkbox_timeout.png")
                return False
            except Exception as e:
                logger.error(f"Error clicking terms checkbox: {e}")
                # Optional: Add screenshot here
                self.driver.save_screenshot("terms_checkbox_error.png")
                return False # Indicate failure
            
            logger.info("Successfully completed voluntary disclosures")
            return True
            
        except TimeoutException as e:
            logger.error(f"Timeout while handling voluntary disclosures: {e}")
            return False
        except Exception as e:
            logger.error(f"Error handling voluntary disclosures: {e}")
            return False

    def handle_final_submission(self) -> bool:
        """Handles the final submission of the application."""
        logger.info("Handling final application submission...")
        
        try:
            # Find and click the submit button
            submit_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-automation-id="pageFooterNextButton"]'))
            )
            
            # Scroll the button into view
            self.driver.execute_script("arguments[0].scrollIntoView(true);", submit_button)
            time.sleep(0.5)
            
            # Click the submit button
            submit_button.click()
            logger.info("Clicked final submit button")
            
            # Wait for confirmation or next page
            time.sleep(5)  # Wait for submission to process
            
            logger.info("Successfully submitted application")
            return True
            
        except TimeoutException as e:
            logger.error(f"Timeout while handling final submission: {e}")
            return False
        except Exception as e:
            logger.error(f"Error handling final submission: {e}")
            return False

    def run_full_application(self, job_url: str, job_description: str, generated_pdf_path: Path):
        """Orchestrates the application process up to filling experience and uploading resume."""
        if not self.navigate_to_job_page(job_url):
            logger.error("Failed to navigate to job page. Aborting.")
            return False

        if not self.navigate_to_apply_page():
             logger.error("Failed to navigate to the Workday apply page. Aborting.")
             return False
        
        if not self.check_and_sign_in():
            logger.error("Sign in check or process failed. Aborting.")
            return False

        if not self.click_use_last_application():
            logger.error("Failed to click 'Use My Last Application'. Aborting.")
            return False

        if not self.handle_referral_source():
             logger.error("Failed to handle the referral source section. Aborting.")
             return False

        if not self.click_save_and_continue():
            logger.error("Failed to click Save and Continue after referral section. Aborting.")
            return False
        
        # --- Handle Resume Upload --- 
        logger.info("Handling resume upload...")
        if not self.handle_resume_upload(generated_pdf_path):
             logger.error("Failed to upload resume. Aborting.")
             return False
        # --------------------------
        
        # --- Fill Role Descriptions --- 
        logger.info("Generating role descriptions...")
        role_descriptions = self._generate_role_descriptions(job_description)
        if not role_descriptions:
             logger.error("Failed to generate role descriptions. Aborting.")
             return False
             
        logger.info("Filling role descriptions into Workday form...")
        if not self.fill_role_descriptions(role_descriptions):
             logger.error("Failed to fill one or more role descriptions. Aborting (or handle partially). ")
             return False 
        # ---------------------------

        if not self.click_save_and_continue():
            logger.error("Failed to click Save and Continue after role descriptions. Aborting.")
            return False

        # --- Handle Application Questions ---
        logger.info("Handling application questions...")
        if not self.handle_application_questions():
            logger.error("Failed to complete application questions. Aborting.")
            return False
        # ---------------------------

        if not self.click_save_and_continue():
            logger.error("Failed to click Save and Continue after application questions. Aborting.")
            return False

        # --- Handle Voluntary Disclosures ---
        logger.info("Handling voluntary disclosures...")
        if not self.handle_voluntary_disclosures():
            logger.error("Failed to complete voluntary disclosures. Aborting.")
            return False
        # ---------------------------

        if not self.click_save_and_continue():
            logger.error("Failed to click Save and Continue after voluntary disclosures. Aborting.")
            return False

        # --- Handle Final Submission ---
        logger.info("Handling final application submission...")
        if not self.handle_final_submission():
            logger.error("Failed to submit final application. Aborting.")
            return False
        # ---------------------------

        logger.info("Successfully completed all sections of the application and submitted")
        return True

# --- Updated Test Logic --- 
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(module)s:%(funcName)s:%(lineno)d] - %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
    load_dotenv()

    test_job_url = "https://careers.walmart.com/us/jobs/WD2098898-staff-technical-program-manager" 
    test_job_description = """ 
    Manage technical programs, requiring strong understanding of software development cycles, 
    cloud technologies (GCP/Azure), data analysis, and stakeholder communication. 
    Experience with Python, SQL, and project management tools needed. 
    Focus on driving project execution and managing risks.
    """ 
    # --- Define path to the generated PDF for testing --- 
    test_generated_pdf = Path("generated_pdfs_test/edited_resume_for_test_job.pdf")
    if not test_generated_pdf.is_file():
        logger.error(f"Test PDF file not found: {test_generated_pdf}")
        logger.error("Please run pdf_generator.py first to create the resume PDF.")
        sys.exit(1)
    # ----------------------------------------------------

    submitter = None 
    try:
        logger.info("--- Running Application Submitter Test --- ")
        submitter = ApplicationSubmitter() 
        
        if not submitter.email or not submitter.password or not submitter.cv_content or not submitter.model:
             logger.error("Submitter initialization failed (missing credentials, CV, or LLM). Exiting.")
             sys.exit(1)
             
        success = submitter.run_full_application(test_job_url, test_job_description, test_generated_pdf)

        if success:
            logger.info("Application process successful up to filling experience & uploading resume!")
            logger.info("Pausing for 15 seconds before closing browser...")
            time.sleep(15)
        else:
            logger.error("Application process failed. Check logs.")
            # if submitter and submitter.driver:
            #     submitter.driver.save_screenshot("failure_screenshot.png")

    except Exception as e:
        logger.error(f"An unexpected error occurred during the test run: {e}", exc_info=True)
    finally:
        if submitter:
            submitter.close_driver()
        logger.info("--- Test Run Finished --- ") 