import os
import pymysql
from flask import Flask, request, jsonify, render_template, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
import uuid

app = Flask(__name__)

# Konfigurasi Folder Penyimpanan File Permanen (Cloud Storage / Server Storage)
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # Batas maksimal file 50MB

# Konfigurasi Koneksi MySQL (Membaca Environment Variables Railway atau Default Lokal)
DB_HOST = os.environ.get('MYSQLHOST', 'localhost')
DB_USER = os.environ.get('MYSQLUSER', 'root')
DB_PASSWORD = os.environ.get('MYSQLPASSWORD', '')
DB_NAME = os.environ.get('MYSQLDATABASE', 'sentes_db')
DB_PORT = int(os.environ.get('MYSQLPORT', 3306))

def get_db_connection():
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        port=DB_PORT,
        cursorclass=pymysql.cursors.DictCursor
    )

# Inisialisasi Database & Pembuatan Tabel Otomatis
def init_db():
    try:
        # Jika database belum ada di server lokal, buat dulu database-nya
        temp_conn = pymysql.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, port=DB_PORT)
        temp_cursor = temp_conn.cursor()
        temp_cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
        temp_cursor.close()
        temp_conn.close()

        # Koneksi ke database utama untuk membuat tabel
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Tabel Pengguna (Keamanan Password Terenkripsi)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL
            )
        ''')
        
        # Tabel Postingan / File Galeri
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                id INT AUTO_INCREMENT PRIMARY KEY,
                filename VARCHAR(255) NOT NULL,
                original_name VARCHAR(255) NOT NULL,
                file_type VARCHAR(50) NOT NULL,
                uploader VARCHAR(255) NOT NULL,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        cursor.close()
        conn.close()
        print("Database dan Tabel berhasil dibuat secara otomatis!")
    except Exception as e:
        print(f"Gagal menginisialisasi database: {e}")

init_db()

@app.route('/')
def index():
    return render_template('index.html')

# API Pendaftaran Pengguna (Signup)
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    name = data.get('name')
    email = data.get('email').lower()
    password = data.get('password')

    if not name or not email or not password:
        return jsonify({'success': False, 'message': 'Semua kolom wajib diisi!'}), 400

    hashed_password = generate_password_hash(password)
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO users (name, email, password) VALUES (%s, %s, %s)', (name, email, hashed_password))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'success': True, 'message': 'Pendaftaran berhasil!', 'user': {'name': name, 'email': email}})
    except pymysql.err.IntegrityError:
        return jsonify({'success': False, 'message': 'Email sudah terdaftar!'}), 400

# API Masuk Pengguna (Login)
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email').lower()
    password = data.get('password')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, email, password FROM users WHERE email = %s', (email,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if user and check_password_hash(user['password'], password):
        return jsonify({'success': True, 'user': {'id': user['id'], 'name': user['name'], 'email': user['email']}})
    return jsonify({'success': False, 'message': 'Email atau kata sandi salah!'}), 401

# API Unggah File (Permanen Storage + Database MySQL)
@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Tidak ada file yang diunggah'}), 400
    
    file = request.files['file']
    uploader = request.form.get('uploader', '@AnggotaSentes')
    
    if file.filename == '':
        return jsonify({'success': False, 'message': 'Nama file kosong'}), 400

    if file:
        ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        filename = f"{uuid.uuid4().hex}.{ext}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Simpan file secara fisik ke server/cloud storage lokal
        file.save(filepath)

        file_type = 'video' if ext in ['mp4', 'mov', 'avi', 'mkv', 'webm'] else 'image'

        # Catat ke Database MySQL
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO posts (filename, original_name, file_type, uploader) VALUES (%s, %s, %s, %s)',
                       (filename, file.filename, file_type, uploader))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'success': True, 'message': 'File berhasil disimpan secara permanen di database MySQL & server!'})

# API Mengambil Daftar Postingan / Galeri dari Database MySQL
@app.route('/api/posts', methods=['GET'])
def get_posts():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT filename, original_name, file_type, uploader, date FROM posts ORDER BY id DESC')
    posts = cursor.fetchall()
    cursor.close()
    conn.close()

    posts_list = []
    for p in posts:
        posts_list.append({
            'filename': p['filename'],
            'original_name': p['original_name'],
            'file_type': p['file_type'],
            'uploader': p['uploader'],
            'date': str(p['date']),
            'url': f'/uploads/{p["filename"]}'
        })
    return jsonify(posts_list)

# Route untuk Mengakses File yang Disimpan di Server
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    # Railway akan memberikan port secara otomatis, jika tidak ada gunakan 5000
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)