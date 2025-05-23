
from flask import Flask, render_template, request, send_file, redirect, url_for, jsonify
from werkzeug.utils import secure_filename
import os
from mutagen import File as MutagenFile
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TRCK, APIC
from mutagen.mp4 import MP4
from mutagen.mp4 import MP4Cover
from io import BytesIO
from pydub import AudioSegment
import ffmpeg

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'mp3', 'm4a'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        # Read metadata
        ext = filename.rsplit('.', 1)[1].lower()
        if ext == 'mp3':
            audio = MP3(filepath, ID3=ID3)
            tags = {
                'title': audio.tags.get('TIT2', ''),
                'artist': audio.tags.get('TPE1', ''),
                'track': audio.tags.get('TRCK', ''),
            }
            cover = None
            if 'APIC:' in audio.tags:
                cover = audio.tags['APIC:'].data
        elif ext == 'm4a':
            audio = MP4(filepath)
            tags = {
                'title': audio.tags.get('\xa9nam', [''])[0],
                'artist': audio.tags.get('\xa9ART', [''])[0],
                'track': audio.tags.get('trkn', [(0, 0)])[0][0],
            }
            cover = None
            if 'covr' in audio.tags:
                cover = audio.tags['covr'][0]
        else:
            return jsonify({'error': 'Unsupported file type'}), 400
        # Return metadata and cover art (as base64)
        import base64
        cover_b64 = base64.b64encode(cover).decode('utf-8') if cover else None
        return jsonify({'filename': filename, 'tags': tags, 'cover': cover_b64})
    return jsonify({'error': 'Invalid file'}), 400


@app.route('/edit', methods=['POST'])
def edit():
    data = request.form
    file = request.files.get('file')
    cover = request.files.get('cover')
    filename = data.get('filename')
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    ext = filename.rsplit('.', 1)[1].lower()
    # Always export as mp3
    export_filename = os.path.splitext(filename)[0] + '.mp3'
    export_path = os.path.join(app.config['UPLOAD_FOLDER'], export_filename)

    # Convert to mp3 if needed
    if ext == 'mp3':
        audio = MP3(filepath, ID3=ID3)
        if audio.tags is None:
            audio.add_tags()
        audio.tags['TIT2'] = TIT2(encoding=3, text=data.get('title', ''))
        audio.tags['TPE1'] = TPE1(encoding=3, text=data.get('artist', ''))
        audio.tags['TRCK'] = TRCK(encoding=3, text=data.get('track', ''))
        if cover:
            audio.tags['APIC'] = APIC(
                encoding=3,
                mime=cover.mimetype,
                type=3,
                desc='Cover',
                data=cover.read()
            )
        audio.save()
        # Copy to export_path if not already
        if filepath != export_path:
            with open(filepath, 'rb') as src, open(export_path, 'wb') as dst:
                dst.write(src.read())
    elif ext == 'm4a':
        # Convert m4a to mp3 using pydub
        audio_seg = AudioSegment.from_file(filepath, format='m4a')
        audio_seg.export(export_path, format='mp3')
        # Now add tags to the new mp3
        audio = MP3(export_path, ID3=ID3)
        if audio.tags is None:
            audio.add_tags()
        audio.tags['TIT2'] = TIT2(encoding=3, text=data.get('title', ''))
        audio.tags['TPE1'] = TPE1(encoding=3, text=data.get('artist', ''))
        audio.tags['TRCK'] = TRCK(encoding=3, text=data.get('track', ''))
        if cover:
            audio.tags['APIC'] = APIC(
                encoding=3,
                mime=cover.mimetype,
                type=3,
                desc='Cover',
                data=cover.read()
            )
        audio.save()
    else:
        return jsonify({'error': 'Unsupported file type'}), 400
    # Prepare file for download
    with open(export_path, 'rb') as f:
        file_data = f.read()
    return send_file(BytesIO(file_data), as_attachment=True, download_name=export_filename, mimetype='audio/mpeg')

if __name__ == '__main__':
    app.run(debug=True)
