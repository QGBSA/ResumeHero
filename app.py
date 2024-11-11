# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from utils.resume_processing import process_resume
from utils.openai_service import get_ats_score, fine_tune_resume, generate_cover_letter, analyze_job_posting
from config import Config
from werkzeug.utils import secure_filename
import markdown
import requests
from bs4 import BeautifulSoup
import tempfile
from docx import Document
import mistune
import os

app = Flask(__name__)
app.config.from_object(Config)

# Global variables for resume and job description text
resume_text_global = None
job_description_text_global = None

# Ensure the upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Allowed file extensions
ALLOWED_EXTENSIONS = {'pdf', 'txt'}

# Utility functions (unchanged)
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_job_description_from_url(url):
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            for script_or_style in soup(['script', 'style']):
                script_or_style.decompose()
            text = soup.get_text(separator=' ', strip=True)
            return text
        else:
            print(f"Failed to retrieve the page. Status code: {response.status_code}")
            return None
    except requests.exceptions.Timeout:
        print("Request timed out. Please try again later.")
        return None
    except Exception as e:
        print(f"Error fetching page content: {e}")
        return None

def save_resume_as_docx(text, file_path):
    doc = Document()
    for line in text.splitlines():
        doc.add_paragraph(line)
    doc.save(file_path)

# Main Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    global resume_text_global, job_description_text_global

    if request.method == 'POST':
        resume_file = request.files.get('resume')
        job_description_file = request.files.get('job_description')
        job_url = request.form.get('job_url')

        # Check and process resume file
        if resume_file and allowed_file(resume_file.filename):
            resume_filename = secure_filename(resume_file.filename)
            resume_path = os.path.join(app.config['UPLOAD_FOLDER'], resume_filename)
            resume_file.save(resume_path)
            resume_text_global = process_resume(resume_path)
        else:
            flash('Please upload a valid resume file (pdf or txt)', 'error')
            return redirect(url_for('upload_file'))

        # Check and process job description file or URL
        if job_description_file and allowed_file(job_description_file.filename):
            job_description_filename = secure_filename(job_description_file.filename)
            job_description_path = os.path.join(app.config['UPLOAD_FOLDER'], job_description_filename)
            job_description_file.save(job_description_path)
            job_description_text_global = process_resume(job_description_path)
        elif job_url:
            job_description_text_global = extract_job_description_from_url(job_url)
            if not job_description_text_global:
                flash('Could not extract job description from the provided URL. Please type a valid URL or upload a job description document instead.', 'error')
                return redirect(url_for('upload_file'))
        else:
            flash('Please upload a job description file or provide a job URL', 'error')
            return redirect(url_for('upload_file'))

        # Confirm successful upload of both files
        if resume_text_global and job_description_text_global:
            flash("Files uploaded successfully! You may now proceed with job analysis, resume evaluation, resume fine-tuning, or cover letter generation.", 'success')
        else:
            flash("An error occurred during upload. Please try again.", 'error')

    return render_template('upload.html')


@app.route('/ats_scores')
def ats_scores():
    if not (resume_text_global and job_description_text_global):
        flash("Please upload both a resume and a job description before requesting an ATS score.")
        return redirect(url_for('upload_file'))

    score, feedback = get_ats_score(resume_text_global, job_description_text_global)

    feedback_html = mistune.create_markdown()(feedback)
    return render_template('ats_score.html', score=score, feedback=feedback_html)


@app.route('/fine_tune', methods=['GET', 'POST'])
def fine_tune():
    if not (resume_text_global and job_description_text_global):
        print("Files not uploaded")  # Debugging statement
        flash("Please upload both a resume and a job description before requesting resume fine-tuning.")
        return redirect(url_for('upload_file'))

    optimized_resume = fine_tune_resume(resume_text_global, job_description_text_global)

    report = "Fine-tuning complete. Resume is now ATS-friendly."

    optimized_resume_html = mistune.create_markdown()(optimized_resume)

    # Save the optimized resume to a temporary .docx file
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.docx')
    save_resume_as_docx(optimized_resume, temp_file.name)

    return render_template(
        'optimization_report.html', 
        optimized_resume=optimized_resume_html, 
        report=report,
        download_path=temp_file.name
    )

@app.route('/generate_cover_letter', methods=['GET', 'POST'])
def generate_cover_letter_route():
    if not (resume_text_global and job_description_text_global):
        flash("Please upload both a resume and a job description before generating a cover letter.")
        return redirect(url_for('upload_file'))

    cover_letter_markdown = generate_cover_letter(resume_text_global, job_description_text_global)

    cover_letter_html = mistune.create_markdown()(cover_letter_markdown)

    # Save the cover letter to a temporary .docx file
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.docx')
    save_resume_as_docx(cover_letter_markdown, temp_file.name)

    return render_template(
        'cover_letter.html', 
        cover_letter=cover_letter_html, 
        download_path=temp_file.name
    )

@app.route('/download_report')
def download_report():
    download_path = request.args.get('path')
    return send_file(download_path, as_attachment=True, download_name="optimized_resume.docx")


@app.route('/download_cover_letter')
def download_cover_letter():
    download_path = request.args.get('path')
    return send_file(download_path, as_attachment=True, download_name="cover_letter.docx")


@app.route('/analyze_job_posting', methods=['GET', 'POST'])
def analyze_job_posting_route():
    if not job_description_text_global:
        flash("Please upload a job description before analyzing it.")
        return redirect(url_for('upload_file'))

    analysis = analyze_job_posting(job_description_text_global)


    analysis_html = mistune.create_markdown()(analysis)
    #analysis_html = markdown.markdown(analysis)
    return render_template('job_analysis.html', analysis=analysis_html)

@app.route('/about')
def about():
    return render_template('about.html')

if __name__ == '__main__':
    app.run(debug=True)
