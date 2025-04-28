import json
import logging
from pathlib import Path
from typing import List, Dict, Union, Tuple # Use specific types
import datetime

# Configure logging (assuming main.py might configure root logger)
logger = logging.getLogger(__name__)

class JobFilter:
    def __init__(self, storage_file: str = "processed_jobs.json"):
        self.storage_file = Path(storage_file)
        self.processed_jobs = self._load_processed_jobs()

    def _load_processed_jobs(self) -> Dict[str, Dict]: # Store more info per job
        """Load the dictionary of processed jobs from storage."""
        if self.storage_file.exists():
            try:
                with open(self.storage_file, 'r') as f:
                    data = json.load(f)
                    # Basic validation: ensure it's a dict
                    if isinstance(data, dict):
                        logger.info(f"Loaded {len(data)} processed job records from {self.storage_file}")
                        return data
                    else:
                        logger.warning(f"Data in {self.storage_file} is not a dictionary. Initializing empty list.")
                        return {}
            except json.JSONDecodeError:
                logger.error(f"Error decoding JSON from {self.storage_file}. Initializing empty list.")
                return {}
            except Exception as e:
                logger.error(f"Error reading processed jobs file {self.storage_file}: {str(e)}. Initializing empty list.")
                return {}
        logger.info(f"Processed jobs file {self.storage_file} not found. Initializing empty list.")
        return {}

    def _save_processed_jobs(self):
        """Save the dictionary of processed jobs to storage."""
        try:
            with open(self.storage_file, 'w') as f:
                json.dump(self.processed_jobs, f, indent=2, sort_keys=True)
            logger.debug(f"Successfully saved {len(self.processed_jobs)} processed jobs to {self.storage_file}")
        except Exception as e:
            logger.error(f"Failed to save processed jobs to {self.storage_file}: {str(e)}")

    def get_jobs_to_process(self, found_jobs: List[Dict[str, str]]) -> Tuple[List[Dict], List[Dict]]:
        """Identify jobs that need processing.

        Separates jobs into two lists:
        1. new_jobs: Jobs not previously seen (URL not in processed_jobs.json).
        2. retry_jobs: Jobs previously seen but ended in an error state
                      (status is not 'Applied' or 'Not Relevant').

        Returns:
            Tuple[List[Dict], List[Dict]]: A tuple containing (new_jobs, retry_jobs).
        """
        new_jobs = []
        retry_jobs = []
        final_statuses = {"Applied", "Not Relevant"} # Statuses that mean we shouldn't retry

        for job in found_jobs:
            job_url = job.get('url')
            if not job_url:
                logger.warning(f"Found job listing with missing URL: {job.get('title', '[No Title]')}")
                continue

            if job_url not in self.processed_jobs:
                new_jobs.append(job)
                logger.info(f"Identified new job to evaluate: {job.get('title', '[No Title]')} ({job_url})")
            else:
                # Job exists in processed_jobs, check its status
                job_entry = self.processed_jobs[job_url]
                current_status = job_entry.get('status')
                job_title = job.get('title', job_entry.get('title', '[No Title]')) # Use latest title

                if current_status and current_status not in final_statuses:
                    retry_jobs.append(job) # Add the job found *now* for reprocessing
                    logger.info(f"Identified job to retry (status: {current_status}): {job_title} ({job_url})")
                else:
                    # Job has a final status or no status, skip it
                    logger.debug(f"Skipping already processed job with final status '{current_status}': {job_title} ({job_url})")

        total_to_process = len(new_jobs) + len(retry_jobs)
        logger.info(f"Found {len(found_jobs)} jobs total. {total_to_process} need processing ({len(new_jobs)} new, {len(retry_jobs)} retries).")
        return new_jobs, retry_jobs

    def update_job_status(self, job_url: str, title: str, status: str, explanation: str = None):
        """Update the status of a job in the processed list and save.
        
        Args:
            job_url: The unique URL of the job.
            title: The job title.
            status: The new status (e.g., 'Relevant', 'Not Relevant', 'Error_Scraping', 'Error_Checking_Relevance').
            explanation: Optional further details or reason for the status.
        """
        if not job_url:
            logger.error("Attempted to update status for a job with no URL.")
            return

        now = datetime.datetime.now().isoformat()
        
        # Ensure the entry exists even if it wasn't strictly "new" (e.g., reprocessing errors)
        if job_url not in self.processed_jobs:
             self.processed_jobs[job_url] = {"title": title, "history": []}
        elif "title" not in self.processed_jobs[job_url] or not self.processed_jobs[job_url]["title"]:
            self.processed_jobs[job_url]["title"] = title # Update title if missing
            
        # Update status and add to history
        self.processed_jobs[job_url]['last_updated'] = now
        self.processed_jobs[job_url]['status'] = status
        if explanation:
             self.processed_jobs[job_url]['explanation'] = explanation
        else:
            self.processed_jobs[job_url].pop('explanation', None) # Remove explanation if None
            
        # Optional: Keep a history log
        history_entry = {"timestamp": now, "status": status, "explanation": explanation}
        if "history" not in self.processed_jobs[job_url]:
             self.processed_jobs[job_url]["history"] = []
        self.processed_jobs[job_url]["history"].append(history_entry)
        
        logger.info(f"Updated status for '{title}' ({job_url}) to: {status}")
        self._save_processed_jobs()

# Keep main for standalone testing of filter logic if needed
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Test data
    test_jobs_found = [
        {"title": "Data Scientist", "url": "https://careers.walmart.com/job1"},
        {"title": "Data Engineer", "url": "https://careers.walmart.com/job2"},      # Assume job2 is processed
        {"title": "Data Analyst", "url": "https://careers.walmart.com/job3"},
        {"title": "Software Engineer", "url": "https://careers.walmart.com/job4"},   # Assume job4 is processed
    ]
    
    # Initialize filter (will create/read processed_jobs.json)
    job_filter = JobFilter()
    
    # Simulate some previously processed jobs
    job_filter.processed_jobs = {
        "https://careers.walmart.com/job2": { "title": "Data Engineer", "status": "Applied", "last_updated": "..." },
        "https://careers.walmart.com/job4": { "title": "Software Engineer", "status": "Not Relevant", "last_updated": "..." }
    }
    print(f"Initial processed jobs (simulated): {list(job_filter.processed_jobs.keys())}")

    # Filter jobs
    new_jobs, retry_jobs = job_filter.get_jobs_to_process(test_jobs_found)
    
    # Print results
    print(f"\nFound {len(new_jobs)} new jobs and {len(retry_jobs)} retry jobs out of {len(test_jobs_found)} total jobs found:")
    for job in new_jobs:
        print(f"  - New job: {job['title']} - {job['url']}")
    for job in retry_jobs:
        print(f"  - Retry job: {job['title']} - {job['url']}")
        
    # Test updating status
    if new_jobs or retry_jobs:
        print("\nTesting status update...")
        test_job_to_update = new_jobs[0] if new_jobs else retry_jobs[0]
        job_filter.update_job_status(test_job_to_update['url'], test_job_to_update['title'], "Relevant", "LLM determined fit.")
        job_filter.update_job_status("https://careers.walmart.com/job3", "Data Analyst", "Not Relevant", "Mismatch based on LLM.")
        print(f"Current state of processed jobs in memory: {job_filter.processed_jobs}")
        # Note: This test will write to processed_jobs.json
    else:
        print("\nNo new or retry jobs to test status update.") 