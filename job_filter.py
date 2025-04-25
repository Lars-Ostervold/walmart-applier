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

    def filter_new_jobs(self, found_jobs: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Identify jobs from the found list that are not yet in processed_jobs."""
        new_jobs_to_process = []
        urls_found = {job['url'] for job in found_jobs if 'url' in job} # Set of URLs found now
        processed_urls = set(self.processed_jobs.keys())

        for job in found_jobs:
            job_url = job.get('url')
            if job_url and job_url not in processed_urls:
                new_jobs_to_process.append(job)
                logger.info(f"Identified new job to evaluate: {job.get('title', '[No Title]')} ({job_url})")
            elif job_url:
                logger.debug(f"Skipping already processed job: {job.get('title', '[No Title]')} ({job_url})")

        logger.info(f"Found {len(found_jobs)} jobs total, {len(new_jobs_to_process)} are new and need evaluation.")
        return new_jobs_to_process

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
    new_jobs = job_filter.filter_new_jobs(test_jobs_found)
    
    # Print results
    print(f"\nFound {len(new_jobs)} new jobs out of {len(test_jobs_found)} total jobs found:")
    for job in new_jobs:
        print(f"  - New job: {job['title']} - {job['url']}")
        
    # Test updating status
    if new_jobs:
        print("\nTesting status update...")
        test_job_to_update = new_jobs[0]
        job_filter.update_job_status(test_job_to_update['url'], test_job_to_update['title'], "Relevant", "LLM determined fit.")
        job_filter.update_job_status("https://careers.walmart.com/job3", "Data Analyst", "Not Relevant", "Mismatch based on LLM.")
        print(f"Current state of processed jobs in memory: {job_filter.processed_jobs}")
        # Note: This test will write to processed_jobs.json
    else:
        print("\nNo new jobs to test status update.") 