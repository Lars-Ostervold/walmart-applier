import logging
import google.generativeai as genai
import os
from dotenv import load_dotenv
from pathlib import Path
from typing import Union
import re # Import re for cleaning

logger = logging.getLogger(__name__)

class ResumeEditor:
    def __init__(self, base_resume_path: str = "base_resume.md", cv_path: str = "cv.md"):
        self.base_resume_path = Path(base_resume_path)
        self.cv_path = Path(cv_path)
        self.base_resume_content = self._load_file_content(self.base_resume_path, "Base Resume")
        self.cv_content = self._load_file_content(self.cv_path, "CV")
        self.model = self._configure_llm()

    def _load_file_content(self, file_path: Path, file_description: str) -> Union[str, None]:
        """Load text content from a file."""
        if not file_path.is_file():
            logger.error(f"{file_description} file not found at: {file_path}")
            return None
        try:
            # Try UTF-8 first, fallback to latin-1
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                logger.warning(f"UTF-8 decoding failed for {file_path}. Trying latin-1.")
                with open(file_path, 'r', encoding='latin-1') as f:
                    content = f.read()
            logger.info(f"Successfully loaded {file_description} from {file_path}")
            return content
        except Exception as e:
            logger.error(f"Error reading {file_description} file {file_path}: {str(e)}")
            return None

    def _configure_llm(self) -> Union[genai.GenerativeModel, None]:
        """Configure and return the Google Generative AI client."""
        load_dotenv()
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logger.error("GOOGLE_API_KEY not found in environment variables. Please set it in a .env file.")
            return None
        try:
            genai.configure(api_key=api_key)
            # Using a model capable of potentially longer generation
            model = genai.GenerativeModel('gemini-2.0-flash-lite') 
            logger.info("Google Generative AI configured successfully for resume editing.")
            return model
        except Exception as e:
            logger.error(f"Failed to configure Google Generative AI: {str(e)}")
            return None

    def _clean_llm_markdown_output(self, raw_text: str) -> str:
        """Removes common LLM artifacts like surrounding code fences from Markdown output."""
        cleaned_text = raw_text.strip()
        # Pattern to match ``` optionally followed by language name, newline, content, newline, ```
        # Uses re.DOTALL to make '.' match newlines
        pattern = r"^```(?:[a-zA-Z0-9_\-]+)?\s*\n(.*?)\n```$"
        match = re.match(pattern, cleaned_text, re.DOTALL)
        if match:
            logger.debug("Removed surrounding Markdown code block fences.")
            cleaned_text = match.group(1).strip()
        else:
            # Simpler check for just the fences if the above didn't match
            if cleaned_text.startswith("```") and cleaned_text.endswith("```"):
                 cleaned_text = cleaned_text[3:-3].strip()
                 # Could also try removing potential language identifier on first line
                 lines = cleaned_text.split('\n', 1)
                 if len(lines) > 1 and not lines[0].strip().startswith( ('#', '*', '-', '[') ): # Heuristic: language name likely doesn't start like MD
                     logger.debug("Removed simple surrounding fences and potential language identifier.")
                     cleaned_text = lines[1].strip()
                 else:
                     logger.debug("Removed simple surrounding fences.")
        return cleaned_text

    def edit_resume(self, job_title: str, job_description: str) -> Union[str, None]:
        """Edits the base resume using Gemini based on the job description and CV.

        Returns:
            The cleaned, edited resume content as a Markdown string, or None if an error occurred.
        """
        if not self.model:
            logger.error("LLM model not configured. Cannot edit resume.")
            return None
        if not self.base_resume_content:
            logger.error("Base resume content not loaded. Cannot edit resume.")
            return None
        if not self.cv_content:
            logger.warning("CV content not loaded. Editing will proceed without CV reference.")
        if not job_description:
            logger.error("Job description is empty. Cannot edit resume effectively.")
            return None

        prompt = f"""
        **Task:** Edit the provided Base Resume (Markdown format) to be highly optimized for the specific Job Description below. The resume should be dripping with keywords that are relevant to the job description and wow the ATS screening bots and the recruiter. Use relevant details from the Supplementary CV (Markdown format) to strengthen the resume's impact and alignment with the target role, but do not add skills or experiences the user doesn't possess. 

        The final output MUST be the complete, ATS-friendly edited resume in Markdown format, adhering STRICTLY to the formatting guidelines below, ready to be saved to a .md file.

        **Formatting Guidelines:**
        1.  **Header:** Start the document *immediately* with:
            *   The candidate's full name as a Level 1 Markdown Header (e.g., `# Lars Ostervold`).
            *   Followed *immediately* by a single paragraph containing contact information (e.g., `LOstervold@dow.com | 918.845.3010 | [LinkedIn](URL) | [GitHub](URL)`). Use pipe symbols (|) as separators.
        2.  **Sections:** Use Level 2 Markdown Headers (e.g., `## SUMMARY`, `## TECHNICAL SKILLS`, `## TECHNICAL EXPERIENCE`, `## PROJECTS`, `## EDUCATION`) for standard resume sections. Ensure these headers are ALL CAPS. Do not forget any sections from the base resume.
        3.  **Experience/Projects:**
            *   Use Level 3 Headers (e.g., `### Job Title | Company Name`) for job titles or project names.
            *   **Project Links:** If a project has a URL, include the Markdown link *within the H3 header itself*, like `### Project Name | [Link](URL)` or `### Project Name ([Link](URL))`. Do NOT put the link on a separate line.
            *   Immediately follow the H3 header line with a separate line for the date range, ideally using an en dash (–) like `Month YYYY – Present` or `Month YYYY – Month YYYY`.
            *   Use standard Markdown bullet points (`- ` or `* `) for responsibilities and achievements under each role/project.
        4.  **Strict Output:** The output MUST be ONLY the full, edited Markdown resume content, starting directly with the H1 Name header. Do not include *any* introductory text, explanations, ```markdown``` tags, or other text before or after the resume content.

        **VERY IMPORTANT Content Guidelines:**
        *   Keyword Optimization & Alignment: Thoroughly analyze the Target Job Description and strategically incorporate relevant keywords and phrases into the resume, particularly within the Summary/Profile, Skills, and Experience sections. Prioritize keywords that appear frequently and are critical requirements for the role. The resume should be absolutely dripping with keywords that are relevant to the job description.

        *   Quantifiable Achievements: Whenever possible, quantify accomplishments and responsibilities using specific numbers, percentages, and metrics. Draw these details from the Supplementary CV if they directly relate to the requirements of the Target Job Description. Frame these achievements to highlight their impact on previous organizations. Example: Instead of "Managed projects," aim for "Successfully managed 5 cross-functional projects concurrently, resulting in a 15% reduction in project timelines."

        *   Impactful Language: Employ strong action verbs and professional language to clearly articulate responsibilities and achievements. Focus on what you did and the results of your actions.

        *   ATS Compliance: Maintain a clean, professional, and easily parsable Markdown format. Use standard headings (e.g., "Summary," "Experience," "Skills," "Education"), clear bullet points, and avoid complex formatting that might confuse Applicant Tracking Systems (ATS).

        *   Truthful Representation: Only include skills and experiences that are accurately reflected in the Base Resume and Supplementary CV. Do not invent or exaggerate qualifications. Focus on presenting your existing qualifications in the most compelling way for this specific role.

        *   Summary/Profile Optimization: Craft a compelling Summary or Professional Profile that immediately highlights your key qualifications and aligns them with the core requirements of the Target Job Description. This section should act as a concise "elevator pitch" tailored to the specific role. This should absolutely WOW the recruiter and be heavily weighted towards the Target Job Description for ATS optimization.

        *   Experience Tailoring: For each role in the Experience section, focus on the responsibilities and achievements that are most relevant to the Target Job Description. Use bullet points to detail your contributions and quantify your impact where possible.


        **Inputs:**
        1. Base Resume (Markdown) - This is what a generic data scientist resume looks like.
        2. Supplementary CV (Markdown - for reference only) - This is supplemental information about the user that is not part of the base resume, but can be referenced to improve match of the resume to the job description.
        3. Target Job Title - This is the title of the job that the user is applying for.
        4. Target Job Description - This is the job description of the job that the user is applying for.

        **Base Resume (Markdown):**
        ```markdown
        {self.base_resume_content}
        ```

        **Supplementary CV (Markdown - for reference only):**
        ```markdown
        {self.cv_content if self.cv_content else 'CV content not available.'}
        ```

        **Target Job Title:** {job_title}

        **Target Job Description:**
        ```
        {job_description}
        ```

        **Output (Edited Markdown Resume ONLY):**
        """

        try:
            logger.info(f"Sending request to Gemini for resume editing for job: {job_title}")
            response = self.model.generate_content(prompt)
            
            raw_edited_resume_md = response.text.strip()
            
            cleaned_edited_resume_md = self._clean_llm_markdown_output(raw_edited_resume_md)

            if not cleaned_edited_resume_md or len(cleaned_edited_resume_md) < 100: 
                 feedback = getattr(response, 'prompt_feedback', 'Unknown feedback')
                 logger.warning(f"LLM response after cleaning is very short or empty. Might be an issue. Feedback: {feedback}. Original length: {len(raw_edited_resume_md)}, Cleaned length: {len(cleaned_edited_resume_md)}")
                 return None 
            
            logger.info(f"Successfully received and cleaned edited resume content from LLM for job: {job_title}")
            return cleaned_edited_resume_md

        except Exception as e:
            logger.error(f"Error calling Gemini API for resume editing '{job_title}': {str(e)}")
            return None

    def save_edited_resume(self, markdown_content: str, output_filename: Union[str, Path]) -> bool:
        """Saves the provided markdown content to a file."""
        output_path = Path(output_filename)
        # Ensure parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            logger.info(f"Successfully saved edited resume to: {output_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save edited resume to {output_path}: {str(e)}")
            return False

# Step 2: Add Test Case
if __name__ == '__main__':
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - [%(module)s:%(funcName)s] - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )

    # --- Configuration for Testing ---
    # Ensure these files exist for the test
    test_base_resume = Path("base_resume.md") 
    test_cv = Path("cv.md") 
    test_output_dir = Path("edited_resumes_test")
    test_output_filename = test_output_dir / "edited_resume_for_test_job.md"
    
    # Create dummy files if they don't exist for testing purposes
    if not test_base_resume.exists():
        logger.warning(f"Creating dummy {test_base_resume} for testing.")
        test_base_resume.parent.mkdir(parents=True, exist_ok=True)
        with open(test_base_resume, "w") as f:
            f.write("# Base Resume\n\n## Experience\n- Did stuff at Old Job")
    if not test_cv.exists():
        logger.warning(f"Creating dummy {test_cv} for testing.")
        test_cv.parent.mkdir(parents=True, exist_ok=True)
        with open(test_cv, "w") as f:
            f.write("# Full CV\n\n## Detailed Experience\n- Did specific thing X using Python at Old Job (2020-2022)")
            
    # Ensure output directory exists
    test_output_dir.mkdir(exist_ok=True)

    # Sample Job Data
    test_job_title = "Python Data Analyst"
    test_job_description = """
    We need a Data Analyst proficient in Python and SQL to analyze data and create reports. 
    Experience with data visualization libraries like Matplotlib or Seaborn is required. 
    Must communicate findings clearly.
    """
    # ---------------------------------

    logger.info("--- Running Standalone Resume Editor Test ---")
    
    editor = ResumeEditor(base_resume_path=str(test_base_resume), cv_path=str(test_cv))

    if not editor.model:
        logger.error("LLM Model not configured. Exiting test. Check GOOGLE_API_KEY.")
        sys.exit(1)
    if not editor.base_resume_content:
        logger.error("Base resume content not loaded. Exiting test.")
        sys.exit(1)
        
    edited_md = editor.edit_resume(test_job_title, test_job_description)
    
    if edited_md:
        logger.info("Resume editing successful (content received and cleaned). Attempting to save...")
        saved = editor.save_edited_resume(edited_md, test_output_filename)
        if saved:
            logger.info(f"Test completed successfully. Edited resume saved to: {test_output_filename}")
        else:
            logger.error("Test failed: Could not save the edited resume.")
            sys.exit(1)
    else:
        logger.error("Test failed: Did not receive valid edited resume content from LLM after cleaning.")
        sys.exit(1) 