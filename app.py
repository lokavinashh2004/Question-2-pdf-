import os
import json
import uuid
from flask import Flask, request, render_template, send_from_directory, jsonify
import pandas as pd
from PyPDF2 import PdfReader
from datetime import datetime
import google.generativeai as genai

GOOGLE_API_KEY = 'AIzaSyDeo_FSywoTQhoazTFyd-CUslFBuhg8lmM'
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-1.5-pro')

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'outputs'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def extract_text_from_pdf(pdf_path):
    text = ""
    with open(pdf_path, 'rb') as file:
        reader = PdfReader(file)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text

def extract_medical_data(pdf_text):
    prompt = f"""
    Extract all medical investigation data from the text below.

    Return the output as a JSON object where:
    - keys are investigation/test names (e.g., "WBC Count", "Hemoglobin")
    - values are their corresponding numeric values (include unit if available)
    - also include a key "report_date" with the report date in DD.MM.YY format if found
    - also give any medical terms that is determined with no values

    Medical Report Text:
    {pdf_text}
    """

    response = model.generate_content(prompt)

    try:
        json_str = response.text.strip().replace('```json', '').replace('```', '').strip()
        extracted_data = json.loads(json_str)
        return extracted_data
    except Exception as e:
        print(f"Error processing Gemini response: {e}")
        return None

def create_excel_from_extracted_data(all_data, output_path):
    investigations = sorted(set(k for data in all_data for k in data['data'].keys()))
    dates = [data['report_date'] or f"Date {i+1}" for i, data in enumerate(all_data)]

    df = pd.DataFrame({
        'Investigations': investigations
    })

    for i, record in enumerate(all_data):
        col = dates[i]
        values = []
        for test in investigations:
            values.append(record['data'].get(test, ''))
        df[col] = values

    df.to_excel(output_path, index=False)
    return output_path

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    files = request.files.getlist('pdfs')
    if not files:
        return 'No PDF files uploaded.', 400

    extracted_records = []
    json_outputs = {}

    for file in files:
        unique_filename = str(uuid.uuid4()) + ".pdf"
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(pdf_path)

        pdf_text = extract_text_from_pdf(pdf_path)
        extracted_data = extract_medical_data(pdf_text)

        if extracted_data:
            report_date = extracted_data.pop("report_date", None)
            extracted_records.append({
                "report_date": report_date,
                "data": extracted_data
            })
            json_outputs[file.filename] = {
                "report_date": report_date,
                "data": extracted_data
            }

    output_excel = os.path.join(app.config['OUTPUT_FOLDER'], 'medical_data.xlsx')
    create_excel_from_extracted_data(extracted_records, output_excel)

    return render_template('result.html', 
                           download_link='/download/medical_data.xlsx', 
                           json_data=json.dumps(json_outputs, indent=2))

@app.route('/download/<filename>')
def download(filename):
    return send_from_directory(app.config['OUTPUT_FOLDER'], filename, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
