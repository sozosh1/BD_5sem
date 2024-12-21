from flask import Flask, render_template, request, redirect, url_for, flash, send_file, abort
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import configparser
from models import db, User, Client, BookType, Book, Journal
import re
from datetime import datetime, timedelta
from sqlalchemy import func, desc, text
from io import StringIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from io import BytesIO
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'

# Чтение конфигурации
config = configparser.ConfigParser()
config.read('config/database.ini')

app.config['SQLALCHEMY_DATABASE_URI'] = f"postgresql://{config['postgresql']['user']}:{config['postgresql']['password']}@{config['postgresql']['host']}/{config['postgresql']['database']}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Инициализация расширен
db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            flash('У вас нет прав для изменения данных', 'danger')
            return redirect(url_for('catalog'))
        return f(*args, **kwargs)
    return decorated_function

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Маршруты для клиентов
@app.route('/references/clients')
@login_required
@admin_required
def clients_list():
    page = request.args.get('page', 1, type=int)
    sort_by = request.args.get('sort_by', 'id')
    search = request.args.get('search', '')
    
    query = Client.query
    query = apply_search(query, search, Client, ['last_name', 'first_name', 'father_name', 'passport_seria', 'passport_number'])
    query = apply_sorting(query, sort_by, Client)
    pagination = get_pagination(query, page)
    
    return render_template('references/clients.html', 
                         pagination=pagination,
                         sort_by=sort_by,
                         search=search)

@app.route('/references/clients/add', methods=['GET', 'POST'])
@login_required
@admin_required
def client_add():
    if request.method == 'POST':
        last_name = request.form['last_name']
        first_name = request.form['first_name']
        father_name = request.form['father_name']
        passport_seria = request.form['passport_seria']
        passport_number = request.form['passport_number']
        
        # Паттерн для проверки кириллицы
        cyrillic_pattern = re.compile(r'^[А-Яа-яЁё\s-]+$')
        
        # Валидация ФИО
        if not cyrillic_pattern.match(last_name):
            flash('Фамилия должна содержать только кириллицу')
            return render_template('references/client_form.html')
            
        if not cyrillic_pattern.match(first_name):
            flash('Имя должно содержать только кириллицу')
            return render_template('references/client_form.html')
            
        if father_name and not cyrillic_pattern.match(father_name):
            flash('Отчество должно содержать только кириллицу')
            return render_template('references/client_form.html')
        
        # Валидация паспортных данных
        if len(passport_seria) != 4 or not passport_seria.isdigit():
            flash('Серия паспорта должна состоять из 4 цифр')
            return render_template('references/client_form.html')
            
        if len(passport_number) != 6 or not passport_number.isdigit():
            flash('Номер паспорта должен состоять из 6 цифр')
            return render_template('references/client_form.html')
            
        client = Client(
            last_name=last_name,
            first_name=first_name,
            father_name=father_name,
            passport_seria=passport_seria,
            passport_number=passport_number
        )
        db.session.add(client)
        db.session.commit()
        flash('Клиент успешно добавлен')
        return redirect(url_for('clients_list'))
    return render_template('references/client_form.html')

@app.route('/')
@login_required
def index():
    return redirect(url_for('reports'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Неверное имя пользователя или пароль')
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

def create_default_users():
    if User.query.count() == 0:
        admin = User(
            username='admin',
            password_hash=generate_password_hash('admin123'),
            is_admin=True
        )
        
        user = User(
            username='user',
            password_hash=generate_password_hash('user123'),
            is_admin=False
        )
        
        db.session.add(admin)
        db.session.add(user)
        db.session.commit()

@app.route('/references/clients/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def client_edit(id):
    client = Client.query.get_or_404(id)
    if request.method == 'POST':
        client.last_name = request.form['last_name']
        client.first_name = request.form['first_name']
        client.father_name = request.form['father_name']
        client.passport_seria = request.form['passport_seria']
        client.passport_number = request.form['passport_number']
        db.session.commit()
        flash('Клиент успешно обновлен')
        return redirect(url_for('clients_list'))
    return render_template('references/client_form.html', client=client)

@app.route('/references/clients/<int:id>/delete')
@login_required
def client_delete(id):
    client = Client.query.get_or_404(id)
    db.session.delete(client)
    db.session.commit()
    flash('Клиент успешно дален')
    return redirect(url_for('clients_list'))

@app.route('/books')
@login_required
def books_list():
    search = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    sort_by = request.args.get('sort_by', 'id')
    
    query = Book.query.join(BookType)
    
    if search:
        query = query.filter(Book.name.ilike(f'%{search}%'))
    
    query = apply_sorting(query, sort_by, Book)
    pagination = get_pagination(query, page)
    
    return render_template('books/list.html',
                         books=pagination.items,
                         pagination=pagination,
                         search=search,
                         sort_by=sort_by,
                         read_only=False)

@app.route('/book_types')
@login_required
@admin_required
def book_types_list():
    search = request.args.get('search', '')
    sort_by = request.args.get('sort_by', 'id')
    page = request.args.get('page', 1, type=int)
    
    query = BookType.query
    
    if search:
        query = query.filter(BookType.type.ilike(f'%{search}%'))
        
    if sort_by == 'id':
        query = query.order_by(BookType.id)
    elif sort_by == 'type':
        query = query.order_by(BookType.type)
    elif sort_by == 'fine':
        query = query.order_by(BookType.fine)
    elif sort_by == 'day_count':
        query = query.order_by(BookType.day_count)
        
    pagination = query.paginate(page=page, per_page=10)
    
    return render_template('references/book_types.html',
                         book_types=pagination.items,
                         pagination=pagination,
                         search=search,
                         sort_by=sort_by,
                         read_only=not current_user.is_admin())

@app.route('/books/add', methods=['GET', 'POST'])
@login_required
@admin_required
def books_add():
    if request.method == 'POST':
        name = request.form['name']
        
        # Проверям существование книги с таким названием
        existing_book = Book.query.filter(Book.name.ilike(name)).first()
        if existing_book:
            flash('Книга с таким названием уже существует', 'error')
            book_types = BookType.query.all()
            return render_template('references/book_form.html', book_types=book_types)
            
        book = Book(
            name=name,
            cnt=request.form['cnt'],
            type_id=request.form['type_id']
        )
        db.session.add(book)
        db.session.commit()
        flash('Книга успешно добавлена')
        return redirect(url_for('books_list'))
        
    book_types = BookType.query.all()
    return render_template('references/book_form.html', book_types=book_types)

@app.route('/books/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def books_edit(id):
    book = Book.query.get_or_404(id)
    if request.method == 'POST':
        book.name = request.form['name']
        book.cnt = request.form['cnt']
        book.type_id = request.form['type_id']
        db.session.commit()
        flash('Книга успешно обновлена')
        return redirect(url_for('books_list'))
    book_types = BookType.query.all()
    return render_template('references/book_form.html', book=book, book_types=book_types)

@app.route('/references/books/<int:id>/delete')
@login_required
def book_delete(id):
    book = Book.query.get_or_404(id)
    db.session.delete(book)
    db.session.commit()
    flash('Книга успешно удалена')
    return redirect(url_for('books_list'))

@app.route('/journal')
@login_required
@admin_required
def journal_list():
    page = request.args.get('page', 1, type=int)
    sort_by = request.args.get('sort_by', 'id')
    search = request.args.get('search', '')
    
    query = Journal.query
    if search:
        query = query.join(Client).join(Book).filter(
            db.or_(
                Client.last_name.ilike(f'%{search}%'),
                Client.first_name.ilike(f'%{search}%'),
                Book.name.ilike(f'%{search}%')
            )
        )
    
    if sort_by and hasattr(Journal, sort_by):
        query = query.order_by(getattr(Journal, sort_by))
    
    pagination = get_pagination(query, page)
    
    return render_template('journals/journal.html',
                         pagination=pagination,
                         sort_by=sort_by,
                         search=search)

@app.route('/journal/add', methods=['GET', 'POST'])
@login_required
def journal_add():
    if request.method == 'POST':
        client_id = request.form['client_id']
        book_id = request.form['book_id']
        
        # Проверяем количество книг у клиента
        client_books = Journal.query.filter_by(
            client_id=client_id, 
            date_ret=None
        ).count()
        
        if client_books >= 10:
            flash('Клиент не может взять больше 10 книг', 'error')
            return redirect(url_for('journal_add'))
        
        # Проверяем доступность книги
        book = Book.query.get_or_404(book_id)
        
        # Проверяем реальное количество доступных экземпляров
        issued_books = Journal.query.filter_by(
            book_id=book_id,
            date_ret=None
        ).count()
        
        if issued_books >= book.cnt:
            flash('Книга недоступна для выдачи (все экземпляры на руках)', 'error')
            return redirect(url_for('journal_add'))
        
        try:
            date_beg = datetime.strptime(request.form['date_beg'], '%Y-%m-%d')
            date_end = date_beg + timedelta(days=book.book_type.day_count)
            
            journal = Journal(
                client_id=client_id,
                book_id=book_id,
                date_beg=date_beg,
                date_end=date_end
            )
            
            db.session.add(journal)
            db.session.commit()
            
            flash('Книга успешно выдана')
            return redirect(url_for('journal_list'))
            
        except Exception as e:
            db.session.rollback()
            flash('Произошла ошибка при выдаче книги', 'error')
            return redirect(url_for('journal_add'))
    
    # Получаем список доступных книг с реальным количеством
    available_books = Book.query.all()
    for book in available_books:
        issued = Journal.query.filter_by(
            book_id=book.id,
            date_ret=None
        ).count()
        book.available = book.cnt - issued
    
    available_books = [book for book in available_books if book.available > 0]
    
    clients = Client.query.order_by(Client.last_name).all()
    today = datetime.now().strftime('%Y-%m-%d')
    
    return render_template('journals/journal_form.html',
                         clients=clients,
                         available_books=available_books,
                         today=today)

@app.route('/journal/<int:id>/return')
@login_required
def journal_return(id):
    journal = Journal.query.get_or_404(id)
    if not journal.date_ret:
        try:
            journal.date_ret = datetime.now()
            db.session.commit()
            flash('Книга успешно возвращена')
        except Exception as e:
            db.session.rollback()
            flash('Ошибка при возврате книги', 'error')
    return redirect(url_for('journal_list'))

@app.route('/journal/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def journal_delete(id):
    journal = Journal.query.get_or_404(id)
    db.session.delete(journal)
    db.session.commit()
    flash('Запись успешно удалена')
    return redirect(url_for('journal_list'))

def get_pagination(query, page, per_page=10):
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return pagination

def apply_sorting(query, sort_by, model):
    if sort_by and hasattr(model, sort_by):
        return query.order_by(getattr(model, sort_by))
    return query

def apply_search(query, search_text, model, search_fields):
    if search_text:
        search_filters = []
        for field in search_fields:
            if hasattr(model, field):
                search_filters.append(getattr(model, field).ilike(f'%{search_text}%'))
        if search_filters:
            query = query.filter(db.or_(*search_filters))
    return query

@app.route('/reports')
@login_required
@admin_required
def reports():
    clients = Client.query.order_by(Client.last_name).all()
    return render_template('reports/index.html', clients=clients)

@app.route('/reports/library_stats')
@login_required
def library_stats():
    # Размер самого большого штрафа - используем структуру из документации
    max_fine = db.session.query(
        func.max((Journal.date_ret - Journal.date_end) * BookType.fine)
    ).select_from(Journal).join(
        Book, 
        Journal.book_id == Book.id
    ).join(
        BookType,
        Book.type_id == BookType.id
    ).filter(
        Journal.date_ret > Journal.date_end
    ).scalar() or 0
    
    # Три самые популярные кнг
    popular_books = db.session.query(
        Book.name,
        func.count(Book.name).label('count')
    ).join(
        Journal,
        Book.id == Journal.book_id
    ).group_by(
        Book.name
    ).order_by(
        func.count(Book.name).desc()
    ).limit(3).all()
    
    # Формируем отчет
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Статистика библиотеки'])
    writer.writerow(['Максимальный штраф:', float(max_fine)])
    writer.writerow([])
    writer.writerow(['Самые опопулярны книги:'])
    for book, count in popular_books:
        writer.writerow([book, count])
    
    return output.getvalue(), 200, {
        'Content-Type': 'text/csv; charset=utf-8',
        'Content-Disposition': 'attachment; filename=library_stats.csv'
    }

def create_pdf_report(data, title):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    
    # Настройка шрифта для подерки кириллицы
    pdfmetrics.registerFont(TTFont('Arial', 'arial.ttf'))
    p.setFont('Arial', 14)
    
    # Заголовок
    p.drawString(50, 800, title)
    p.setFont('Arial', 12)
    
    y = 750
    for line in data:
        p.drawString(50, y, str(line))
        y -= 20
        
    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer

@app.route('/reports/client_books_pdf/<int:client_id>')
@login_required
def client_books_report_pdf(client_id):
    # Число книг на руках
    books_count = Journal.query.filter(
        Journal.client_id == client_id,
        Journal.date_ret.is_(None)
    ).count()
    
    # Размер штрафа клиента
    client_fine = db.session.query(
        func.sum((Journal.date_ret - Journal.date_end) * BookType.fine)
    ).select_from(Journal).join(
        Book, 
        Journal.book_id == Book.id
    ).join(
        BookType,
        Book.type_id == BookType.id
    ).filter(
        Journal.client_id == client_id,
        Journal.date_ret > Journal.date_end
    ).scalar() or 0
    
    client = Client.query.get_or_404(client_id)
    
    # Создаем PDF с подержкой кириллицы
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    
    # Регистрируем шрифт с поддержкой кириллицы
    pdfmetrics.registerFont(TTFont('Arial', 'arial.ttf'))
    p.setFont('Arial', 14)
    
    # Используем кириллицу в тексте
    p.drawString(50, 800, 'Отчет по клиенту')
    p.drawString(50, 770, f'ФИО: {client.last_name} {client.first_name} {client.father_name}')
    p.drawString(50, 740, f'Книг на руках: {books_count}')
    p.drawString(50, 710, f'Общий штраф: {float(client_fine)} руб.')
    
    p.showPage()
    p.save()
    
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f'client_report_{client_id}.pdf',
        mimetype='application/pdf'
    )

@app.route('/reports/library_stats_pdf')
@login_required
def library_stats_pdf():
    # Размер самого большого штрафа
    max_fine = db.session.query(
        func.max((Journal.date_ret - Journal.date_end) * BookType.fine)
    ).select_from(Journal).join(
        Book,
        Journal.book_id == Book.id
    ).join(
        BookType,
        Book.type_id == BookType.id
    ).filter(
        Journal.date_ret > Journal.date_end
    ).scalar() or 0
    
    # Три самые популярые книги
    popular_books = db.session.query(
        Book.name,
        func.count(Journal.id).label('count')
    ).join(
        Journal,
        Book.id == Journal.book_id
    ).group_by(
        Book.name
    ).order_by(
        desc('count')
    ).limit(3).all()
    
    # Создаем PDF с поддержкой кириллицы
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    
    # Регистрируем шрифт с поддержкой кириллицы
    pdfmetrics.registerFont(TTFont('DejaVuSans', 'DejaVuSans.ttf'))
    p.setFont('DejaVuSans', 14)
    
    # Добавляем данные в PDF
    p.drawString(50, 800, 'Статистика библиотеки')
    p.drawString(50, 770, f'Максимальный штраф: {float(max_fine)} руб.')
    p.drawString(50, 740, 'Самые популярные книги:')
    
    y = 710
    for book, count in popular_books:
        p.drawString(70, y, f'- {book}: {count} выдач')
        y -= 30
    
    p.showPage()
    p.save()
    
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name='library_stats.pdf',
        mimetype='application/pdf'
    )

@app.route('/reports/overdue_books_pdf')
@login_required
def overdue_books_report_pdf():
    # Получаем список росроченных книг
    overdue_books = db.session.query(
        Journal.id,
        Client.last_name,
        Client.first_name,
        Book.name,
        Journal.date_end,
        func.current_date(),
        ((func.current_date() - Journal.date_end) * BookType.fine).label('fine')
    ).join(
        Client,
        Journal.client_id == Client.id
    ).join(
        Book,
        Journal.book_id == Book.id
    ).join(
        BookType,
        Book.type_id == BookType.id
    ).filter(
        Journal.date_ret.is_(None),
        Journal.date_end < func.current_date()
    ).order_by(desc('fine')).all()
    
    # Создаем PDF
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    
    pdfmetrics.registerFont(TTFont('Arial', 'arial.ttf'))
    p.setFont('Arial', 14)
    
    p.drawString(50, 800, 'Отчет по просроченным книгам')
    p.setFont('Arial', 12)
    
    y = 750
    for record in overdue_books:
        line = f"{record.last_name} {record.first_name} - {record.name} (просрочка: {record.fine} руб.)"
        p.drawString(50, y, line)
        y -= 20
    
    p.showPage()
    p.save()
    
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name='overdue_books.pdf',
        mimetype='application/pdf'
    )

@app.cli.command("create-users")
def create_users():
    # Создаем адмнистратора
    admin = User(username='admin', role='admin')
    admin.set_password('admin_password')
    
    # Создаем обычного пользователя
    user = User(username='user', role='user')
    user.set_password('user_password')
    
    db.session.add(admin)
    db.session.add(user)
    db.session.commit()
    
    print('Users created successfully')

def init_db():
    with app.app_context():
        # Удаляем таблицу users если она существует
        db.session.execute(text('DROP TABLE IF EXISTS users'))
        db.session.commit()
        
        # Создаем таблицы заново
        db.create_all()
        
        # Создаем пользователей с использованием метода set_password
        if User.query.count() == 0:
            admin = User(username='admin', role='admin')
            admin.set_password('admin123')
            
            user = User(username='user', role='user')
            user.set_password('user123')
            
            db.session.add(admin)
            db.session.add(user)
            db.session.commit()
            print('Default users created')

@app.route('/book_types/add', methods=['GET', 'POST'])
@login_required
@admin_required
def book_type_add():
    if request.method == 'POST':
        book_type = BookType(
            type=request.form['type'],
            fine=request.form['fine'],
            day_count=request.form['day_count']
        )
        db.session.add(book_type)
        db.session.commit()
        flash('Тип книги успешно добавлен')
        return redirect(url_for('book_types_list'))
    return render_template('references/book_type_form.html')

@app.route('/book_types/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def book_type_edit(id):
    book_type = BookType.query.get_or_404(id)
    if request.method == 'POST':
        book_type.type = request.form['type']
        book_type.fine = request.form['fine']
        book_type.day_count = request.form['day_count']
        db.session.commit()
        flash('Тип книги успешно обновлен')
        return redirect(url_for('book_types_list'))
    return render_template('references/book_type_form.html', book_type=book_type)

@app.route('/book_types/<int:id>/delete')
@login_required
@admin_required
def book_type_delete(id):
    book_type = BookType.query.get_or_404(id)
    db.session.delete(book_type)
    db.session.commit()
    flash('Тип книги успешно удален')
    return redirect(url_for('book_types_list'))

@app.route('/catalog')
@login_required
def catalog():
    search = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    query = Book.query.join(BookType)
    
    if search:
        query = query.filter(
            db.or_(
                Book.name.ilike(f'%{search}%'),
                BookType.type.ilike(f'%{search}%')
            )
        )
    
    pagination = query.paginate(page=page, per_page=10)
    return render_template('catalog.html', books=pagination.items, pagination=pagination, search=search)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Проверяем, существует ли пользователь
        if User.query.filter_by(username=username).first():
            flash('Пользователь с таким именем уже существует')
            return render_template('register.html')
            
        # Проверяем совпадение паролей
        if password != confirm_password:
            flash('Пароли не совпадают')
            return render_template('register.html')
            
        # Создаем нового пользователя
        user = User(username=username, role='user')
        user.set_password(password)
        
        try:
            db.session.add(user)
            db.session.commit()
            flash('Регистрация успешна! Теперь вы можете войти.')
            return redirect(url_for('login'))
        except:
            db.session.rollback()
            flash('Произошла ошибка при регистрации')
            
    return render_template('register.html')

# Добавляем вызо функции ри запуске
if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5003)
