from flask import Flask, request, jsonify, send_file
import boto3
import os
import csv
import io
from werkzeug.utils import secure_filename
from botocore.exceptions import NoCredentialsError

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = '/tmp'
S3_BUCKET = 'pop-paperless-poc'
DYNAMODB_TABLE = 'pop-paperless-poc'
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

s3_client = boto3.client('s3')
textract_client = boto3.client('textract')
dynamodb = boto3.resource('dynamodb')

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file part'})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No selected file'})
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        # Upload file to S3
        s3_client.upload_file(file_path, S3_BUCKET, filename)

        # Extract text using Textract
        response = textract_client.detect_document_text(Document={'S3Object': {'Bucket': S3_BUCKET, 'Name': filename}})
        
        # Save extracted text to DynamoDB
        text_data = ''
        for item in response['Blocks']:
            if item['BlockType'] == 'LINE':
                text_data += item['Text'] + '\n'
        
        table = dynamodb.Table(DYNAMODB_TABLE)
        table.put_item(Item={'DocumentName': filename, 'ExtractedText': text_data})

        os.remove(file_path)
        return jsonify({'success': True, 'downloadUrl': f'/download/{filename}'})
    else:
        return jsonify({'success': False, 'error': 'Unsupported file type'})

@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    table = dynamodb.Table(DYNAMODB_TABLE)
    response = table.get_item(Key={'DocumentName': filename})

    if 'Item' in response:
        text_data = response['Item']['ExtractedText']

        # Provide file as TXT or CSV
        output = io.StringIO()
        output.write(text_data)
        output.seek(0)
        
        return send_file(output, mimetype='text/plain', as_attachment=True, download_name=f'{filename}.txt')

    return jsonify({'success': False, 'error': 'File not found'})

if __name__ == '__main__':
    app.run(debug=True)
