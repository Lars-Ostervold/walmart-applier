import logging
import sys
import time
from pathlib import Path # Import Path
import re # Import re for filename sanitization
import argparse # Add argparse
from dotenv import load_dotenv # Add load_dotenv

# Import our modules
from job_discovery import discover_jobs_from_urls
from job_filter import JobFilter
from job_details_scraper import get_job_description
from relevance_checker import RelevanceChecker
from resume_editor import ResumeEditor # Import ResumeEditor
from pdf_generator import PdfGenerator # Import PdfGenerator
from application_submitter import ApplicationSubmitter # Import ApplicationSubmitter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(module)s:%(funcName)s] - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
        # Optionally add FileHandler here
        # logging.FileHandler("job_apply_run.log") 
    ]
)
logger = logging.getLogger(__name__) # Get logger for main script

# --- Configuration ---
URLS_TO_SCRAPE = [
    "https://careers.walmart.com/results?q=Data%20Scientist&page=1&sort=date&jobCity=Bentonville&jobState=AR&jobDepartmentCode=-872043147&expand=department,brand,type,rate&jobCareerArea=all",
    "https://careers.walmart.com/results?q=Data%20Analyst&page=1&sort=date&jobCity=Bentonville&jobState=AR&jobDepartmentCode=-872043147&expand=department,brand,type,rate&jobCareerArea=all",
    "https://careers.walmart.com/results?q=Big%20Data%20Engineer&page=1&sort=date&jobCity=Bentonville&jobState=AR&jobDepartmentCode=-872043147&expand=department,brand,type,rate&jobCareerArea=all"
]
BASE_RESUME_PATH = "base_resume.md"
CV_PATH = "cv.md"
PROCESSED_JOBS_FILE = "processed_jobs.json"
EDITED_RESUMES_DIR = Path("edited_resumes") # Define output directory
GENERATED_PDFS_DIR = Path("generated_pdfs") # Define PDF output directory
MAX_JOBS_TO_PROCESS = None # Will be set by args
# --- End Configuration ---

def sanitize_filename(filename: str) -> str:
    """Removes or replaces characters illegal in filenames."""
    # Remove illegal characters
    sanitized = re.sub(r'[<>:"/\\|?*]', '', filename)
    # Replace spaces with underscores (optional, but common)
    sanitized = sanitized.replace(' ', '_')
    # Limit length (optional)
    max_len = 100
    if len(sanitized) > max_len:
        sanitized = sanitized[:max_len]
    return sanitized

def run_job_pipeline(limit: int = None):
    logger.info("=== Starting Walmart Job Application Pipeline ===")
    load_dotenv() # Load environment variables early

    # --- 1. Discover Jobs ---
    logger.info("Step 1: Discovering jobs from target URLs...")
    all_found_jobs = discover_jobs_from_urls(URLS_TO_SCRAPE)
    if not all_found_jobs:
        logger.warning("No jobs were discovered. Exiting pipeline.")
        return
    logger.info(f"Discovered {len(all_found_jobs)} total potential jobs.")

    # --- 2. Filter New Jobs ---
    logger.info("Step 2: Filtering out previously processed jobs...")
    job_filter = JobFilter(storage_file=PROCESSED_JOBS_FILE)
    new_jobs, retry_jobs = job_filter.get_jobs_to_process(all_found_jobs)
    jobs_to_evaluate = new_jobs + retry_jobs
    
    if not jobs_to_evaluate:
        logger.info("No new or retry jobs found to evaluate. Exiting pipeline.")
        return
    logger.info(f"Total jobs to evaluate in this run: {len(jobs_to_evaluate)} ({len(new_jobs)} new, {len(retry_jobs)} retry)")

    # --- 3. Evaluate New Jobs ---
    logger.info("Step 3: Evaluating relevance of jobs...")
    relevance_checker = RelevanceChecker(resume_path=BASE_RESUME_PATH)
    relevant_jobs_for_editing = []
    evaluated_count = 0 # Counter for limit

    for i, job in enumerate(jobs_to_evaluate):
        # Apply Limit for Evaluation Step
        if limit is not None and evaluated_count >= limit:
            logger.info(f"Reached processing limit ({limit}). Stopping evaluation.")
            break 
        evaluated_count += 1

        job_title = job.get('title', '[No Title]')
        job_url = job.get('url')
        logger.info(f"-- Evaluating job {i+1}/{len(jobs_to_evaluate)} (Overall) | {evaluated_count}/{limit if limit else 'Unlimited'} (Processing Limit): '{job_title}' ({job_url}) --")

        if not job_url:
            logger.warning(f"Skipping job '{job_title}' due to missing URL.")
            continue

        # 3a. Scrape Job Description
        description = None
        try:
            description = get_job_description(job_url)
            time.sleep(1) 
        except Exception as e:
            logger.error(f"Error scraping description for {job_url}: {str(e)}")
            job_filter.update_job_status(job_url, job_title, "Error_Scraping", str(e))
            continue 

        if not description:
            logger.warning(f"Could not scrape description for {job_url}. Marking as error.")
            job_filter.update_job_status(job_url, job_title, "Error_Scraping", "Failed to retrieve description text.")
            continue

        # 3b. Check Relevance
        status = None
        explanation = None
        try:
            status, explanation = relevance_checker.check_relevance(job_title, description)
            time.sleep(1) 
        except Exception as e:
            logger.error(f"Error checking relevance for {job_url}: {str(e)}")
            job_filter.update_job_status(job_url, job_title, "Error_Checking_Relevance", str(e))
            continue

        # 3c. Update Status and Collect Relevant Jobs
        if status == "Relevant":
            logger.info(f"Job '{job_title}' marked as RELEVANT.")
            job['description'] = description # Store description for editing step
            relevant_jobs_for_editing.append(job)
            job_filter.update_job_status(job_url, job_title, "Relevant", explanation)
        elif status == "Not Relevant":
            logger.info(f"Job '{job_title}' marked as NOT RELEVANT. Reason: {explanation}")
            job_filter.update_job_status(job_url, job_title, "Not Relevant", explanation)
        else:
            logger.warning(f"Relevance check failed or returned unexpected status for {job_url}. Status: {status}, Explanation: {explanation}")
            job_filter.update_job_status(job_url, job_title, "Error_Checking_Relevance", f"Status: {status}, Explanation: {explanation}")

    # --- 4. Edit Resumes for Relevant Jobs ---
    # relevant_jobs_for_editing now contains only the jobs evaluated within the limit that were relevant
    logger.info(f"Step 4: Editing resumes for {len(relevant_jobs_for_editing)} relevant jobs (within limit)...")
    edited_resumes_paths = {}
    if relevant_jobs_for_editing:
        resume_editor = ResumeEditor(base_resume_path=BASE_RESUME_PATH, cv_path=CV_PATH)
        if not resume_editor.model or not resume_editor.base_resume_content:
             logger.error("Resume editor not properly configured. Skipping editing step.")
        else:
            for job in relevant_jobs_for_editing:
                job_title = job.get('title', '[No Title]')
                job_url = job.get('url')
                job_desc = job.get('description') 
                
                logger.info(f"-- Editing resume for: '{job_title}' ({job_url}) --")
                if not job_desc:
                    logger.warning(f"Skipping resume edit for '{job_title}' because description was missing.")
                    continue
                
                edited_md = resume_editor.edit_resume(job_title, job_desc)
                
                if edited_md:
                    sanitized_title = sanitize_filename(job_title)
                    job_id_match = re.search(r'WD(\d+)', job_url)
                    job_id = job_id_match.group(1) if job_id_match else "unknown_id"
                    output_filename = EDITED_RESUMES_DIR / f"resume_{sanitized_title}_{job_id}.md"
                    
                    saved = resume_editor.save_edited_resume(edited_md, output_filename)
                    if saved:
                        edited_resumes_paths[job_url] = str(output_filename)
                        logger.info(f"Successfully edited and saved resume to {output_filename}")
                    else:
                         logger.error(f"Failed to save edited resume for '{job_title}'.")
                    # Update status to reflect editing failure
                    job_filter.update_job_status(job_url, job_title, "Error_Editing_Resume", "LLM failed to generate edited resume.")
                else:
                    logger.error(f"Failed to edit resume using LLM for '{job_title}'.")
                    # Update status to reflect editing failure
                    job_filter.update_job_status(job_url, job_title, "Error_Editing_Resume", "LLM failed to generate edited resume.")
                
                time.sleep(1)

    # --- 5. Generate PDFs from Edited Resumes ---
    logger.info(f"Step 5: Generating PDFs for {len(edited_resumes_paths)} edited resumes...")
    generated_pdf_paths = {} # Dict {job_url: pdf_path or error status}
    if edited_resumes_paths:
        pdf_generator = PdfGenerator() 
        GENERATED_PDFS_DIR.mkdir(parents=True, exist_ok=True)
        
        # We need the job description again here. Let's find the original job data.
        # Create a quick lookup map from URL back to the job dict that includes description
        job_data_map = {job['url']: job for job in relevant_jobs_for_editing}
        
        for job_url, md_path_str in edited_resumes_paths.items():
            md_path = Path(md_path_str)
            
            # Retrieve the job description using the URL
            original_job_data = job_data_map.get(job_url)
            if not original_job_data or 'description' not in original_job_data:
                 logger.error(f"Could not find original job data or description for {job_url}. Skipping PDF generation.")
                 generated_pdf_paths[job_url] = "[FAILED_MISSING_DESC]"
                 job_filter.update_job_status(job_url, job_title, "Error_PDF_Generation", "Missing job description for PDF generation.") # Update status
                 continue
            job_desc = original_job_data['description']
            job_title = original_job_data.get('title', md_path.stem) # Get title for logging
            
            pdf_filename = GENERATED_PDFS_DIR / md_path.with_suffix('.pdf').name
            logger.info(f"-- Generating PDF for: '{job_title}' ({md_path.name}) -> {pdf_filename} --")
            
            # Pass the job_desc to the generator
            success = pdf_generator.generate_single_page_pdf(md_path, pdf_filename, job_desc)
            
            if success:
                generated_pdf_paths[job_url] = str(pdf_filename)
                logger.info(f"Successfully generated single-page PDF: {pdf_filename}")
            else:
                logger.error(f"Failed to generate single-page PDF for {md_path.name}. Check logs.")
                if pdf_filename.exists():
                     generated_pdf_paths[job_url] = f"[FAILED_1_PAGE] {pdf_filename}"
                else:
                     generated_pdf_paths[job_url] = "[FAILED_GENERATION]"
                job_filter.update_job_status(job_url, job_title, "Error_PDF_Generation", generated_pdf_paths[job_url]) # Update status
            
            time.sleep(0.5) 

    # --- 6. Summary ---
    logger.info("Step 6: PDF Generation complete.")
    successful_pdfs = {k: v for k, v in generated_pdf_paths.items() if not v.startswith("[FAILED")}
    failed_pdfs = {k: v for k, v in generated_pdf_paths.items() if v.startswith("[FAILED")}
    logger.info(f"Successfully generated {len(successful_pdfs)} single-page PDF resumes.")
    if successful_pdfs:
        logger.info("Generated PDF file paths:")
        for url, path in successful_pdfs.items():
            logger.info(f"  - {url} -> {path}")
    if failed_pdfs:
        logger.warning(f"{len(failed_pdfs)} PDFs failed generation or could not be shortened to one page:")
        for url, path_or_status in failed_pdfs.items():
             logger.warning(f"  - {url} -> {path_or_status}")

    # --- 7. Application Submission ---
    logger.info(f"Step 7: Submitting applications for {len(successful_pdfs)} jobs...")
    submitter = None
    submitted_count = 0
    try:
        if successful_pdfs:
            logger.info("Initializing application submitter...")
            submitter = ApplicationSubmitter(cv_path=CV_PATH)
            if not submitter.email or not submitter.password or not submitter.cv_content or not submitter.model:
                logger.error("Application Submitter initialization failed (missing credentials, CV, or LLM). Skipping submission step.")
            else:
                # We need the job data again here
                if not job_data_map: # Rebuild map if needed (though it should exist from PDF step)
                    job_data_map = {job['url']: job for job in relevant_jobs_for_editing}
                    
                for job_url, pdf_path_str in successful_pdfs.items():
                    pdf_path = Path(pdf_path_str)
                    original_job_data = job_data_map.get(job_url)

                    if not original_job_data or 'description' not in original_job_data:
                        logger.error(f"Cannot submit for {job_url}: Missing original job data or description.")
                        job_filter.update_job_status(job_url, "[Unknown Title]", "Error_Submitting", "Missing job data for submission.")
                        continue
                        
                    job_title = original_job_data.get('title', '[No Title]')
                    job_desc = original_job_data['description']
                    
                    logger.info(f"-- Attempting submission for: '{job_title}' ({job_url}) using PDF: {pdf_path} --")
                    
                    try:
                        submission_success = submitter.run_full_application(job_url, job_desc, pdf_path)
                        
                        if submission_success:
                            logger.info(f"Successfully submitted application for '{job_title}'!")
                            job_filter.update_job_status(job_url, job_title, "Applied", "Successfully submitted via automation.")
                            submitted_count += 1
                        else:
                            logger.error(f"Application submission failed for '{job_title}'. Check submitter logs.")
                            job_filter.update_job_status(job_url, job_title, "Error_Submitting", "Submission process failed. See logs.")
                            # Optional: Take a screenshot on failure from submitter if possible
                            # submitter.driver.save_screenshot(f"failure_{sanitize_filename(job_title)}.png")
                            
                    except Exception as submit_err:
                        logger.error(f"Unexpected error during submission for '{job_title}': {submit_err}", exc_info=True)
                        job_filter.update_job_status(job_url, job_title, "Error_Submitting", f"Unexpected exception: {submit_err}")
                        # Optional: Screenshot on unexpected error
                        # if submitter and submitter.driver:
                        #     submitter.driver.save_screenshot(f"unexpected_error_{sanitize_filename(job_title)}.png")
                            
                    # Add a delay between submissions if desired
                    logger.info("Pausing before next submission...")
                    time.sleep(10) 
                    
    except Exception as e:
        logger.error(f"An error occurred during the submission phase setup or loop: {e}", exc_info=True)
    finally:
        if submitter:
            logger.info("Closing application submitter WebDriver.")
            submitter.close_driver()

    logger.info(f"--- Submission Summary ---")
    logger.info(f"Attempted to submit for {len(successful_pdfs)} jobs.")
    logger.info(f"Successfully submitted {submitted_count} applications.")
    logger.info(f"Failed or skipped submissions: {len(successful_pdfs) - submitted_count}")
    # ---------------------------

    logger.info("=== Walmart Job Application Pipeline Finished ===")
    return generated_pdf_paths # Return generated PDFs map (or submission status map later)

if __name__ == "__main__":
    # Add Argument Parser
    parser = argparse.ArgumentParser(description="Run the Walmart Job Application Pipeline.")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit the number of new jobs to process through the full pipeline (evaluation, editing, PDF gen, submission)."
    )
    args = parser.parse_args()
    
    run_job_pipeline(limit=args.limit) # Pass limit to function