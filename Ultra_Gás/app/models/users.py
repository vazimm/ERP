from app import db


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)  # nova coluna para nome
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)
    enviroment = db.Column(db.String(100), nullable=False) # nova coluna para ambiente
    tema = db.Column(db.String(30), nullable=False, default="root")
    user_type = db.Column(db.String(10), nullable=False)  # 'admin' ou 'user'
    