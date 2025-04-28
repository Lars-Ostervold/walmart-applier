import logging
import google.generativeai as genai
import os
from dotenv import load_dotenv
from pathlib import Path
from typing import Union, Tuple

logger = logging.getLogger(__name__)

class RelevanceChecker:
    def __init__(self, resume_path: str = "base_resume.md"):
        self.resume_path = Path(resume_path)
        self.resume_content = self._load_resume()
        self._configure_llm()

    def _load_resume(self) -> Union[str, None]:
        """Load the resume content from the specified Markdown file."""
        if not self.resume_path.is_file():
            logger.error(f"Resume file not found at: {self.resume_path}")
            return None
        try:
            # Attempt to read with UTF-8 first, then fallback to latin-1 if needed
            try:
                with open(self.resume_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                logger.warning(f"UTF-8 decoding failed for {self.resume_path}. Trying latin-1.")
                with open(self.resume_path, 'r', encoding='latin-1') as f:
                    content = f.read()

            logger.info(f"Successfully loaded resume from {self.resume_path}")
            return content
        except Exception as e:
            logger.error(f"Error reading resume file {self.resume_path}: {str(e)}")
            return None

    def _configure_llm(self):
        """Configure the Google Generative AI client."""
        load_dotenv() # Load environment variables from .env file
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logger.error("GOOGLE_API_KEY not found in environment variables. Please set it in a .env file.")
            self.model = None
            return
        
        try:
            genai.configure(api_key=api_key)
            # Use a Gemini model suitable for text generation/analysis (Flash is faster/cheaper)
            self.model = genai.GenerativeModel('gemini-2.0-flash-lite') 
            logger.info("Google Generative AI configured successfully using gemini-2.0-flash-lite.")
        except Exception as e:
            logger.error(f"Failed to configure Google Generative AI: {str(e)}")
            self.model = None

    def check_relevance(self, job_title: str, job_description: str) -> Tuple[Union[str, None], Union[str, None]]:
        """Check job relevance using the LLM based on resume and job description.

        Returns:
            tuple[Union[str, None], Union[str, None]]: (status, explanation)
            Status can be 'Relevant', 'Not Relevant', or None if an error occurred.
            Explanation is the LLM's reasoning or an error message.
        """
        if not self.model:
            return None, "LLM not configured."
        if not self.resume_content:
            return None, "Resume content not loaded."
        if not job_description:
            logger.warning(f"Job description for '{job_title}' is empty or None. Skipping relevance check.")
            return None, "Job description is empty."

        prompt = f"""
        Analyze the following job description for relevance based on the provided user resume/profile.

        User Profile (from Resume - Markdown format):
        --- START RESUME ---
        {self.resume_content}
        --- END RESUME ---

        Job Title: {job_title}

        Job Description:
        --- START DESCRIPTION ---
        {job_description}
        --- END DESCRIPTION ---

        Hard Rules: 
        1. The job MUST NOT require Java as a primary skill or core responsibility. Mentioning Java incidentally or as a 'nice to have' is okay, but if it's a fundamental requirement for the role, the job is not relevant.
        2. The job MUST NOT require big data technologies like Hadoop, Spark, or Kafka as a primary skill or core responsibility. Mentioning them incidentally or as a 'nice to have' is okay, but if it's a fundamental requirement for the role, the job is not relevant.

        Instructions:
        1. Assess the alignment between the user's skills/experience in the resume and the requirements/responsibilities in the job description. Consider the overall focus of the role.
        2. Strictly check if the hard rules are violated.
        3. Determine if the job is a relevant match for the user based on both skills alignment AND the hard rules.
        4. Respond with ONLY the word 'Relevant' or 'Not Relevant'.
        5. On the next line, provide a brief, one-sentence explanation for your decision. If a hard rule was the deciding factor, mention it explicitly (e.g., 'Violates Java rule', 'Violates big data rule').
        
        Example Response 1:
        Relevant
        The role aligns well with the candidate's data science background and Python skills.
        
        Example Response 2:
        Not Relevant
        This position requires extensive Java development as a core responsibility, violating the user's constraint (Violates Java rule).
        
        Example Response 3:
        Not Relevant
        Requires deep experience with Spark and Hadoop which is not in the user profile (Violates big data rule).

        Example Response 4:
        Not Relevant
        The candidate's experience is primarily in data analysis, while this role focuses heavily on platform engineering unrelated to their background.

        Your Response:
        """

        # Limit description size to avoid excessive token usage (adjust limit as needed)
        max_desc_length = 15000 # Approx character limit
        if len(job_description) > max_desc_length:
             logger.warning(f"Job description for '{job_title}' is very long ({len(job_description)} chars). Truncating for LLM analysis.")
             job_description = job_description[:max_desc_length] + "..."


        try:
            logger.info(f"Sending request to Gemini for job: {job_title}")
            response = self.model.generate_content(prompt)
            
            # Robust parsing of the response
            response_text = getattr(response, 'text', '').strip()
            lines = [line.strip() for line in response_text.split('\n') if line.strip()]
            
            if not lines:
                 # Handle cases where the response might be blocked or empty
                 feedback = getattr(response, 'prompt_feedback', 'Unknown feedback')
                 logger.warning(f"LLM returned an empty or blocked response for '{job_title}'. Feedback: {feedback}")
                 return None, f"LLM returned empty/blocked response. Feedback: {feedback}"

            status = lines[0]
            explanation = lines[1] if len(lines) >= 2 else "No explanation provided by LLM."
            
            if status == 'Relevant':
                logger.info(f"LLM relevance check result for '{job_title}': {status} - {explanation}")
                return status, explanation
            elif status == 'Not Relevant':
                 logger.info(f"LLM relevance check result for '{job_title}': {status} - {explanation}")
                 return status, explanation
            else:
                # If the first line isn't exactly 'Relevant' or 'Not Relevant', treat as unexpected
                logger.warning(f"LLM returned unexpected status line: '{status}'. Full response: {response_text}")
                # Return the raw first line as explanation for debugging
                return None, f"LLM returned unexpected status: '{status}'"

        except Exception as e:
            # Catch potential API errors or other issues during generation
            logger.error(f"Error calling Gemini API for job '{job_title}': {str(e)}")
            # Attempt to access specific error details if available in the exception
            error_details = getattr(e, 'message', str(e))
            return None, f"LLM API call failed: {error_details}"

# Example Usage (for testing this script directly)
if __name__ == '__main__':
    # Need sys for exit and stdout handler
    import sys 

    # Configure logging for standalone testing
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)] # Ensure logs go to console
    )
    
    # --- CONFIGURATION FOR TESTING ---
    # 1. Create a .env file with GOOGLE_API_KEY=YOUR_API_KEY
    # 2. Place your resume (e.g., base_resume.md) in the project directory
    # 3. Update the resume_file_name if needed
    resume_file_name = "base_resume.md" # <--- Make sure this file exists!
    # ---------------------------------

    if not Path(resume_file_name).exists():
        logger.error(f"Error: Resume file '{resume_file_name}' not found. Please create it or update the path.")
        sys.exit(1) # Exit if resume is missing for testing

    checker = RelevanceChecker(resume_path=resume_file_name)
    
    # Sample job data for testing
    test_title_ok = "Senior Data Scientist"
    test_description_ok = """
    Seeking a Senior Data Scientist to lead projects using Python, R, and SQL. 
    Responsibilities include building machine learning models, performing statistical analysis, 
    and communicating findings. Experience with cloud platforms (AWS/GCP) is a plus. 
    Knowledge of Java is helpful for interfacing with legacy systems but not required.
    Knowledge of Spark is helpful but not required.
    """

    test_title_java = "Backend Java Engineer"
    test_description_java = """
    Join our team as a Java developer! You will design, build, and maintain efficient, reusable, 
    and reliable Java code. Strong understanding of Spring Boot, Hibernate, and microservices required. 
    Python scripting is a small part of the role for automation tasks.
    """
    
    test_title_bigdata = "Big Data Platform Engineer"
    test_description_bigdata = """
    Build and maintain our large-scale data processing platform using Hadoop, Spark, and Kafka. 
    Requires deep expertise in distributed systems and experience optimizing Spark jobs. 
    Experience with Python or Scala is necessary.
    """

    test_title_mismatch = "Marketing Manager"
    test_description_mismatch = """
    Looking for a dynamic Marketing Manager to lead campaigns and manage social media presence. 
    Requires experience in digital marketing, SEO, and content creation. No coding required.
    """

    if checker.model and checker.resume_content:
        print("\n--- Testing Relevant Job (OK) ---")
        status, explanation = checker.check_relevance(test_title_ok, test_description_ok)
        print(f"Status: {status}, Explanation: {explanation}")

        print("\n--- Testing Irrelevant Job (Java) ---")
        status, explanation = checker.check_relevance(test_title_java, test_description_java)
        print(f"Status: {status}, Explanation: {explanation}")
        
        print("\n--- Testing Irrelevant Job (Big Data) ---")
        status, explanation = checker.check_relevance(test_title_bigdata, test_description_bigdata)
        print(f"Status: {status}, Explanation: {explanation}")
        
        print("\n--- Testing Irrelevant Job (Mismatch) ---")
        status, explanation = checker.check_relevance(test_title_mismatch, test_description_mismatch)
        print(f"Status: {status}, Explanation: {explanation}")

        print("\n--- Testing with Empty Description ---")
        status, explanation = checker.check_relevance("Empty Desc Job", "")
        print(f"Status: {status}, Explanation: {explanation}")
    elif not checker.resume_content:
         print("\nTesting skipped: Resume content could not be loaded.")
    else: # Implies model setup failed
        print("\nTesting skipped: LLM model not configured. Check API key and .env file.") 