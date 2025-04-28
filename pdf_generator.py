import logging
import subprocess
import os
import sys
from pathlib import Path
from typing import Union
from pypdf import PdfReader # For reading page count
import google.generativeai as genai
from dotenv import load_dotenv
import re # Import re for cleaning
import shutil # Import shutil for file copying

try:
    from weasyprint import HTML, CSS
    from weasyprint.logger import PROGRESS_LOGGER
    # Silence WeasyPrint progress logs unless it's an error
    PROGRESS_LOGGER.setLevel(logging.ERROR)
except ImportError:
    print("Error: WeasyPrint is not installed. Please install it with 'pip install WeasyPrint'")
    print("Note: WeasyPrint may also require system dependencies (like pango, cairo, gdk-pixbuf). See WeasyPrint documentation.")
    sys.exit(1)

logger = logging.getLogger(__name__)

class PdfGenerator:
    # Removed pandoc_path, template_path. Added css_path.
    def __init__(self, css_path: str = "style.css", max_iterations: int = 10):
        self.css_path = Path(css_path)
        self.max_iterations = max_iterations
        self.model = self._configure_llm()

        if not self.css_path.exists():
             logger.warning(f"CSS stylesheet not found at {self.css_path}. PDF formatting may be incorrect.")
             # Allow to continue, but formatting will be default

    def _configure_llm(self) -> Union[genai.GenerativeModel, None]:
        """Configure and return the Google Generative AI client for shortening."""
        load_dotenv()
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logger.error("GOOGLE_API_KEY not found in environment variables.")
            return None
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-2.0-flash-lite')
            logger.info("Google Generative AI configured successfully for PDF generator.")
            return model
        except Exception as e:
            logger.error(f"Failed to configure Google Generative AI: {str(e)}")
            return None

    # Renamed from _clean_llm_markdown_output
    def _clean_llm_output(self, raw_text: str) -> str:
        """Removes common LLM artifacts like surrounding code fences from HTML output."""
        cleaned_text = raw_text.strip()
        # Pattern to match ``` optionally followed by language name (html), newline, content, newline, ```
        pattern = r"^```(?:html)?\s*\n(.*?)\n```$"
        match = re.match(pattern, cleaned_text, re.DOTALL | re.IGNORECASE)
        if match:
            logger.debug("Cleaned surrounding HTML code block fences (complex pattern).")
            cleaned_text = match.group(1).strip()
        else:
            # Simpler check for just the fences
            if cleaned_text.startswith("```") and cleaned_text.endswith("```"):
                 cleaned_text = cleaned_text[3:-3].strip()
                 logger.debug("Cleaned simple surrounding fences.")

        # Remove potential leading/trailing <html> or <body> tags if LLM added them
        cleaned_text = re.sub(r"^\s*<html[^>]*>", "", cleaned_text, flags=re.IGNORECASE | re.DOTALL).strip()
        cleaned_text = re.sub(r"</html\s*>\s*$", "", cleaned_text, flags=re.IGNORECASE | re.DOTALL).strip()
        cleaned_text = re.sub(r"^\s*<body[^>]*>", "", cleaned_text, flags=re.IGNORECASE | re.DOTALL).strip()
        cleaned_text = re.sub(r"</body\s*>\s*$", "", cleaned_text, flags=re.IGNORECASE | re.DOTALL).strip()

        return cleaned_text

    # Kept this function - it extracts info from the *input* Markdown
    def _extract_header_info(self, md_content: str) -> tuple[str, str, str]:
        """Extracts Name, Contact, and Body from Markdown.
        Handles H1 Name potentially followed by a blank line, then a contact paragraph.
        """
        name = ""
        contact = ""
        body = md_content # Default to full content
        lines = md_content.split('\n') # Split into all lines

        if len(lines) > 0 and lines[0].startswith('# '):
            name = lines[0][2:].strip()
            logger.info(f"Extracted Name: '{name}'")

            body_start_index = 1 # Default: body starts after name
            # Check line 1 (index 1)
            if len(lines) > 1 and lines[1].strip() and not lines[1].strip().startswith('#'):
                # Line 1 has non-empty content and is not a header: assume it's contact
                contact = lines[1].strip()
                logger.info(f"Extracted Contact (line 2): '{contact}'")
                body_start_index = 2 # Body starts after contact
            elif len(lines) > 2 and not lines[1].strip(): # Check if line 1 is blank
                # Line 1 is blank, check line 2 (index 2)
                if lines[2].strip() and not lines[2].strip().startswith('#'):
                     # Line 2 has non-empty content and is not a header: assume it's contact
                    contact = lines[2].strip()
                    logger.info(f"Extracted Contact (line 3 after blank): '{contact}'")
                    body_start_index = 3 # Body starts after contact and the preceding blank line
                else:
                     # Line 1 blank, Line 2 also blank or a header - no contact found near name
                     logger.warning("Found blank line after name, but no contact info on the next line.")
                     body_start_index = 1 # Treat everything after Name as body
            else:
                # Line 1 immediately follows name and is either empty or a header - no contact found
                logger.warning("Did not find contact info immediately after name.")
                body_start_index = 1 # Treat everything after Name as body

            # Join the rest of the lines for the body
            if len(lines) > body_start_index:
                body = "\n".join(lines[body_start_index:])
            else:
                body = "" # No body content found
        else:
            logger.warning("Could not extract Name header from input Markdown. Expected H1 for Name.")
            # Keep body as the full content if Name not found

        return name, contact, body.strip() # Return stripped body

    # Renamed from _run_pandoc. Uses WeasyPrint now.
    def _generate_pdf_from_html(self, html_body_content: str, name: str, contact: str, output_pdf_path: Path) -> bool:
        """Generates a PDF from HTML body content using WeasyPrint."""

        # --- Convert Markdown links in contact string to HTML links ---
        if contact:
            contact_html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', contact)
            logger.debug(f"Converted contact Markdown links to HTML: '{contact_html}'")
        else:
            contact_html = ''
        # ------------------------------------------------------------

        # Construct the full HTML document using the processed contact_html
        full_html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <title>{name if name else 'Resume'}</title>
            <link rel="stylesheet" href="{self.css_path.resolve().as_uri()}">
        </head>
        <body>
            <div class="header">
                <div class="name">{name if name else ''}</div>
                <div class="contact">{contact_html}</div>
            </div>
            <main>
                {html_body_content}
            </main>
        </body>
        </html>
        """

        logger.info(f"Generating PDF with WeasyPrint -> {output_pdf_path}")
        success = False
        try:
            HTML(string=full_html, base_url=str(Path().resolve())).write_pdf(output_pdf_path)
            logger.info(f"WeasyPrint generated PDF successfully: {output_pdf_path}")
            success = True
        except Exception as e:
            logger.error(f"WeasyPrint failed to generate PDF: {str(e)}")
        return success

    # Kept this function for reading PDF page count
    def _get_pdf_page_count(self, pdf_path: Path) -> Union[int, None]:
        """Reads a PDF and returns the number of pages."""
        try:
            if not pdf_path.exists() or pdf_path.stat().st_size == 0:
                logger.error(f"PDF file not found or is empty for page count check: {pdf_path}")
                return None
            reader = PdfReader(str(pdf_path))
            count = len(reader.pages)
            logger.info(f"PDF {pdf_path} has {count} page(s).")
            return count
        except Exception as e:
            logger.error(f"Failed to read PDF or get page count for {pdf_path}: {str(e)}")
            return None

    # Refactored prompt to shorten Markdown body
    def _shorten_resume_with_llm(self, md_body_content: str, job_description: str) -> Union[str, None]:
        """Uses LLM to shorten the resume MARKDOWN BODY content, returning condensed MARKDOWN BODY content."""
        if not self.model:
            logger.error("LLM not configured. Cannot shorten resume.")
            return None

        if not md_body_content:
             logger.warning("Markdown body content for shortening is empty.")
             return "" # Return empty string for Markdown

        prompt = f"""
        **Task:** Condense the key information from the following Markdown resume **BODY** so the resume fully fills a SINGLE PDF page. Use the provided Job Description as context to prioritize keeping the most relevant information. This is an iterative process, so make sure to only remove the least relevant information each iteration rather than making many changes at once.

        **Instructions & Order of Operations:**
        *   **Primary Goal:** Reduce the length of the BODY content by applying *only ONE* of the following actions in the listed order of preference. 
        *   **Actions (VERY IMPORTANT: Apply ONLY ONE per attempt):**
            *   **1)** Check for redundant degrees. If both BS and MS are present, remove the BS degree. If PhD, check if MS is present and remove it if so. Etc.
            *   **2)** Skill Categories: If the TECHNICAL SKILLS section has more than 4 categories, combine skills into 4 or fewer categories. **Crucially, do not remove individual skills listed.**
            *   **3)** Low-Impact Bullets: Identify and remove the single least relevant bullet point from the EXPERIENCE or PROJECTS section, considering the Target Job Description.
            *   **4)** Redundant Bullets: Identify and remove one bullet point in EXPERIENCE or PROJECTS that is very similar to another, keeping the more impactful one.
            *   **5)** Low-Impact Experience: If there are more than 2 entries in EXPERIENCE, remove the single least relevant *entire* experience entry.
            *   **6)** Low-Impact Project: If there are more than 2 entries in PROJECTS, remove the single least relevant *entire* project entry.
            *   **7)** Summary Polish: Rephrase the 'SUMMARY' section slightly to be more concise while retaining the core message and impact.
        *   **DO NOT UNDER ANY CIRCUMSTANCES UNDER PENALTY OF DEATH:**
            *   **Skills:** Never remove any specific skill listed under TECHNICAL SKILLS. You MAY reorganize categories if necessary.
            *   **Continued Education:** Do not remove the 'Continued Education' section if the job description mentions AI, ML, NLP, etc.
            *   **Summary:** Do not remove the 'SUMMARY' section entirely.
        *   **Preserve Core Value:** Avoid removing key achievements or essential skills highly relevant to the target job.
        *   **If No Action Possible:** If you cannot apply any of the above actions without violating the constraints, return the original Markdown body content **UNCHANGED**.
        *   **Output Format:** Return ONLY the condensed content formatted as clean, standard **Markdown**, suitable for the BODY section of a resume. Adhere to standard Markdown syntax (e.g., `##`, `###`, `-` or `*` for lists).
        *   **Crucially:** Do **NOT** include ````markdown` code fences in your output. Only provide the condensed Markdown resume BODY content.

        **Input Resume BODY (Markdown):**
        ```markdown
        {md_body_content}
        ```

        **Target Job Description (for context):**
        ```
        {job_description}
        ```

        **Condensed Markdown Resume BODY Content:**
        """

        try:
            logger.info("Sending request to Gemini to shorten resume body (Markdown)...")
            response = self.model.generate_content(prompt)
            raw_shortened_md_body = response.text.strip()

            cleaned_shortened_md_body = self._clean_llm_output(raw_shortened_md_body)

            # Relax the check slightly (e.g., allow 99% of original length)
            # Also check if it's empty
            if not cleaned_shortened_md_body:
                 feedback = getattr(response, 'prompt_feedback', 'Unknown feedback')
                 logger.warning(f"LLM did not return usable shortened Markdown body or failed to shorten significantly. Feedback: {feedback}")
                 # Log the raw response for debugging
                 logger.debug(f"Raw LLM response (shortening failed): {raw_shortened_md_body}")
                 return None

            logger.info("Successfully received and cleaned shortened resume Markdown body from LLM.")
            return cleaned_shortened_md_body
        except Exception as e:
            logger.error(f"Error calling Gemini API for Markdown resume body shortening: {str(e)}")
            return None

    # New method for MD -> HTML conversion
    def _convert_md_body_to_html_body(self, md_body_content: str) -> Union[str, None]:
        """Uses LLM to convert resume Markdown BODY content to HTML BODY content."""
        if not self.model:
            logger.error("LLM not configured. Cannot convert Markdown to HTML.")
            return None

        if not md_body_content:
             logger.warning("Markdown body content for HTML conversion is empty.")
             return ""

        prompt = f"""
        **Task:** Convert the following resume **BODY** content from Markdown format to clean, semantic **HTML body elements**. Ensure the HTML structure matches standard resume sections.

        **Instructions:**
        *   **Primary Goal:** Convert the Markdown structure to equivalent HTML.
        *   **HTML Formatting:**
            *   Use `<section>` tags for main resume sections (identified by `## Section Title` in Markdown).
            *   Inside sections, use `<h2>` for the section title (extracted from `##`).
            *   Use `<h3>` for job titles, degree names, or project titles (often from `###` in Markdown).
            *   Use `<p>` for descriptive paragraphs or date lines.
            *   Use `<ul>` and `<li>` for Markdown bullet points (`-` or `*`).
            *   Convert Markdown links `[text](url)` to HTML `<a>` tags `<a href="url">text</a>`.
            *   Keep the content otherwise identical to the input Markdown.
        *   **Output:** Return ONLY the converted **HTML body elements**. Do **NOT** include `<html>`, `<head>`, `<body>` tags, or ````html` code fences in your output. Only provide the inner HTML elements that would go inside the `<body>`.

        **Input Resume BODY (Markdown):**
        ```markdown
        {md_body_content}
        ```

        **Converted HTML Resume BODY Content:**
        """

        try:
            logger.info("Sending request to Gemini to convert Markdown body to HTML...")
            # Note: Consider using a different model or settings if pure conversion needs less 'creativity'
            response = self.model.generate_content(prompt)
            raw_html_body = response.text.strip()

            cleaned_html_body = self._clean_llm_output(raw_html_body)

            if not cleaned_html_body:
                 feedback = getattr(response, 'prompt_feedback', 'Unknown feedback')
                 logger.warning(f"LLM did not return usable HTML body from Markdown conversion. Feedback: {feedback}")
                 return None

            logger.info("Successfully received and cleaned converted HTML body from LLM.")
            return cleaned_html_body
        except Exception as e:
            logger.error(f"Error calling Gemini API for Markdown to HTML conversion: {str(e)}")
            return None

    # Updated to handle separated MD shortening and HTML conversion
    def generate_single_page_pdf(
        self,
        input_md_path: Union[str, Path],
        output_pdf_path: Union[str, Path],
        job_description: str,
        save_intermediate_files: bool = False # Renamed for clarity (includes HTML now)
    ) -> bool:
        """Converts MD to PDF via HTML/CSS, shortening MD content iteratively to ensure it's one page."""
        input_md_path = Path(input_md_path)
        output_pdf_path = Path(output_pdf_path)
        output_dir = output_pdf_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)

        if not input_md_path.exists():
             logger.error(f"Input Markdown file not found: {input_md_path}")
             return False

        try:
            original_md_content = input_md_path.read_text(encoding='utf-8')
        except Exception as e:
             logger.error(f"Failed to read input markdown file {input_md_path}: {str(e)}")
             return False

        # Extract Name/Contact/Body from the original Markdown
        name, contact, current_md_body_content = self._extract_header_info(original_md_content)

        # --- Check for empty Markdown body early ---
        if not current_md_body_content.strip():
            logger.error("Extracted Markdown body content is empty. Cannot proceed.")
            return False
        # -----------------------------------------

        final_pdf_generated = False
        final_pdf_is_one_page = False
        last_successful_pdf_path = None

        for i in range(self.max_iterations + 1):
            iteration_stem = output_pdf_path.stem # Base name for intermediate files
            iteration_pdf_path = output_pdf_path
            iteration_html_path = None # Initialize

            if save_intermediate_files:
                iteration_pdf_path = output_dir / f"{iteration_stem}_attempt_{i}.pdf"
                iteration_html_path = output_dir / f"{iteration_stem}_attempt_{i}.html"

            logger.info(f"PDF Generation Attempt {i+1}/{self.max_iterations+1} for {input_md_path.name}")

            # --- Convert current MD body to HTML --- 
            logger.info(f"Converting Markdown body to HTML (Attempt {i+1})...")
            current_html_body_content = self._convert_md_body_to_html_body(current_md_body_content)
            if current_html_body_content is None:
                logger.error(f"Failed to convert Markdown to HTML on attempt {i+1}. Stopping.")
                break

            # --- Save Intermediate HTML (if requested) --- 
            if save_intermediate_files and iteration_html_path:
                try:
                    with open(iteration_html_path, 'w', encoding='utf-8') as f_html:
                        # Construct the full HTML for saving/viewing
                        full_html_for_save = f"""
                        <!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
                        <title>{name if name else 'Resume'} (Attempt {i})</title>
                        <link rel="stylesheet" href="{self.css_path.name}">
                        </head><body><div class="header"><div class="name">{name}</div><div class="contact">{contact}</div></div>
                        <main>{current_html_body_content}</main></body></html>
                        """
                        f_html.write(full_html_for_save)
                    logger.info(f"Saved intermediate HTML to: {iteration_html_path}")
                except Exception as e:
                    logger.warning(f"Failed to save intermediate HTML {iteration_html_path}: {e}")
                    # Continue with PDF generation anyway

            # --- Delete potential output PDF from previous (failed) iteration --- 
            if not save_intermediate_files and iteration_pdf_path.exists():
                try: iteration_pdf_path.unlink()
                except OSError as e: logger.error(f"Failed to delete previous PDF {iteration_pdf_path}: {e}")
            elif save_intermediate_files and iteration_pdf_path.exists():
                 logger.warning(f"Intermediate PDF {iteration_pdf_path} already exists, will be overwritten.")

            # --- Generate PDF from current HTML body --- 
            success = self._generate_pdf_from_html(current_html_body_content, name, contact, iteration_pdf_path)
            if not success:
                logger.error(f"WeasyPrint failed on attempt {i+1}. Stopping conversion for this file.")
                break

            final_pdf_generated = True
            last_successful_pdf_path = iteration_pdf_path

            # --- Check Page Count --- 
            page_count = self._get_pdf_page_count(iteration_pdf_path)
            if page_count == 1:
                logger.info(f"Successfully generated single-page PDF: {iteration_pdf_path}")
                final_pdf_is_one_page = True
                # If saving intermediates, ensure the final name exists if needed
                if save_intermediate_files and iteration_pdf_path != output_pdf_path:
                    try:
                        shutil.copy2(iteration_pdf_path, output_pdf_path)
                        logger.info(f"Copied successful intermediate PDF to {output_pdf_path}")
                    except Exception as e: logger.error(f"Failed to copy successful intermediate PDF to {output_pdf_path}: {e}")
                break # SUCCESS

            if page_count is None:
                 logger.error("Failed to get page count. Cannot verify single-page requirement.")
                 break

            # --- Shorten MARKDOWN body if needed --- 
            if i < self.max_iterations:
                logger.warning(f"PDF {iteration_pdf_path.name} has {page_count} pages. Attempting LLM shortening of MARKDOWN body (Iteration {i+1}/{self.max_iterations}).")
                # Shorten the current Markdown body
                shortened_md_body = self._shorten_resume_with_llm(current_md_body_content, job_description)
                if shortened_md_body:
                    # Use the new shortened Markdown body for the *next* iteration's conversion
                    current_md_body_content = shortened_md_body 
                else:
                    logger.error("LLM failed to shorten the resume Markdown content. Stopping iteration.")
                    break
            else:
                 logger.error(f"Reached max iterations ({self.max_iterations}). Final PDF ({last_successful_pdf_path.name}) has {page_count} pages.")
                 final_pdf_is_one_page = False
                 break

        return final_pdf_generated and final_pdf_is_one_page

# --- Test Logic Updated --- 
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(module)s:%(funcName)s:%(lineno)d] - %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - [%(module)s:%(funcName)s:%(lineno)d] - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )

    logger.info("--- Running Standalone PDF Generator Test (HTML Workflow, Saving Intermediates) ---")

    test_input_dir = Path("edited_resumes_test")
    test_output_dir = Path("generated_pdfs_test")
    test_output_dir.mkdir(exist_ok=True)

    dummy_job_description = "This is a dummy job description for testing purposes. Focus on Python, SQL, and data visualization."

    if not test_input_dir.exists() or not any(test_input_dir.glob('*.md')):
        logger.error(f"Input directory '{test_input_dir}' does not exist or contains no .md files. Please run resume_editor.py test first.")
        sys.exit(1)

    generator = PdfGenerator() # Uses new defaults (css_path)

    if not generator.model:
         logger.warning("LLM could not be configured. Shortening loop will fail if needed.")

    success_count = 0
    fail_count = 0
    md_files = list(test_input_dir.glob('*.md'))

    for md_file in md_files:
        logger.info(f"\nProcessing test file: {md_file}")
        final_output_pdf_file = test_output_dir / md_file.with_suffix('.pdf').name

        result = generator.generate_single_page_pdf(
            md_file,
            final_output_pdf_file,
            dummy_job_description,
            save_intermediate_files=True
        )

        if result:
            logger.info(f"Successfully generated single-page PDF (final copy): {final_output_pdf_file}")
            success_count += 1
        else:
            logger.error(f"Failed to generate single-page PDF for: {md_file}. Check logs and intermediate files in {test_output_dir}")
            fail_count +=1

    logger.info(f"\n--- Test Summary ---")
    logger.info(f"Processed {len(md_files)} markdown files.")
    logger.info(f"Successfully generated single-page final PDFs: {success_count}")
    logger.info(f"Failed to generate single-page final PDFs: {fail_count}")
    logger.info(f"Test output (including intermediate PDFs) saved to: {test_output_dir}") 