import os
import qrcode
from io import BytesIO
import socket
from flask import Flask, render_template, redirect, url_for, request, flash, send_from_directory, send_file, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.utils import secure_filename
from models import db, User, Post, Comment, Like, Event, get_sl_time
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'SuperSecretKeyForYayamulla'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'uploads')
    # app.config['MAX_CONTENT_LENGTH'] removed to allow unlimited upload size

# Create uploads folder if not exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db.init_app(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'
socketio = SocketIO(app, cors_allowed_origins="*")

IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
VIDEO_EXTENSIONS = {'mp4', 'webm', 'ogg', 'mov', 'avi'}
DOC_EXTENSIONS = {'pdf', 'doc', 'docx', 'txt', 'xlsx', 'xls', 'ppt', 'pptx', 'zip'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in IMAGE_EXTENSIONS.union(VIDEO_EXTENSIONS).union(DOC_EXTENSIONS)

def get_file_type(filename):
    ext = filename.rsplit('.', 1)[1].lower()
    if ext in IMAGE_EXTENSIONS: return 'image'
    if ext in VIDEO_EXTENSIONS: return 'video'
    if ext in DOC_EXTENSIONS: return 'document'
    return 'unknown'

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route("/")
@login_required
def index():
    posts = Post.query.order_by(Post.timestamp.desc()).all()
    return render_template('index.html', posts=posts)

@app.route("/events")
@login_required
def events():
    events_list = Event.query.order_by(Event.event_date.asc(), Event.event_time.asc()).all()
    return render_template('events.html', events=events_list)

@app.route("/create_event", methods=['POST'])
@login_required
def create_event():
    title = request.form.get('title')
    description = request.form.get('description')
    event_date_str = request.form.get('event_date')
    event_time_str = request.form.get('event_time')
    
    poster_file = request.files.get('poster')
    doc_file = request.files.get('document')
    
    poster_filename = None
    doc_filename = None
    
    if poster_file and allowed_file(poster_file.filename):
        poster_filename = secure_filename("poster_" + str(get_sl_time().timestamp()) + "_" + poster_file.filename)
        poster_file.save(os.path.join(app.config['UPLOAD_FOLDER'], poster_filename))
        
    if doc_file and allowed_file(doc_file.filename):
        doc_filename = secure_filename("doc_" + str(get_sl_time().timestamp()) + "_" + doc_file.filename)
        doc_file.save(os.path.join(app.config['UPLOAD_FOLDER'], doc_filename))
        
    if title and event_date_str and event_time_str:
        # Parse date and time
        from datetime import datetime as dt_parser
        event_date = dt_parser.strptime(event_date_str, '%Y-%m-%d').date()
        event_time = dt_parser.strptime(event_time_str, '%H:%M').time()
        
        event = Event(title=title, description=description, event_date=event_date, event_time=event_time,
                      poster_filename=poster_filename, document_filename=doc_filename, user_id=current_user.id)
        db.session.add(event)
        db.session.commit()
        flash("Event scheduled successfully!", "success")
    else:
        flash("Title, date, and time are required.", "danger")
        
    return redirect(url_for('events'))

@app.route("/delete_event/<int:event_id>", methods=['POST'])
@login_required
def delete_event(event_id):
    event = Event.query.get_or_404(event_id)
    if event.user_id != current_user.id and not current_user.is_admin:
        return jsonify({"success": False, "msg": "Unauthorized"})
    
    if event.poster_filename:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], event.poster_filename)
        if os.path.exists(file_path): os.remove(file_path)
        
    if event.document_filename:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], event.document_filename)
        if os.path.exists(file_path): os.remove(file_path)
            
    db.session.delete(event)
    db.session.commit()
    flash("Event deleted.", "success")
    return redirect(url_for('events'))

@app.route("/admin_dashboard")
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash("You do not have permission to access this page.", "danger")
        return redirect(url_for('index'))
    users = User.query.all()
    posts = Post.query.order_by(Post.timestamp.desc()).all()
    lan_ip_url = f"http://{get_local_ip()}:5000/"
    return render_template('admin.html', users=users, posts=posts, lan_ip_url=lan_ip_url)

@app.route("/delete_user/<int:user_id>", methods=['POST'])
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        return jsonify({"success": False, "msg": "Unauthorized"})
    user = User.query.get_or_404(user_id)
    if user.is_admin:
        return jsonify({"success": False, "msg": "Cannot delete another admin"})
    db.session.delete(user)
    db.session.commit()
    flash("User deleted.", "success")
    return redirect(url_for('admin_dashboard'))

@app.route("/delete_post/<int:post_id>", methods=['POST'])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author != current_user and not current_user.is_admin:
        return jsonify({"success": False, "msg": "Unauthorized"})
    
    if post.media_filename:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], post.media_filename)
        if os.path.exists(file_path):
            os.remove(file_path)
    
    db.session.delete(post)
    db.session.commit()
    flash("Post deleted.", "success")
    return redirect(request.referrer or url_for('index'))

@app.route("/register", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Super simple check for existing
        if User.query.filter_by(username=username).first():
            flash('Username already taken.', 'danger')
            return redirect(url_for('register'))
        if User.query.filter_by(email=email).first():
            flash('Email already used.', 'danger')
            return redirect(url_for('register'))
        
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        user = User(username=username, email=email, password_hash=hashed_password)
        db.session.add(user)
        db.session.commit()
        flash('Your account has been created! You are now able to log in', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        login_input = request.form.get('login_input') # can be email or username
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False
        
        user = User.query.filter((User.email == login_input) | (User.username == login_input)).first()
        if user and bcrypt.check_password_hash(user.password_hash, password):
            login_user(user, remember=remember)
            return redirect(url_for('index'))
        else:
            flash('Login Unsuccessful. Please check username/email and password', 'danger')
    return render_template('login.html')

@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route("/create_post", methods=['POST'])
@login_required
def create_post():
    content = request.form.get('content')
    file = request.files.get('file')
    filename = None
    file_type = None

    if file and allowed_file(file.filename):
        filename = secure_filename(str(get_sl_time().timestamp()) + "_" + file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        file_type = get_file_type(filename)

    if content or filename:
        post = Post(content=content, media_filename=filename, media_type=file_type, author=current_user)
        db.session.add(post)
        db.session.commit()
        flash("Post created!", "success")
    return redirect(url_for('index'))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/react/<int:post_id>', methods=['POST'])
@login_required
def toggle_reaction(post_id):
    post = Post.query.get_or_404(post_id)
    data = request.get_json() or {}
    reaction_type = data.get('reaction_type', 'like') # 'like', 'heart', 'sad'
    
    # Check if user already reacted
    existing_reaction = Like.query.filter_by(user_id=current_user.id, post_id=post_id).first()
    
    if existing_reaction:
        if existing_reaction.reaction_type == reaction_type:
            # Toggle off if clicking the same reaction
            db.session.delete(existing_reaction)
            db.session.commit()
            action = 'removed'
        else:
            # Change reaction type
            existing_reaction.reaction_type = reaction_type
            db.session.commit()
            action = 'changed'
    else:
        new_reaction = Like(user_id=current_user.id, post_id=post_id, reaction_type=reaction_type)
        db.session.add(new_reaction)
        db.session.commit()
        action = 'added'
    
    # Calculate counts
    likes_count = len([r for r in post.likes if r.reaction_type == 'like'])
    hearts_count = len([r for r in post.likes if r.reaction_type == 'heart'])
    sads_count = len([r for r in post.likes if r.reaction_type == 'sad'])
    total_reactions = len(post.likes)

    return jsonify({
        "success": True, 
        "action": action, 
        "reaction_type": reaction_type,
        "likes_count": likes_count,
        "hearts_count": hearts_count,
        "sads_count": sads_count,
        "total": total_reactions
    })

@app.route("/qrcode")
def generate_qrcode():
    host_url = f"http://{get_local_ip()}:5000/"
    img = qrcode.make(host_url)
    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

# SocketIO for real-time comments
@socketio.on('new_comment')
def handle_new_comment(data):
    post_id = data.get('post_id')
    content = data.get('content')
    user_id = current_user.id
    
    if content and post_id:
        comment = Comment(content=content, user_id=user_id, post_id=post_id)
        db.session.add(comment)
        db.session.commit()
        
        # Broadcast the new comment to all connected clients
        emit('receive_comment', {
            'post_id': post_id,
            'content': content,
            'username': current_user.username,
            'timestamp': comment.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        }, broadcast=True)

if __name__ == '__main__':
    with app.app_context():
        # Create database
        db.create_all()
        # Create an initial admin if not exists
        if not User.query.filter_by(username='admin').first():
            hashed_pw = bcrypt.generate_password_hash('admin123').decode('utf-8')
            admin = User(username='admin', email='admin@yayamulla.com', password_hash=hashed_pw, is_admin=True)
            db.session.add(admin)
            db.session.commit()
    socketio.run(app, debug=True, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
