import logging
import sys
import time
from pathlib import Path # Import Path
import re # Import re for filename sanitization

# Import our modules
from job_discovery import discover_jobs_from_urls
from job_filter import JobFilter
from job_details_scraper import get_job_description
from relevance_checker import RelevanceChecker
from resume_editor import ResumeEditor # Import ResumeEditor
from pdf_generator import PdfGenerator # Import PdfGenerator

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

def run_job_pipeline():
    logger.info("=== Starting Walmart Job Application Pipeline ===")

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
    new_jobs = job_filter.filter_new_jobs(all_found_jobs)
    if not new_jobs:
        logger.info("No new jobs found to evaluate. Exiting pipeline.")
        return
    logger.info(f"Identified {len(new_jobs)} new jobs for evaluation.")

    # --- 3. Evaluate New Jobs ---
    logger.info("Step 3: Evaluating relevance of new jobs...")
    relevance_checker = RelevanceChecker(resume_path=BASE_RESUME_PATH, cv_path=CV_PATH) # Pass CV path too
    relevant_jobs_for_editing = []

    for i, job in enumerate(new_jobs):
        job_title = job.get('title', '[No Title]')
        job_url = job.get('url')
        logger.info(f"-- Evaluating job {i+1}/{len(new_jobs)}: '{job_title}' ({job_url}) --")

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
    logger.info(f"Step 4: Editing resumes for {len(relevant_jobs_for_editing)} relevant jobs...")
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
                else:
                    logger.error(f"Failed to edit resume using LLM for '{job_title}'.")
                
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

    # --- 7. Next Steps (Placeholder) ---
    # TODO: Implement Workday automation and application submission using the generated PDFs
    logger.info("Placeholder for next steps: Application Submission")

    logger.info("=== Walmart Job Application Pipeline Finished ===")
    return generated_pdf_paths

if __name__ == "__main__":
    run_job_pipeline() 