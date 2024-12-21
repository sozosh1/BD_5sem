from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='user')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        return self.role == 'admin'
        
    def __repr__(self):
        return f'<User {self.username} (role: {self.role})>'

class Client(db.Model):
    __tablename__ = 'clients'
    
    id = db.Column(db.Integer, primary_key=True)
    last_name = db.Column(db.String(50))
    first_name = db.Column(db.String(50))
    father_name = db.Column(db.String(50))
    passport_seria = db.Column(db.String(4))
    passport_number = db.Column(db.String(6))

class BookType(db.Model):
    __tablename__ = 'book_types'
    
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(20))
    fine = db.Column(db.Numeric(10,2))
    day_count = db.Column(db.Integer)

class Book(db.Model):
    __tablename__ = 'books'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    cnt = db.Column(db.Integer)
    type_id = db.Column(db.Integer, db.ForeignKey('book_types.id'))
    
    book_type = db.relationship('BookType', backref='books')

class Journal(db.Model):
    __tablename__ = 'journal'
    
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    date_beg = db.Column(db.Date, nullable=False)
    date_end = db.Column(db.Date, nullable=False)
    date_ret = db.Column(db.Date)
    
    client = db.relationship('Client', backref=db.backref('journal_entries', lazy=True))
    book = db.relationship('Book', backref=db.backref('journal_entries', lazy=True)) 